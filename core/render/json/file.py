import json
from viur.core.render.json.default import DefaultRender


class FileRender(DefaultRender):
    def renderUploadComplete(self, *args, **kwargs):
        return json.dumps("OKAY")

    def addDirSuccess(self, *args, **kwargs):
        return json.dumps("OKAY")
