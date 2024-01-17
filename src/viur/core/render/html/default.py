import codecs
import collections
import enum
import functools
import logging
import os
import typing as t

from jinja2 import ChoiceLoader, Environment, FileSystemLoader, Template

from viur.core import conf, current, db, errors, securitykey
from viur.core.bones import *
from viur.core.i18n import LanguageWrapper, TranslationExtension
from viur.core.skeleton import SkelList, SkeletonInstance
from . import utils as jinjaUtils
from ..json.default import CustomJsonEncoder

KeyValueWrapper = collections.namedtuple("KeyValueWrapper", ["key", "descr"])


class Render(object):
    """
        The core jinja2 render.

        This is the bridge between your ViUR modules and your templates.
        First, the default jinja2-api is exposed to your templates. See http://jinja.pocoo.org/ for
        more information. Second, we'll pass data das global variables to templates depending on the
        current action.

            - For list() a `skellist` is provided containing all requested skeletons to a limit
            - For view(): skel - a dictionary with values from the skeleton prepared for use inside html
            - For add()/edit: a dictionary as `skel` with `values`, `structure` and `errors` as keys.

        Third, a bunch of global filters (like urlencode) and functions (getEntry, ..) are available  to templates.

        See the ViUR Documentation for more information about functions and data available to jinja2 templates.

        Its possible for modules to extend the list of filters/functions available to templates by defining
        a function called `jinjaEnv`. Its called from the render when the environment is first created and
        can extend/override the functionality exposed to templates.

    """
    kind = "html"

    listTemplate = "list"
    viewTemplate = "view"
    addTemplate = "add"
    editTemplate = "edit"

    addSuccessTemplate = "add_success"
    editSuccessTemplate = "edit_success"
    deleteSuccessTemplate = "delete_success"

    listRepositoriesTemplate = "list_repositories"  # fixme: This is a relict, should be solved differently (later!).

    __haveEnvImported_ = False

    def __init__(self, parent=None, *args, **kwargs):
        super(Render, self).__init__(*args, **kwargs)
        if not Render.__haveEnvImported_:
            # We defer loading our plugins to this point to avoid circular imports
            # noinspection PyUnresolvedReferences
            from . import env
            Render.__haveEnvImported_ = True
        self.parent = parent

    def getTemplateFileName(
        self,
        template: str | list[str] | tuple[str],
        ignoreStyle: bool = False,
        raise_exception: bool = True,
    ) -> str | None:
        """
            Returns the filename of the template.

            This function decides in which language and which style a given template is rendered.
            The style is provided as get-parameters for special-case templates that differ from
            their usual way.

            It is advised to override this function in case that
            :func:`viur.core.render.jinja2.default.Render.getLoaders` is redefined.

            :param template: The basename of the template to use. This can optionally be also a sequence of names.
            :param ignoreStyle: Ignore any maybe given style hints.
            :param raise_exception: Defaults to raise an exception when not found, otherwise returns None.

            :returns: Filename of the template
        """
        validChars = "abcdefghijklmnopqrstuvwxyz1234567890-"
        htmlpath = getattr(self, "htmlpath", "html")

        if (
            not ignoreStyle
            and (style := current.request.get().template_style)
            and all(x in validChars for x in style.lower())
        ):
            style_postfix = f"_{style}"
        else:
            style_postfix = ""

        lang = current.language.get()

        if not isinstance(template, (tuple, list)):
            template = (template,)

        for tpl in template:
            filenames = [tpl]
            if style_postfix:
                filenames.append(tpl + style_postfix)

            if lang:
                filenames += [
                    os.path.join(lang, _tpl)
                    for _tpl in filenames
                ]

            for filename in reversed(filenames):
                filename += ".html"

                if "_" in filename:
                    dirname, tail = filename.split("_", 1)
                    if tail:
                        if conf.instance.project_base_path.joinpath(htmlpath, dirname, filename).is_file():
                            return os.path.join(dirname, filename)

                if conf.instance.project_base_path.joinpath(htmlpath, filename).is_file():
                    return filename

                if conf.instance.core_base_path.joinpath("viur", "core", "template", filename).is_file():
                    return filename

        msg = f"""Template {" or ".join((repr(tpl) for tpl in template))} not found."""
        if raise_exception:
            raise errors.NotFound(msg)

        logging.error(msg)
        return None

    def getLoaders(self) -> ChoiceLoader:
        """
            Return the list of Jinja2 loaders which should be used.

            May be overridden to provide an alternative loader
            (e.g. for fetching templates from the datastore).
        """
        # fixme: Why not use ChoiceLoader directly for template loading?
        return ChoiceLoader((
            FileSystemLoader(getattr(self, "htmlpath", "html")),
            FileSystemLoader(conf.instance.core_base_path / "viur" / "core" / "template"),
        ))

    def renderBoneValue(self,
                        bone: BaseBone,
                        skel: SkeletonInstance,
                        key: t.Any,  # TODO: unused
                        boneValue: t.Any,
                        isLanguageWrapped: bool = False
                        ) -> list | dict | KeyValueWrapper | LanguageWrapper | str | None:
        """
        Renders the value of a bone.

        It can be overridden and super-called from a custom renderer.

        :param bone: The bone which value should be rendered.
            (inherited from :class:`viur.core.bones.base.BaseBone`).
        :param skel: The skeleton containing the bone instance.
        :param key: The name of the bone.
        :param boneValue: The value of the bone.
        :param isLanguageWrapped: Is this bone wrapped inside a :class:`LanguageWrapper`?

        :return: A dict containing the rendered attributes.
        """
        if bone.languages and not isLanguageWrapped:
            res = LanguageWrapper(bone.languages)
            if isinstance(boneValue, dict):
                for language in bone.languages:
                    if language in boneValue:
                        res[language] = self.renderBoneValue(bone, skel, key, boneValue[language], True)
            return res
        elif bone.type == "select" or bone.type.startswith("select."):
            def get_label(value) -> str:
                if isinstance(value, enum.Enum):
                    return bone.values.get(value.value, value.name)
                return bone.values.get(value, str(value))

            if isinstance(boneValue, list):
                return {val: get_label(val) for val in boneValue}

            return KeyValueWrapper(boneValue, get_label(boneValue))

        elif bone.type == "relational" or bone.type.startswith("relational."):
            if isinstance(boneValue, list):
                tmpList = []
                for k in boneValue:
                    if not k:
                        continue
                    if bone.using is not None and k["rel"]:
                        k["rel"].renderPreparation = self.renderBoneValue
                        usingData = k["rel"]
                    else:
                        usingData = None
                    k["dest"].renderPreparation = self.renderBoneValue
                    tmpList.append({
                        "dest": k["dest"],
                        "rel": usingData
                    })
                return tmpList
            elif isinstance(boneValue, dict):
                if bone.using is not None and boneValue["rel"]:
                    boneValue["rel"].renderPreparation = self.renderBoneValue
                    usingData = boneValue["rel"]
                else:
                    usingData = None
                boneValue["dest"].renderPreparation = self.renderBoneValue
                return {
                    "dest": boneValue["dest"],
                    "rel": usingData
                }
        elif bone.type == "record" or bone.type.startswith("record."):
            value = boneValue
            if value:
                if bone.multiple:
                    ret = []
                    for entry in value:
                        entry.renderPreparation = self.renderBoneValue
                        ret.append(entry)
                    return ret
                value.renderPreparation = self.renderBoneValue
                return value
        elif bone.type == "password":
            return ""
        elif bone.type == "key":
            return db.encodeKey(boneValue) if boneValue else None

        else:
            return boneValue

        return None

    def get_template(self, action: str, template: str) -> Template:
        """
        Internal function for retrieving a template from an action name.
        """
        if not template:
            default_template = action + "Template"
            template = getattr(self.parent, default_template, None) or getattr(self, default_template)

        return self.getEnv().get_template(self.getTemplateFileName(template))

    def render_action_template(
        self,
        default: str,
        skel: SkeletonInstance,
        action: str,
        tpl: str = None,
        params: dict = None,
        **kwargs
    ) -> str:
        """
        Internal action rendering that provides a variable structure to render an input-form.
        The required information is passed via skel["structure"], skel["value"] and skel["errors"].

        Any data in **kwargs is passed unmodified to the template.

        :param default: The default action to render, which is used to construct a template name.
        :param skel: Skeleton of which should be used for the action.
        :param action: The name of the action, which is passed into the template.
        :param tpl: Name of a different template, which should be used instead of the default one.
        :param params: Optional data that will be passed unmodified to the template.

        Any data in **kwargs is passed unmodified to the template.

        :return: Returns the emitted HTML response.
        """
        template = self.get_template(default, tpl)

        skel.skey = BaseBone(descr="SecurityKey", readOnly=True, visible=False)
        skel["skey"] = securitykey.create()

        # fixme: Is this still be used?
        if current.request.get().kwargs.get("nomissing") == "1":
            if isinstance(skel, SkeletonInstance):
                super(SkeletonInstance, skel).__setattr__("errors", [])

        skel.renderPreparation = self.renderBoneValue

        return template.render(
            skel={
                "structure": skel.structure(),
                "errors": skel.errors,
                "value": skel
            },
            action=action,
            params=params,
            **kwargs
        )

    def render_view_template(
        self,
        default: str,
        skel: SkeletonInstance,
        action: str,
        tpl: str = None,
        params: dict = None,
        **kwargs
    ) -> str:
        """
        Renders a page with an entry.

        :param default: The default action to render, which is used to construct a template name.
        :param skel: Skeleton which contains the data of the corresponding entity.
        :param action: The name of the action, which is passed into the template.
        :param tpl: Name of a different template, which should be used instead of the default one.
        :param params: Optional data that will be passed unmodified to the template

        Any data in **kwargs is passed unmodified to the template.

        :return: Returns the emitted HTML response.
        """
        template = self.get_template(default, tpl)

        if isinstance(skel, SkeletonInstance):
            skel.renderPreparation = self.renderBoneValue

        return template.render(
            skel=skel,
            action=action,
            params=params,
            **kwargs
        )

    def list(self, skellist: SkelList, action: str = "list", tpl: str = None, params: t.Any = None, **kwargs) -> str:
        """
        Renders a page with a list of entries.

        :param skellist: List of Skeletons with entries to display.
        :param action: The name of the action, which is passed into the template.
        :param tpl: Name of a different template, which should be used instead of the default one.

        :param params: Optional data that will be passed unmodified to the template

        Any data in **kwargs is passed unmodified to the template.

        :return: Returns the emitted HTML response.
        """
        template = self.get_template("list", tpl)

        for skel in skellist:
            skel.renderPreparation = self.renderBoneValue

        return template.render(skellist=skellist, action=action, params=params, **kwargs)

    def view(self, skel: SkeletonInstance, action: str = "view", tpl: str = None, params: t.Any = None,
             **kwargs) -> str:
        """
        Renders a page for viewing an entry.

        For details, see self.render_view_template().
        """
        return self.render_view_template("view", skel, action, tpl, params, **kwargs)

    def add(self, skel: SkeletonInstance, action: str = "add", tpl: str = None, params: t.Any = None, **kwargs) -> str:
        """
        Renders a page for adding an entry.

        For details, see self.render_action_template().
        """
        return self.render_action_template("add", skel, action, tpl, params, **kwargs)

    def edit(self, skel: SkeletonInstance, action: str = "edit", tpl: str = None, params: t.Any = None,
             **kwargs) -> str:
        """
        Renders a page for modifying an entry.

        For details, see self.render_action_template().
        """
        return self.render_action_template("edit", skel, action, tpl, params, **kwargs)

    def addSuccess(
        self,
        skel: SkeletonInstance,
        action: str = "addSuccess",
        tpl: str = None,
        params: t.Any = None,
        **kwargs
    ) -> str:
        """
        Renders a page, informing that an entry has been successfully created.

        For details, see self.render_view_template().
        """
        return self.render_view_template("addSuccess", skel, action, tpl, params, **kwargs)

    def editSuccess(
        self,
        skel: SkeletonInstance,
        action: str = "editSuccess",
        tpl: str = None,
        params: t.Any = None,
        **kwargs
    ) -> str:
        """
        Renders a page, informing that an entry has been successfully modified.

        For details, see self.render_view_template().
        """
        return self.render_view_template("editSuccess", skel, action, tpl, params, **kwargs)

    def deleteSuccess(
        self,
        skel: SkeletonInstance,
        action: str = "deleteSuccess",
        tpl: str = None,
        params: t.Any = None,
        **kwargs
    ) -> str:
        """
        Renders a page, informing that an entry has been successfully deleted.

        For details, see self.render_view_template().
        """
        return self.render_view_template("deleteSuccess", skel, action, tpl, params, **kwargs)

    def listRootNodes(  # fixme: This is a relict, should be solved differently (later!).
        self,
        repos: t.List[dict[t.Literal["key", "name"], t.Any]],
        action: str = "listrootnodes",
        tpl: str = None,
        params: t.Any = None,
        **kwargs
    ) -> str:
        """
        Renders a list of available root nodes.

        :param repos: List of repositories (dict with "key"=>Repo-Key and "name"=>Repo-Name)
        :param action: The name of the action, which is passed into the template.
        :param tpl: Name of a different template, which should be used instead of the default one.
        :param params: Optional data that will be passed unmodified to the template

        Any data in **kwargs is passed unmodified to the template.

        :return: Returns the emitted HTML response.
        """
        template = self.get_template("listRootNodes", tpl)
        return template.render(repos=repos, action=action, params=params, **kwargs)

    def renderEmail(self,
                    dests: t.List[str],
                    file: str = None,
                    template: str = None,
                    skel: None | dict | SkeletonInstance | t.List["SkeletonInstance"] = None,
                    **kwargs) -> tuple[str, str]:
        """
            Renders an email.
            Uses the first not-empty line as subject and the remaining template as body.

            :param dests: Destination recipients.
            :param file: The name of a template from the deploy/emails directory.
            :param template: This string is interpreted as the template contents. Alternative to load from template file.
            :param skel: Skeleton or dict which data to supply to the template.
            :return: Returns the rendered email subject and body.
        """
        if isinstance(skel, SkeletonInstance):
            skel.renderPreparation = self.renderBoneValue

        elif isinstance(skel, list):
            for x in skel:
                if isinstance(x, SkeletonInstance):
                    x.renderPreparation = self.renderBoneValue
        if file is not None:
            try:
                tpl = self.getEnv().from_string(codecs.open("emails/" + file + ".email", "r", "utf-8").read())
            except Exception as err:
                logging.exception(err)
                tpl = self.getEnv().get_template(file + ".email")
        else:
            tpl = self.getEnv().from_string(template)
        content = tpl.render(skel=skel, dests=dests, **kwargs).lstrip().splitlines()
        if len(content) == 1:
            content.insert(0, "")  # add empty subject

        if isinstance(skel, SkeletonInstance):
            skel.renderPreparation = None

        elif isinstance(skel, list):
            for x in skel:
                if isinstance(x, SkeletonInstance):
                    x.renderPreparation = None

        return content[0], os.linesep.join(content[1:]).lstrip()

    def getEnv(self) -> Environment:
        """
            Constructs the Jinja2 environment.

            If an application specifies an jinja2Env function, this function
            can alter the environment before its used to parse any template.

            :return: Extended Jinja2 environment.
        """
        if "env" not in dir(self):
            loaders = self.getLoaders()
            self.env = Environment(loader=loaders,
                                   extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols", TranslationExtension])
            self.env.trCache = {}
            self.env.policies["json.dumps_kwargs"]["cls"] = CustomJsonEncoder

            # Import functions.
            for name, func in jinjaUtils.getGlobalFunctions().items():
                self.env.globals[name] = functools.partial(func, self)

            # Import filters.
            for name, func in jinjaUtils.getGlobalFilters().items():
                self.env.filters[name] = functools.partial(func, self)

            # Import tests.
            for name, func in jinjaUtils.getGlobalTests().items():
                self.env.tests[name] = functools.partial(func, self)

            # Import extensions.
            for ext in jinjaUtils.getGlobalExtensions():
                self.env.add_extension(ext)

            # Import module-specific environment, if available.
            if "jinjaEnv" in dir(self.parent):
                self.env = self.parent.jinjaEnv(self.env)

        return self.env
