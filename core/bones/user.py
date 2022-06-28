from viur.core.bones.relational import RelationalBone
from viur.core.config import conf


class UserBone(RelationalBone):
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
        if self.updateMagic or (self.creationMagic and isAdd):
            user = conf["viur.mainApp"].user.getCurrentUser()
            if user:
                return self.setBoneValue(skel, key, user["key"], False)
            skel[key] = None
            return True
