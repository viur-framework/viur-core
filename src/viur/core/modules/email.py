from viur.core.prototypes.list import List
from viur.core.bones import *
from viur.core.skeleton import Skeleton

KINDNAME = "viur-emails"  # FIXME: VIUR4: Rename into "viur-email"


class EmailSkel(Skeleton):
    kindName = KINDNAME

    creationdate = None  # FIXME: VIUR4: See "creationDate" below!
    changedate = None
    name = None

    sendDate = DateBone()  # FIXME: VIUR4: Rename to senddate
    creationDate = DateBone()  # FIXME: VIUR4: This should become the ordinary creationdate!

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

    isSend = BooleanBone()  # FIXME: VIUR4: Rename into is_send
    errorCount = NumericBone()  # FIXME: VIUR4: Rename into error_count
    transportFuncResult = JsonBone()  # FIXME: VIUR4: Rename into transport_func_result


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
