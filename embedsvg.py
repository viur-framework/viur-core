import os, json, logging
from viur.core import conf


def initializeEmbedSvgPool():
	if conf["viur.render.html.embedsvg.pool"] is None:
		conf["viur.render.html.embedsvg.pool"] = {}

		for path in conf["viur.render.html.embedsvg.path"]:
			logging.debug("embedsvg caching path %r", path)

			content = None
			try:
				with open(os.path.join(os.getcwd(), *path.split("/")), "rb") as f:
					content = f.read().decode("UTF-8")
			except Exception as e:
				logging.exception(e)

			if not content:
				continue

			try:
				content = json.loads(content)
				conf["viur.render.html.embedsvg.pool"].update(content)

				logging.info("%d images added successfully to svg pool", len(content))
			except:
				logging.error("Content of file %r doesn't look like JSON", path)
