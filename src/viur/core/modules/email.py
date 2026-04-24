from viur.core.prototypes.list import List
from viur.core.bones import *
from viur.core.skeleton import Skeleton

KINDNAME = "viur-emails"  # FIXME: VIUR4: Rename into "viur-email"


class EmailSkel(Skeleton):
    kindName = KINDNAME

    creationdate = None
    changedate = None
    name = None

    sender = EmailBone()

    subject = StringBone(
        escape_html=False,
    )

    body = RawBone(
        indexed=False,
    )

    dests = EmailBone(
        multiple=True,
    )

    cc = EmailBone(
        multiple=True,
    )

    bcc = EmailBone(
        multiple=True,
    )

    sendDate = DateBone()
    creationDate = DateBone()
    isSend = BooleanBone()
    errorCount = NumericBone()
    transportFuncResult = JsonBone()


class Email(List):
    kindName = KINDNAME

    default_order = {
        "orderby": "creationDate",
        "orderdir": "desc",
    }

    def adminInfo(self):
        return {
            "name": "E-Mail",
            "icon": "envelope-at",
            "disabledActions": ["add"],
            "views": [
                {
                    "name": "Sent",
                    "icon": "envelope-check",
                    "filter": {
                        "isSend": True,
                    } | (self.default_order or {}),
                },
                {
                    "name": "Unsent",
                    "icon": "envelope-x",
                    "filter": {
                        "isSend": False,
                    } | (self.default_order or {}),
                },
                {
                    "name": "Defective",
                    "icon": "envelope-exclamation",
                    "filter": {
                        "isSend": False,
                        "errorCount$gt": 0,
                    } | (self.default_order or {}),
                },
            ]
        }

    roles = {
        "admin": "*",
    }

    def canAdd(self):
        return False

    def canEdit(self, skel):
        if super().canEdit(skel):
            if skel["isSend"]:
                skel.readonly()

            return True

        return False
