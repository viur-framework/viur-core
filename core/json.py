"""
JSON module replacement for ViUR
"""
import json, typing, datetime

from viur.core import db
from viur.core.i18n import translate


loads = json.loads


def dumps(o: typing.Any, cls=None, *args, **kwargs) -> str:

	class ViurJsonEncoder(json.JSONEncoder):
		"""
			This custom JSON-Encoder for this json-render ensures that translations are evaluated and can be dumped.
		"""

		def default(self, o: typing.Any) -> typing.Any:
			if isinstance(o, translate):
				return str(o)
			elif isinstance(o, datetime.datetime):
				return o.isoformat()
			elif isinstance(o, db.Key):
				return db.encodeKey(o)
			return json.JSONEncoder.default(self, o)

	if cls is None:
		cls = ViurJsonEncoder

	return json.dumps(o, cls=cls, *args, **kwargs)
