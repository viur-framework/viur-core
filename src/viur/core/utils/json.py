import base64
import datetime
import decimal
import json
import pytz
import typing as t
from viur.core import db


class ViURJsonEncoder(json.JSONEncoder):
    """
    Adds support for db.Key, db.Entity, datetime, timedelta, bytes, set and Decimal and converts
    the provided obj into a special dict with JSON-serializable values.
    """
    def default(self, obj: t.Any) -> t.Any:
        if isinstance(obj, bytes):
            return {".__bytes__": base64.b64encode(obj).decode("ASCII")}
        elif isinstance(obj, datetime.datetime):
            return {".__datetime__": obj.astimezone(pytz.UTC).isoformat()}
        elif isinstance(obj, datetime.timedelta):
            return {".__timedelta__": obj / datetime.timedelta(microseconds=1)}
        elif isinstance(obj, decimal.Decimal):
            # str() keeps the exact value (NumericBone(decimal=True)); float would round it
            return {".__decimal__": str(obj)}
        elif isinstance(obj, set):
            return {".__set__": list(obj)}
        elif hasattr(obj, "__iter__"):
            return tuple(obj)
        # cannot be tested in tests...
        elif isinstance(obj, db.Key):
            return {".__key__": str(obj)}

        return super().default(obj)

    @staticmethod
    def preprocess(obj: t.Any) -> t.Any:
        """
        Needed to preprocess db.Entity as it subclasses dict.
        There is currently no other way to integrate with JSONEncoder.
        """
        if isinstance(obj, db.Entity):
            return {
                ".__entity__": ViURJsonEncoder.preprocess(dict(obj)),
                ".__key__": str(obj.key) if obj.key else None
            }
        elif isinstance(obj, dict):
            return {
                ViURJsonEncoder.preprocess(key): ViURJsonEncoder.preprocess(value) for key, value in obj.items()
            }
        elif isinstance(obj, (list, tuple)):
            return tuple(ViURJsonEncoder.preprocess(value) for value in obj)

        elif hasattr(obj, "__class__") and obj.__class__.__name__ == "SkeletonInstance":  # SkeletonInstance
            return {bone_name: ViURJsonEncoder.preprocess(obj[bone_name]) for bone_name in obj}

        return obj


def dumps(obj: t.Any, *, cls: ViURJsonEncoder = ViURJsonEncoder, **kwargs) -> str:
    """
    Wrapper for json.dumps() which converts additional ViUR datatypes.
    """
    return json.dumps(cls.preprocess(obj), cls=cls, **kwargs)


def _decode_object_hook(obj: t.Any):
    """
        Inverse for _preprocess_json_object, which is an object-hook for json.loads.
        Check if the object matches a custom ViUR type and recreate it accordingly.
    """
    # Membership checks, not truthiness: b"" encodes to "", timedelta(0) to 0.0 and
    # set() to [] -- all falsy, yet they must round-trip to their type, not to the marker dict.
    if len(obj) == 1:
        if ".__bytes__" in obj:
            return base64.b64decode(obj[".__bytes__"])
        elif ".__datetime__" in obj:
            return datetime.datetime.fromisoformat(obj[".__datetime__"])
        elif ".__timedelta__" in obj:
            return datetime.timedelta(microseconds=obj[".__timedelta__"])
        elif ".__decimal__" in obj:
            return decimal.Decimal(obj[".__decimal__"])
        elif ".__key__" in obj:
            return db.Key.from_legacy_urlsafe(obj[".__key__"])
        elif ".__set__" in obj:
            return set(obj[".__set__"])

    elif len(obj) == 2 and all(k in obj for k in (".__entity__", ".__key__")):
        entity = db.Entity(db.Key.from_legacy_urlsafe(obj[".__key__"]) if obj[".__key__"] else None)
        entity.update(obj[".__entity__"])
        return entity

    return obj


def loads(s: str, *, object_hook=_decode_object_hook, **kwargs) -> t.Any:
    """
    Wrapper for json.loads() which recreates additional ViUR datatypes.
    """
    return json.loads(s, object_hook=object_hook, **kwargs)
