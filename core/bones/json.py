import ast
import json
import jsonschema
from typing import Union, Mapping
from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.bones.raw import RawBone


class JsonBone(RawBone):
    """
    This bone saves its content as a JSON-string, but unpacks its content to a dict or list when used.
    :param schema If provided we can control and verify which data to accept.
    Example:
        >>> schema = {
        >>>     "type" : "object",
        >>>     "properties" : {
        >>>         "price" : {"type" : "number"},
        >>>         "name" : {"type" : "string"},
        >>>     }
        >>> }
        This will only accept the provided JSON when price is a number and name is a string.

    """

    type = "raw.json"

    def __init__(self, indexed: bool = False, multiple: bool = False, languages: bool = None, schema: Mapping = {},
                 *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        assert not multiple
        assert not languages
        assert not indexed
        # Validate the schema, if it's invalid a SchemaError will be raised
        jsonschema.validators.validator_for(False).check_schema(schema)
        self.schema = schema

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

    def singleValueFromClient(self, value: Union[str, list, dict], *args, **kwargs):
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

                try:
                    jsonschema.validate(value, self.schema)
                except (jsonschema.exceptions.ValidationError, jsonschema.exceptions.SchemaError) as e:
                    return self.getEmptyValue(), [
                        ReadFromClientError(ReadFromClientErrorSeverity.Invalid,
                                            f"Invalid JSON for schema supplied: {e!s}")]
        return super().singleValueFromClient(value, *args, **kwargs)

    def structure(self) -> dict:
        return super().structure() | {
            "schema": self.schema
        }
