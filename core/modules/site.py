from viur.core import errors, exposed


class Site(object):
    adminInfo = None

    def __init__(self, *args, **kwargs):
        super(Site, self).__init__()
        self.modulePath = ""

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
