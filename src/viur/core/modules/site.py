from viur.core import Module, errors
from viur.core.decorators import exposed


class Site(Module):
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
