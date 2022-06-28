import json
from viur.core.render.xml.default import DefaultRender, serializeXML


class FileRender(DefaultRender):
    def renderUploadComplete(self, *args, **kwargs):
        return serializeXML("OKAY")

    def addDirSuccess(self, *args, **kwargs):
        return serializeXML("OKAY")
