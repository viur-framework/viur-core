import ast
import json
import jsonschema
import typing as t
from viur.core.bones.base import ReadFromClientError, ReadFromClientErrorSeverity
from viur.core.bones.raw import RawBone
from viur.core import utils


class JsonBone(RawBone):
    """
    This bone saves its content as a JSON-string, but unpacks its content to a dict or list when used.
    :param schema If provided we can control and verify which data to accept.

    ..  code-block:: python

        # Example
        schema= {"type": "object", "properties" :{"price": {"type": "number"},"name": {"type": "string"}}
        # This will only accept the provided JSON when price is a number and name is a string.

    """

    type = "raw.json"

    def __init__(
        self,
        *,
        indexed: bool = False,
        multiple: bool = False,
        languages: bool = None,
        schema: t.Mapping = {},
        **kwargs
    ):
        # JsonBone is bound to certain limits
        assert not multiple
        assert not languages
        assert not indexed

        super().__init__(indexed=indexed, multiple=multiple, languages=languages, **kwargs)

        # Validate the schema; if it's invalid a SchemaError will be raised
        jsonschema.validators.validator_for(False).check_schema(schema)
        self.schema = schema

    def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        return utils.json.dumps(skel.accessedValues[name])

    def singleValueUnserialize(self, val):
        return utils.json.loads(val)

    def singleValueFromClient(self, value: str | list | dict, skel, bone_name, client_data):
        if value:
            if not isinstance(value, (list, dict)):
                value = str(value)

                # Try to parse a JSON string
                try:
                    value = utils.json.loads(value)

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
                        ReadFromClientError(
                            ReadFromClientErrorSeverity.Invalid,
                            f"Invalid JSON for schema supplied: {e!s}")
                        ]

        return super().singleValueFromClient(value, skel, bone_name, client_data)

    def structure(self) -> dict:
        return super().structure() | {
            "schema": self.schema
        }
