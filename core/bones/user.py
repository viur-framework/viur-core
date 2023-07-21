from viur.core import current
from viur.core.bones.relational import RelationalBone


class UserBone(RelationalBone):
    """
    A specialized relational bone for handling user references. Extends the functionality of
    :class:`viur.core.bones.relational.RelationalBone` to include support for creation and update magic.

    :param bool creationMagic: If True, the bone will automatically store the creating user when a new entry is added.
    :param bool updateMagic: If True, the bone will automatically store the last user who updated the entry.
    :param bool visible: If True, the bone will be visible in the skeleton.
    :param bool readOnly: If True, the bone will be read-only and its value cannot be changed through user input.
    :param dict kwargs: Additional keyword arguments passed to the parent class constructor.
    :raises ValueError: If the bone has multiple set to True and a creation/update magic is set.
    """
    kind = "user"
    datafields = ["name"]

    def __init__(self, *, creationMagic=False, updateMagic=False, visible=None, readOnly=False, **kwargs):
        if creationMagic or updateMagic:
            readOnly = False
            if visible is None:
                visible = False  # defaults
        elif visible is None:
            visible = True

        super().__init__(visible=visible, readOnly=readOnly, **kwargs)

        self.creationMagic = creationMagic
        self.updateMagic = updateMagic

        if self.multiple and (creationMagic or updateMagic):
            raise ValueError("Cannot be multiple and have a creation/update-magic set!")

    def performMagic(self, skel, key, isAdd, *args, **kwargs):
        """
        Perform the magic operation on the bone value.

        If updateMagic is enabled or creationMagic is enabled and the operation is an addition,
        the bone will store the current user's key.

        :param SkeletonInstance skel: The skeleton instance to operate on.
        :param str key: The key of the bone in the skeleton.
        :param bool isAdd: If True, the operation is an addition. Otherwise, it is an update.
        :param args: Additional positional arguments.
        :param kwargs: Additional keyword arguments.
        :return: True if the magic operation was successful, False otherwise.
        :rtype: bool
        """
        if self.updateMagic or (self.creationMagic and isAdd):
            if user := current.user.get():
                return self.setBoneValue(skel, key, user["key"], False)
            skel[key] = None
            return True
