from .default import DefaultRender as default
from viur.core import conf, current, decorators, errors, Module, securitykey
from viur.core.decorators import exposed
from viur.core.render.json.default import CustomJsonEncoder
from viur.core.skeleton import SkeletonInstance
import datetime
import json
import logging

__all__ = ["default"]


@exposed
def skey(amount: int = 1, *args, **kwargs) -> str:
    """
    Creates CSRF-security-keys for transactions.

    All returned keys are associated with the session, therefore they cannot be used across sessions.
    The keys get a maximum lifetime of the session lifetime, afterward they become invalid.

    :param amount: Optional amount of securitykeys to create in a batch.
        `amount > 1` can only be used by authenticated users, for a maximum of 100 keys.

    See module securitykey for details.
    """
    current.request.get().response.headers["Content-Type"] = "application/json"

    if amount == 1:
        return json.dumps(securitykey.create())

    if not 0 < amount <= 100:
        raise errors.Forbidden("Invalid amount provided")

    if not current.user.get():
        raise errors.Forbidden("Batch securitykey creation is only available to authenticated users")

    return json.dumps(securitykey.create(amount=amount))


@exposed
def timestamp(*args, **kwargs) -> str:
    """
    Returns the current server time.
    """
    current.request.get().response.headers["Content-Type"] = "application/json"
    return json.dumps(datetime.datetime.now().strftime("%Y-%m-%dT%H-%M-%S"))


@exposed
@decorators.skey  # the endpoint below shadows the name skey in this module
def setLanguage(lang: str) -> None:
    """
    Sets the language of the current session, when it is one of ``conf.i18n.available_languages``.
    """
    if lang in conf.i18n.available_languages:
        current.language.set(lang)


def _is_admin(user_skel: SkeletonInstance | None) -> bool:
    """Whether *user_skel* may see the module configuration: it carries the "admin" or "root" access right."""
    return bool(user_skel and user_skel["access"] and any(flag in user_skel["access"] for flag in ("admin", "root")))


@exposed
def admin(*args, **kwargs):
    """
    Redirects to the admin tool, when the project ships one in ``admin/main.html`` or ``vi/main.html``.

    :raises: :exc:`viur.core.errors.NotFound`, when there is no admin tool.
    """
    if args or kwargs:
        raise errors.NotFound()

    if (
        not conf.instance.project_base_path.joinpath("vi", "main.html").exists()
        and not conf.instance.project_base_path.joinpath("admin", "main.html").exists()
    ):
        raise errors.NotFound()

    if conf.instance.is_dev_server or current.request.get().isSSLConnection:
        raise errors.Redirect("/vi/s/main.html")

    raise errors.Redirect(f"https://{current.request.get().request.host}/vi/s/main.html")


@exposed
def config() -> str:
    """
    Public settings of the admin tool; no login required.

    Users with the "admin" or "root" access right additionally get the core version and the description of every
    module, by its dotted path below ``/json/``.
    """
    current.request.get().response.headers["Content-Type"] = "application/json"

    result = {}
    configuration = {k.replace("_", "."): v for k, v in conf.admin.items(True)}

    if conf.user.google_client_id:
        configuration["admin.user.google.clientID"] = conf.user.google_client_id

    configuration["admin.language"] = current.language.get() or conf.i18n.default_language
    configuration["admin.languages"] = conf.i18n.available_languages

    if _is_admin(current.user.get()):
        # always fill up to 4 parts
        version = conf.version
        while len(version) < 4:
            version += (None,)

        result["version"] = version[:4]

        modules = {}
        visited_objects = set()

        # Recursively collects all routable modules; some modules reference others as their parent,
        # so every module is visited only once.
        def collect_modules(parent, depth: int = 0) -> None:
            if depth > 10:
                logging.warning(f"Reached maximum recursion limit of {depth} at {parent=}")
                return

            for key in dir(parent):
                module = getattr(parent, key, None)
                if not isinstance(module, Module) or module in visited_objects:
                    continue

                visited_objects.add(module)

                if admin_info := module.describe():
                    modules[module.modulePath.removeprefix("/json/").replace("/", ".")] = admin_info

                collect_modules(module, depth=depth + 1)

        collect_modules(conf.main_app.json)
        result["modules"] = modules

    result["configuration"] = configuration
    return json.dumps(result, cls=CustomJsonEncoder)


@exposed
def routes() -> str:
    """
    All routes of this instance.
    """
    current.request.get().response.headers["Content-Type"] = "application/json"

    def resolve(node: dict) -> list[str]:
        result = []

        for key, value in node.items():
            if isinstance(value, dict):
                result.extend(f"{key}/{sub}" for sub in resolve(value))
            else:
                result.append(key)

        return result

    return json.dumps(resolve(conf.main_resolver))


def _postProcessAppObj(obj):
    obj["admin"] = admin
    obj["config"] = config
    obj["routes"] = routes
    obj["setLanguage"] = setLanguage
    obj["skey"] = skey
    obj["timestamp"] = timestamp
    return obj
