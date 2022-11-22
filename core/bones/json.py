import json
import logging

from viur.core.bones import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.bones import BaseBone


class JsonBone(BaseBone):
    """
    This bone saves its content as a JSON-string.
    """

    type = "json"

    def __init__(self, indexed=False, multiple=False, languages=None, *args, **kwargs):
        assert not multiple
        assert not languages
        assert not indexed
        super().__init__(*args, **kwargs)

    def serialize(self, skel, name, parentIndexed):
        if name not in skel.accessedValues:
            return False

        value = skel.accessedValues[name]
        if isinstance(value, str):
            try:
                _ = json.loads(value)
                del _
            except Exception as e:
                logging.error(f"Error in serialize in JsonBone: {e=}")
                return False

            skel.dbEntity[name] = value
        else:
            skel.dbEntity[name] = json.dumps(value) if value is not None else None

        # Ensure our indexed flag is False
        skel.dbEntity.exclude_from_indexes.add(name)

        return True

    def unserialize(self, skel, name):
        if data := skel.dbEntity.get(name):
            skel.accessedValues[name] = json.loads(data)
            return True

        return False

    def singleValueFromClient(self, value, *args, **kwargs):
        if value:
            value = str(value)  # Try to parse a JSON string
            try:
                value = json.loads(value)
                return value, None
            except Exception as e:
                logging.error(f"Error in singleValueFromClient in JsonBone: {e=}")
                return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid,
                                                                  "Cannot parse to JSON")]
        else:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.NotSet,
                                                              "Field not submitted")]
