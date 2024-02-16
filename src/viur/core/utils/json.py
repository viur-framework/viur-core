import base64
import datetime
import json
import pytz
import typing as t
from viur.core import db


def _preprocess_json_object(obj: t.Any) -> t.Any:
    """
    Adds support for db.Key, db.Entity, datetime, bytes and and converts the provided obj
    into a special dict with JSON-serializable values.
    """
    if isinstance(obj, db.Key):
        return {".__key__": db.encodeKey(obj)}
    elif isinstance(obj, datetime.datetime):
        return {".__datetime__": obj.astimezone(pytz.UTC).isoformat()}
    elif isinstance(obj, bytes):
        return {".__bytes__": base64.b64encode(obj).decode("ASCII")}
    elif isinstance(obj, db.Entity):
        # TODO: Support Skeleton instances as well?
        return {
            ".__entity__": _preprocess_json_object(dict(obj)),
            ".__ekey__": db.encodeKey(obj.key) if obj.key else None
        }
    elif isinstance(obj, dict):
        return {_preprocess_json_object(k): _preprocess_json_object(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [_preprocess_json_object(x) for x in obj]

    return obj


def dumps(obj: t.Any, *args, **kwargs) -> str:
    """
    Wrapper for json.dumps() which converts additional ViUR datatypes.
    """
    return json.dumps(_preprocess_json_object(obj), *args, **kwargs)


def _decode_object_hook(obj: t.Any):
    """
        Inverse for _preprocess_json_object, which is an object-hook for json.loads.
        Check if the object matches a custom ViUR type and recreate it accordingly.
    """
    if len(obj) == 1:
        if key := obj.get(".__key__"):
            return db.Key.from_legacy_urlsafe(key)
        elif date := obj.get(".__datetime__"):
            return datetime.datetime.fromisoformat(date)
        elif buf := obj.get(".__bytes__"):
            return base64.b64decode(buf)

    elif len(obj) == 2 and ".__entity__" in obj and ".__ekey__" in obj:
        entity = db.Entity(db.Key.from_legacy_urlsafe(obj[".__ekey__"]) if obj[".__ekey__"] else None)
        entity.update(obj[".__entity__"])
        return entity

    return obj


def loads(s: str) -> t.Any:
    """
    Wrapper for json.loads() which recreates additional ViUR datatypes.
    """
    return json.loads(s, object_hook=_decode_object_hook)
