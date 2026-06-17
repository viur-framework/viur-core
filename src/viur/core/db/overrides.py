from google.cloud.datastore.helpers import _get_meaning, _get_value_from_value_pb
from google.cloud.datastore_v1.types import entity as entity_pb2

from .types import Entity, Key


def key_from_protobuf(pb):
    """Reconstruct a Key from a Datastore response protobuf, stripping database_id.

    Replaces the SDK default so that every Key returned from the Datastore API
    is created via our own Key class.  The ``partition_id.database_id`` field is
    intentionally ignored: the database is a client-level concern configured via
    the DATASTORE_DATABASE env var.  Storing it on individual Key objects would
    break ``to_legacy_urlsafe`` / ``Key.__str__`` and violates ViUR's design principle
    that keys are database-agnostic.

    The outgoing side (proto serialization) is handled by ``Key.database`` in
    ``db/types.py``, which reads the active database from the transport client.
    """
    path_args = []
    for element in pb.path:
        path_args.append(element.kind)
        if element.id:  # Simple field (int64)
            path_args.append(element.id)
        # This is safe: we expect proto objects returned will only have
        # one of `name` or `id` set.
        if element.name:  # Simple field (string)
            path_args.append(element.name)

    project = None
    if pb.partition_id.project_id:  # Simple field (string)
        project = pb.partition_id.project_id
    namespace = None
    if pb.partition_id.namespace_id:  # Simple field (string)
        namespace = pb.partition_id.namespace_id

    # database_id is intentionally ignored: the database is a client-level concern
    # configured via conf.db.database_id / DATASTORE_DATABASE, never stored on keys.
    return Key(*path_args, namespace=namespace, project=project)


def entity_from_protobuf(pb):
    """Factory method for creating an entity based on a protobuf.

    The protobuf should be one returned from the Cloud Datastore
    Protobuf API.

    :type pb: :class:`.entity_pb2.Entity`
    :param pb: The Protobuf representing the entity.

    :rtype: :class:`google.cloud.datastore.entity.Entity`
    :returns: The entity derived from the protobuf.
    """
    if isinstance(pb, entity_pb2.Entity):
        pb = pb._pb

    key = None
    if pb.HasField("key"):  # Message field (Key)
        key = key_from_protobuf(pb.key)

    entity_props = {}
    entity_meanings = {}
    exclude_from_indexes = []

    for prop_name, value_pb in pb.properties.items():
        value = _get_value_from_value_pb(value_pb)
        entity_props[prop_name] = value

        # Check if the property has an associated meaning.
        is_list = isinstance(value, list)
        meaning = _get_meaning(value_pb, is_list=is_list)
        if meaning is not None:
            entity_meanings[prop_name] = (meaning, value)

        # Check if ``value_pb`` was excluded from index. Lists need to be
        # special-cased and we require all ``exclude_from_indexes`` values
        # in a list agree.
        if is_list and len(value) > 0:
            exclude_values = set(
                value_pb.exclude_from_indexes
                for value_pb in value_pb.array_value.values
            )
            if len(exclude_values) != 1:
                raise ValueError(
                    "For an array_value, subvalues must either "
                    "all be indexed or all excluded from "
                    "indexes."
                )

            if exclude_values.pop():
                exclude_from_indexes.append(prop_name)
        else:
            if value_pb.exclude_from_indexes:
                exclude_from_indexes.append(prop_name)

    entity = Entity(key=key, exclude_from_indexes=exclude_from_indexes)
    entity.update(entity_props)
    entity._meanings.update(entity_meanings)
    return entity
