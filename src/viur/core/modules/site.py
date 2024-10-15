from viur.core import Module, errors
from viur.core.decorators import exposed


class Site(Module):
    """
    The Site module simply serves static templates without a module-binding stored in html/sites.

    It is normally imported as `s` module in modern ViUR projects, to serve pages under short URL.
    Therefore, a template `html/sites/imprint.html` can be accessed via `/s/imprint` by default.
    """

    adminInfo = None

    @exposed
    def index(self, template="index", *arg, **kwargs):
        if ".." in template or "/" in template:
            return

        try:
            template = self.render.getEnv().get_template(self.render.getTemplateFileName("sites/" + template))
        except:
            raise errors.NotFound()

        return template.render()


Site.html = True
