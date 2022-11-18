import json
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
            value = str(value)
            # Try to parse a JSON string
            try:
                value = json.loads(value)
            except Exception as e:
                raise f"Error in singleValueFromClient in JsonBone: {e=}"

        return super().singleValueFromClient(value, *args, **kwargs)
