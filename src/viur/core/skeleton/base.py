import fnmatch
import logging
import typing as t

from deprecated.sphinx import deprecated

from .meta import MetaBaseSkel
from ..bones.base import BaseBone, ReadFromClientErrorSeverity
from ..config import conf

if t.TYPE_CHECKING:
    from .instance import SkeletonInstance


class BaseSkeleton(object, metaclass=MetaBaseSkel):
    """
        This is a container-object holding information about one database entity.

        It has to be sub-classed with individual information about the kindName of the entities
        and its specific data attributes, the so called bones.
        The Skeleton stores its bones in an :class:`OrderedDict`-Instance, so the definition order of the
        contained bones remains constant.

        :ivar key: This bone stores the current database key of this entity. \
        Assigning to this bones value is dangerous and does *not* affect the actual key its stored in.

        :vartype key: server.bones.BaseBone

        :ivar creationdate: The date and time where this entity has been created.
        :vartype creationdate: server.bones.DateBone

        :ivar changedate: The date and time of the last change to this entity.
        :vartype changedate: server.bones.DateBone
    """
    __viurBaseSkeletonMarker__ = True
    boneMap = None

    @classmethod
    @deprecated(
        version="3.7.0",
        reason="Function renamed. Use subskel function as alternative implementation.",
    )
    def subSkel(cls, *subskel_names, fullClone: bool = False, **kwargs) -> "SkeletonInstance":
        return cls.subskel(*subskel_names, clone=fullClone)  # FIXME: REMOVE WITH VIUR4

    @classmethod
    def subskel(
        cls,
        *names: str,
        bones: t.Iterable[str] = (),
        clone: bool = False,
    ) -> "SkeletonInstance":
        """
            Creates a new sub-skeleton from the current skeleton.

            A sub-skeleton is a copy of the original skeleton, containing only a subset of its bones.

            Sub-skeletons can either be defined using the the subSkels property of the Skeleton object,
            or freely by giving patterns for bone names which shall be part of the sub-skeleton.

            1. Giving names as parameter merges the bones of all Skeleton.subSkels-configurations together.
               This is the usual behavior. By passing multiple sub-skeleton names to this function, a sub-skeleton
               with the union of all bones of the specified sub-skeletons is returned. If an entry called "*"
               exists in the subSkels-dictionary, the bones listed in this entry will always be part of the
               generated sub-skeleton.
            2. Given the *bones* parameter allows to freely specify a sub-skeleton; One specialty here is,
               that the order of the bones can also be changed in this mode. This mode is the new way of defining
               sub-skeletons, and might become the primary way to define sub-skeletons in future.
            3. Both modes (1 + 2) can be combined, but then the original order of the bones is kept.
            4. The "key" bone is automatically available in each sub-skeleton.
            5. An fnmatch-compatible wildcard pattern is allowed both in the subSkels-bone-list and the
               free bone list.

            Example (TodoSkel is the example skeleton from viur-base):
            ```py
            # legacy mode (see 1)
            subskel = TodoSkel.subskel("add")
            # creates subskel: key, firstname, lastname, subject

            # free mode (see 2) allows to specify a different order!
            subskel = TodoSkel.subskel(bones=("subject", "message", "*stname"))
            # creates subskel: key, subject, message, firstname, lastname

            # mixed mode (see 3)
            subskel = TodoSkel.subskel("add", bones=("message", ))
            # creates subskel: key, firstname, lastname, subject, message
            ```

            :param bones: Allows to specify an iterator of bone names (more precisely, fnmatch-wildards) which allow
                to freely define a subskel. If *only* this parameter is given, the order of the specification also
                defines, the order of the list. Otherwise, the original order as defined in the skeleton is kept.
            :param clone: If set True, performs a cloning of the used bone map, to be entirely stand-alone.

            :return: The sub-skeleton of the specified type.
        """
        from_subskel = False
        bones = list(bones)

        for name in names:
            # a str refers to a subskel name from the cls.subSkel dict
            if isinstance(name, str):
                # add bones from "*" subskel once
                if not from_subskel:
                    bones.extend(cls.subSkels.get("*") or ())
                    from_subskel = True

                bones.extend(cls.subSkels.get(name) or ())

            else:
                raise ValueError(f"Invalid subskel definition: {name!r}")

        if from_subskel:
            # when from_subskel is True, create bone names based on the order of the bones in the original skeleton
            bones = tuple(k for k in cls.__boneMap__.keys() if any(fnmatch.fnmatch(k, n) for n in bones))

        if not bones:
            raise ValueError("The given subskel definition doesn't contain any bones!")

        return cls(bones=bones, clone=clone)

    @classmethod
    def setSystemInitialized(cls):
        for attrName in dir(cls):
            bone = getattr(cls, attrName)
            if isinstance(bone, BaseBone):
                bone.setSystemInitialized()

    @classmethod
    def setBoneValue(
        cls,
        skel: "SkeletonInstance",
        boneName: str,
        value: t.Any,
        append: bool = False,
        language: t.Optional[str] = None
    ) -> bool:
        """
            Allows for setting a bones value without calling fromClient or assigning a value directly.
            Sanity-Checks are performed; if the value is invalid, that bone flips back to its original
            (default) value and false is returned.

            :param boneName: The name of the bone to be modified
            :param value: The value that should be assigned. It's type depends on the type of that bone
            :param append: If True, the given value is appended to the values of that bone instead of
                replacing it. Only supported on bones with multiple=True
            :param language: Language to set

            :return: Wherever that operation succeeded or not.
        """
        bone = getattr(skel, boneName, None)

        if not isinstance(bone, BaseBone):
            raise ValueError(f"{boneName!r} is no valid bone on this skeleton ({skel!r})")

        if language:
            if not bone.languages:
                raise ValueError("The bone {boneName!r} has no language setting")
            elif language not in bone.languages:
                raise ValueError("The language {language!r} is not available for bone {boneName!r}")

        if value is None:
            if append:
                raise ValueError("Cannot append None-value to bone {boneName!r}")

            if language:
                skel[boneName][language] = [] if bone.multiple else None
            else:
                skel[boneName] = [] if bone.multiple else None

            return True

        _ = skel[boneName]  # ensure the bone is being unserialized first
        return bone.setBoneValue(skel, boneName, value, append, language)

    @classmethod
    def fromClient(
        cls,
        skel: "SkeletonInstance",
        data: dict[str, list[str] | str],
        *,
        amend: bool = False,
        ignore: t.Optional[t.Iterable[str]] = None,
    ) -> bool:
        """
            Load supplied *data* into Skeleton.

            This function works similar to :func:`~viur.core.skeleton.Skeleton.setValues`, except that
            the values retrieved from *data* are checked against the bones and their validity checks.

            Even if this function returns False, all bones are guaranteed to be in a valid state.
            The ones which have been read correctly are set to their valid values;
            Bones with invalid values are set back to a safe default (None in most cases).
            So its possible to call :func:`~viur.core.skeleton.Skeleton.write` afterwards even if reading
            data with this function failed (through this might violates the assumed consistency-model).

            :param skel: The skeleton instance to be filled.
            :param data: Dictionary from which the data is read.
            :param amend: Defines whether content of data may be incomplete to amend the skel,
                which is useful for edit-actions.
            :param ignore: optional list of bones to be ignored; Defaults to all readonly-bones when set to None.

            :returns: True if all data was successfully read and complete. \
            False otherwise (e.g. some required fields where missing or where invalid).
        """
        complete = True
        skel.errors = []

        for key, bone in skel.items():
            if (ignore is None and bone.readOnly) or key in (ignore or ()):
                continue

            if errors := bone.fromClient(skel, key, data):
                for error in errors:
                    # insert current bone name into error's fieldPath
                    error.fieldPath.insert(0, str(key))

                    # logging.info(f"{key=} {error=} {skel[key]=} {bone.getEmptyValue()=}")

                    incomplete = (
                        # always when something is invalid
                        error.severity == ReadFromClientErrorSeverity.Invalid
                        or (
                            # only when path is top-level
                            len(error.fieldPath) == 1
                            and (
                                # bone is generally required
                                bool(bone.required)
                                and (
                                    # and value is either empty
                                    error.severity == ReadFromClientErrorSeverity.Empty
                                    # or not set, depending on amending mode
                                    or (
                                        error.severity == ReadFromClientErrorSeverity.NotSet
                                        and (amend and bone.isEmpty(skel[key]))
                                        or not amend
                                    )
                                )
                            )
                        )
                    )

                    # in case there are language requirements, test additionally
                    if bone.languages and isinstance(bone.required, (list, tuple)):
                        incomplete &= any([key, lang] == error.fieldPath for lang in bone.required)

                    # logging.debug(f"BaseSkel.fromClient {incomplete=} {error.severity=} {bone.required=}")

                    if incomplete:
                        complete = False

                        if conf.debug.skeleton_from_client:
                            logging.error(
                                f"""{getattr(cls, "kindName", cls.__name__)}: {".".join(error.fieldPath)}: """
                                f"""({error.severity}) {error.errorMessage}"""
                            )
                    else:
                        errors.clear()

                skel.errors += errors

        return complete

    @classmethod
    def refresh(cls, skel: "SkeletonInstance[t.Self]"):
        """
            Refresh the bones current content.

            This function causes a refresh of all relational bones and their associated
            information.
        """
        logging.debug(f"""Refreshing {skel["key"]!r} ({skel.get("name")!r})""")

        for key, bone in skel.items():
            if not isinstance(bone, BaseBone):
                continue

            _ = skel[key]  # Ensure value gets loaded
            bone.refresh(skel, key)

    @classmethod
    def readonly(cls, skel: "SkeletonInstance"):
        """
            Set all bones to readonly in the Skeleton.
        """
        for bone in skel.values():
            if not isinstance(bone, BaseBone):
                continue
            bone.readOnly = True

    def __new__(cls, *args, **kwargs) -> "SkeletonInstance":
        from .instance import SkeletonInstance
        return SkeletonInstance(cls, *args, **kwargs)
