import ast
import json
from typing import Union, Any

from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.bones.raw import RawBone


class JsonBone(RawBone):
    """
    This bone saves its content as a JSON-string, but unpacks its content to a dict or list when used.
    """

    type = "raw.json"

    def __init__(self, indexed: bool = False, multiple: bool = False, languages: bool = None, *args, **kwargs):
        assert not multiple
        assert not languages
        assert not indexed
        super().__init__(*args, **kwargs)

    def serialize(self, skel: 'SkeletonInstance', name: str, parentIndexed: bool) -> bool:
        if name in skel.accessedValues:
            skel.dbEntity[name] = json.dumps(skel.accessedValues[name])

            # Ensure this bone is NOT indexed!
            skel.dbEntity.exclude_from_indexes.add(name)

            return True

        return False

    def unserialize(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> bool:
        if data := skel.dbEntity.get(name):
            skel.accessedValues[name] = json.loads(data)
            return True

        return False

    def singleValueFromClient(self, value: Union[str, list, dict], skel: 'SkeletonInstance',
                              bone_name: str, client_data: dict
                              ) -> tuple[Any, list[ReadFromClientError] | None]:
        if value:
            if not isinstance(value, (list, dict)):
                value = str(value)

                # Try to parse a JSON string
                try:
                    value = json.loads(value)

                except json.decoder.JSONDecodeError as e:
                    # Try to parse a Python dict as fallback
                    try:
                        value = ast.literal_eval(value)

                    except (SyntaxError, ValueError):
                        # If this fails, report back the JSON parse error
                        return self.getEmptyValue(), [
                            ReadFromClientError(ReadFromClientErrorSeverity.Invalid, f"Invalid JSON supplied: {e!s}")
                        ]

        return super().singleValueFromClient(value, skel, bone_name, client_data)
