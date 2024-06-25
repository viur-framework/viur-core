import base64
import json
import logging
import os
import puremagic
import requests
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Union
from urllib import request
from viur.core import db, utils
from viur.core.config import conf
from viur.core.tasks import CallDeferred, DeleteEntitiesIter, PeriodicTask


mailjet_dependencies = True
try:
    import mailjet_rest
except ModuleNotFoundError:
    mailjet_dependencies = False

"""
    This module implements an email delivery system for ViUR. Emails will be queued so that we don't overwhelm
    the email service. As the Appengine does not provide an email-api anymore, you'll have to use a 3rd party service
    to actually deliver the email. A sample implementation for Send in Blue (https://sendinblue.com/) is provided.
    To enable Send in Blue,    set conf["viur.email.transportClass"] to EmailTransportSendInBlue and add your API-Key to
    conf["viur.email.sendInBlue.apiKey"]. To send via another service, you'll have to implement a different transport
    class (and point conf["viur.email.transportClass"] to that class). This module needs a custom queue
    (viur-emails) with a larger backoff value (so that we don't try to deliver the same email multiple times within a
    short timeframe). A suggested configuration would be

    - name: viur-emails
        rate: 1/s
        retry_parameters:
            min_backoff_seconds: 3600
            max_backoff_seconds: 3600

"""


@PeriodicTask(interval=60 * 24)
def cleanOldEmailsFromLog(*args, **kwargs):
    """Start the QueryIter DeleteOldEmailsFromLog to remove old, successfully send emails from the queue"""
    qry = db.Query("viur-emails").filter("isSend =", True) \
        .filter("creationDate <", utils.utcNow() - conf["viur.email.logRetention"])
    DeleteEntitiesIter.startIterOnQuery(qry)


class EmailTransport(ABC):
    maxRetries = 3

    @staticmethod
    @abstractmethod
    def deliverEmail(*, sender: str, dests: List[str], cc: List[str], bcc: List[str], subject: str, body: str,
                     headers: Dict[str, str], attachments: List[Dict[str, bytes]],
                     customData: Union[dict, None], **kwargs):
        """
            The actual email delivery must be implemented here. All email-adresses can be either in the form of
            "mm@example.com" or "Max Musterman <mm@example.com>". If the delivery was successful, this method
            should return normally, if there was an error delivering the message it *must* raise an exception.

            :param sender: The sender to be used on the outgoing email
            :param dests: List of recipients
            :param cc: : List of carbon copy-recipients
            :param bcc: List of blind carbon copy-recipients
            :param subject: The subject of this email
            :param body: The contents of this email (may be text/plain or text/html)
            :param headers: Custom headers to send along with this email
            :param attachments: List of attachments to include in this email
            :param customData:
        """
        raise NotImplementedError()

    @staticmethod
    def validateQueueEntity(entity: db.Entity):
        """
            This function can be used to pre-validate the queue entity before it's deferred into the queue.
            Must raise an exception if the email cannot be send (f.e. if it contains an invalid attachment)
            :param entity: The entity to validate
        """
        return

    @staticmethod
    def transportSuccessfulCallback(entity: db.Entity):
        """
            This callback can be overridden by the project to execute additional tasks after an email
            has been successfully send.
            :param entity: The entity which has been send
        """
        pass

    @staticmethod
    def splitAddress(address: str) -> dict[str, str]:
        """
            Splits a Name/Address Pair into a dict,
            i.e. "Max Musterman <mm@example.com>" into
            {"name": "Max Mustermann", "email": "mm@example.com"}
            :param address: Name/Address pair
            :return: split dict
        """
        posLt = address.rfind("<")
        posGt = address.rfind(">")
        if -1 < posLt < posGt:
            email = address[posLt + 1:posGt]
            sname = address.replace(f"<{email}>", "", 1).strip()
            return {"name": sname, "email": email}
        else:
            return {"email": address}


@CallDeferred
def sendEmailDeferred(emailKey: db.Key):
    """
        Callback from the Taskqueue to send the given Email
        :param emailKey: Database-Key of the email we should send
    """
    logging.debug("Sending deferred email: %s" % str(emailKey))
    queueEntity = db.Get(emailKey)
    assert queueEntity, "Email queue object went missing!"
    if queueEntity["isSend"]:
        return True
    elif queueEntity["errorCount"] > 3:
        raise ChildProcessError("Error-Count exceeded")
    transportClass = conf["viur.email.transportClass"]  # First, ensure we're able to send email at all
    assert issubclass(transportClass, EmailTransport), "No or invalid email transportclass specified!"
    try:
        resultData = transportClass.deliverEmail(dests=queueEntity["dests"],
                                                 sender=queueEntity["sender"],
                                                 cc=queueEntity["cc"],
                                                 bcc=queueEntity["bcc"],
                                                 subject=queueEntity["subject"],
                                                 body=queueEntity["body"],
                                                 headers=queueEntity["headers"],
                                                 attachments=queueEntity["attachments"])
    except Exception:
        # Increase the errorCount and bail out
        queueEntity["errorCount"] += 1
        db.Put(queueEntity)
        raise
    # If that transportFunction did not raise an error that email has been successfully send
    queueEntity["isSend"] = True
    queueEntity["sendDate"] = utils.utcNow()
    queueEntity["transportFuncResult"] = resultData
    queueEntity.exclude_from_indexes.add("transportFuncResult")
    db.Put(queueEntity)
    try:
        transportClass.transportSuccessfulCallback(queueEntity)
    except Exception as e:
        logging.exception(e)


def normalize_to_list(value: Union[None, Any, List[Any], Callable[[], List]]) -> List[Any]:
    """
    Convert the given value to a list.

    If the value parameter is callable, it will be called first to get the actual value.
    """
    if callable(value):
        value = value()
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def sendEMail(*,
              tpl: str = None,
              stringTemplate: str = None,
              skel: Union[None, Dict, "SkeletonInstance", List["SkeletonInstance"]] = None,
              sender: str = None,
              dests: Union[str, List[str]] = None,
              cc: Union[str, List[str]] = None,
              bcc: Union[str, List[str]] = None,
              headers: Dict[str, str] = None,
              attachments: List[Dict[str, Any]] = None,
              context: Union[db.DATASTORE_BASE_TYPES, List[db.DATASTORE_BASE_TYPES], db.Entity] = None,
              **kwargs) -> bool:
    """
    General purpose function for sending e-mail.
    This function allows for sending e-mails, also with generated content using the Jinja2 template engine.
    Your have to implement a method which should be called to send the prepared email finally. For this you have
    to allocate *viur.email.transportClass* in conf.

    :param tpl: The name of a template from the deploy/emails directory.
    :param stringTemplate: This string is interpreted as the template contents. Alternative to load from template file.
        :param skel: The data made available to the template. In case of a Skeleton or SkelList, its parsed the usual way;\
        Dictionaries are passed unchanged.
    :param sender: The address sending this mail.
    :param dests: A list of addresses to send this mail to. A bare string will be treated as a list with 1 address.
    :param cc: Carbon-copy recipients. A bare string will be treated as a list with 1 address.
    :param bcc: Blind carbon-copy recipients. A bare string will be treated as a list with 1 address.
    :param headers: Specify headers for this email.
    :param attachments:
        List of files to be sent within the mail as attachments. Each attachment must be a dictionary with these keys:
            - filename (string): Name of the file that's attached. Always required
            - content (bytes): Content of the attachment as bytes. Required for the send in blue API.
            - mimetype (string): Mimetype of the file. Suggested parameter for other implementations (not used by SIB)
            - gcsfile (string): Link to a GCS-File to include instead of content.
            Not supported by the current SIB implementation

    :param context: Arbitrary data that can be stored along the queue entry to be evaluated in
        transportSuccessfulCallback (useful for tracking delivery / opening events etc).

    .. warning::
        As emails will be queued (and not send directly) you cannot exceed 1MB in total
        (for all text and attachments combined)!
    """
    # First, ensure we're able to send email at all
    transportClass = conf["viur.email.transportClass"]  # First, ensure we're able to send email at all
    assert issubclass(transportClass, EmailTransport), "No or invalid email transportclass specified!"
    # Ensure that all recipient parameters (dest, cc, bcc) are a list
    dests = normalize_to_list(dests)
    cc = normalize_to_list(cc)
    bcc = normalize_to_list(bcc)
    assert dests or cc or bcc, "No destination address given"
    assert all([isinstance(x, str) and x for x in dests]), "Found non-string or empty destination address"
    assert all([isinstance(x, str) and x for x in cc]), "Found non-string or empty cc address"
    assert all([isinstance(x, str) and x for x in bcc]), "Found non-string or empty bcc address"
    attachments = normalize_to_list(attachments)
    if not (bool(stringTemplate) ^ bool(tpl)):
        raise ValueError("You have to set the params 'tpl' xor a 'stringTemplate'.")
    if attachments:
        # Ensure each attachment has the filename key and rewrite each dict to db.Entity so we can exclude
        # it from being indexed
        for _ in range(0, len(attachments)):
            attachment = attachments.pop(0)
            assert "filename" in attachment
            entity = db.Entity()
            for k, v in attachment.items():
                entity[k] = v
                entity.exclude_from_indexes.add(k)
            attachments.append(entity)
        assert all(["filename" in x for x in attachments]), "Attachment is missing the filename key"
    # If conf["viur.email.recipientOverride"] is set we'll redirect any email to these address(es)
    if conf["viur.email.recipientOverride"]:
        logging.warning("Overriding destination %s with %s", dests, conf["viur.email.recipientOverride"])
        oldDests = dests
        newDests = normalize_to_list(conf["viur.email.recipientOverride"])
        dests = []
        for newDest in newDests:
            if newDest.startswith("@"):
                for oldDest in oldDests:
                    dests.append(oldDest.replace(".", "_dot_").replace("@", "_at_") + newDest)
            else:
                dests.append(newDest)
        cc = bcc = []
    elif conf["viur.email.recipientOverride"] is False:
        logging.warning("Sending emails disabled by config[viur.email.recipientOverride]")
        return False
    if conf["viur.email.senderOverride"]:
        sender = conf["viur.email.senderOverride"]
    elif sender is None:
        sender = f'viur@{conf["viur.instance.project_id"]}.appspotmail.com'
    subject, body = conf["viur.emailRenderer"](dests, tpl, stringTemplate, skel, **kwargs)
    # Push that email to the outgoing queue
    queueEntity = db.Entity(db.Key("viur-emails"))
    queueEntity["isSend"] = False
    queueEntity["errorCount"] = 0
    queueEntity["creationDate"] = utils.utcNow()
    queueEntity["sender"] = sender
    queueEntity["dests"] = dests
    queueEntity["cc"] = cc
    queueEntity["bcc"] = bcc
    queueEntity["subject"] = subject
    queueEntity["body"] = body
    queueEntity["headers"] = headers
    queueEntity["attachments"] = attachments
    queueEntity["context"] = context
    queueEntity.exclude_from_indexes = {"body", "attachments", "context"}
    transportClass.validateQueueEntity(queueEntity)  # Will raise an exception if the entity is not valid
    if conf["viur.instance.is_dev_server"] and not conf["viur.email.sendFromLocalDevelopmentServer"]:
        logging.info("Not sending email from local development server")
        logging.info("Subject: %s", queueEntity["subject"])
        logging.info("Body: %s", queueEntity["body"])
        logging.info("Recipients: %s", queueEntity["dests"])
        return False
    db.Put(queueEntity)
    sendEmailDeferred(queueEntity.key, _queue="viur-emails")
    return True


def sendEMailToAdmins(subject: str, body: str, *args, **kwargs) -> bool:
    """
    Sends an e-mail to the root users of the current app.

    If conf["viur.email.admin_recipients"] is set, these recipients
    will be used instead of the root users.

    :param subject: Defines the subject of the message.
    :param body: Defines the message body.
    """
    success = False
    try:
        users = []
        if conf["viur.email.admin_recipients"] is not None:
            users = normalize_to_list(conf["viur.email.admin_recipients"])
        elif "user" in dir(conf["viur.mainApp"]):
            for user_skel in conf["viur.mainApp"].user.viewSkel().all().filter("access =", "root").fetch():
                users.append(user_skel["name"])

        # Prefix the instance's project_id to subject
        subject = conf["viur.instance.project_id"] + ": " + subject

        if users:
            ret = sendEMail(dests=users, stringTemplate=os.linesep.join((subject, body)), *args, **kwargs)
            success = True
            return ret
        else:
            logging.warning("There are no recipients for admin e-mails available.")

    finally:
        if not success:
            logging.critical("Cannot send mail to Admins.")
            logging.critical("Subject of mail: %s", subject)
            logging.critical("Content of mail: %s", body)

    return False


class EmailTransportSendInBlue(EmailTransport):
    maxRetries = 3
    # List of allowed file extensions that can be send from Send in Blue
    allowedExtensions = {"gif", "png", "bmp", "cgm", "jpg", "jpeg", "tif",
                         "tiff", "rtf", "txt", "css", "shtml", "html", "htm",
                         "csv", "zip", "pdf", "xml", "doc", "docx", "ics",
                         "xls", "xlsx", "ppt", "tar", "ez"}

    @staticmethod
    def deliverEmail(*, sender: str, dests: List[str], cc: List[str], bcc: List[str], subject: str, body: str,
                     headers: Dict[str, str], attachments: List[Dict[str, bytes]], **kwargs):
        """
            Internal function for delivering Emails using Send in Blue. This function requires the
            conf["viur.email.sendInBlue.apiKey"] to be set.
            This function is supposed to return on success and throw an exception otherwise.
            If no exception is thrown, the email is considered send and will not be retried.
        """
        dataDict = {
            "sender": EmailTransportSendInBlue.splitAddress(sender),
            "to": [],
            "htmlContent": body,
            "subject": subject,
        }
        for dest in dests:
            dataDict["to"].append(EmailTransportSendInBlue.splitAddress(dest))
        # intitialize bcc and cc lists in dataDict
        if bcc:
            dataDict["bcc"] = []
            for dest in bcc:
                dataDict["bcc"].append(EmailTransportSendInBlue.splitAddress(dest))
        if cc:
            dataDict["cc"] = []
            for dest in cc:
                dataDict["cc"].append(EmailTransportSendInBlue.splitAddress(dest))
        if headers:
            if "Reply-To" in headers:
                dataDict["replyTo"] = EmailTransportSendInBlue.splitAddress(headers["Reply-To"])
                del headers["Reply-To"]
            if headers:
                dataDict["headers"] = headers
        if attachments:
            dataDict["attachment"] = []
            for attachment in attachments:
                dataDict["attachment"].append({
                    "name": attachment["filename"],
                    "content": base64.b64encode(attachment["content"]).decode("ASCII")
                })
        payload = json.dumps(dataDict).encode("UTF-8")
        headers = {
            "api-key": conf["viur.email.sendInBlue.apiKey"],
            "Content-Type": "application/json; charset=utf-8"
        }
        reqObj = request.Request(url="https://api.sendinblue.com/v3/smtp/email",
                                 data=payload, headers=headers, method="POST")
        try:
            response = request.urlopen(reqObj)
        except request.HTTPError as e:
            logging.error("Sending email failed!")
            logging.error(dataDict)
            logging.error(e.read())
            raise
        assert str(response.code)[0] == "2", "Received a non 2XX Status Code!"
        return response.read().decode("UTF-8")

    @staticmethod
    def validateQueueEntity(entity: db.Entity):
        """
            For Send in Blue, we'll validate the attachments (if any) against the list of supported file extensions
        """
        for attachment in entity.get("attachments") or []:
            ext = attachment["filename"].split(".")[-1].lower()
            if ext not in EmailTransportSendInBlue.allowedExtensions:
                raise ValueError("The file-extension %s cannot be send using Send in Blue" % ext)

    @PeriodicTask(60 * 60)
    @staticmethod
    def check_sib_quota() -> None:
        """Periodically checks the remaining SendInBlue email quota.

        This task does not have to be enabled.
        It automatically checks if the apiKey is configured.

        There are three default thresholds: 1000, 500, 100
        Others can be set via conf["viur.email.sendInBlue.thresholds"].
        An email will be sent for the lowest threshold that has been undercut.
        """
        if conf.get("viur.email.sendInBlue.apiKey") is None:
            return  # no SIB key, we cannot check

        req = requests.get(
            "https://api.sendinblue.com/v3/account",
            headers={"api-key": conf["viur.email.sendInBlue.apiKey"]},
        )
        if not req.ok:
            logging.error("Failed to fetch SIB account information")
            return
        data = req.json()
        logging.debug(f"SIB account data: {data}")
        for plan in data["plan"]:
            if plan["type"] == "payAsYouGo":
                credits = plan["credits"]
                break
        else:
            credits = -1
        logging.info(f"SIB E-Mail credits: {credits}")

        # Keep track of the last credits and the limit for which a email has
        # already been sent. This way, emails for the same limit will not be
        # sent more than once and the remaining e-mail credits will not be wasted.
        key = db.Key("viur-email-conf", "sib-credits")
        if not (entity := db.Get(key)):
            logging.debug(f"{entity = }")
            entity = db.Entity(key)
            logging.debug(f"{entity = }")
        logging.debug(f"{entity = }")
        entity.setdefault("latest_warning_for", None)
        entity["credits"] = credits
        entity["email"] = data["email"]

        thresholds = conf.get("viur.email.sendInBlue.thresholds", (1000, 500, 100))
        for idx, limit in list(enumerate(thresholds, 1))[::-1]:
            if credits < limit:
                if entity["latest_warning_for"] == limit:
                    logging.info(f"Already send an email for {limit = }.")
                    break

                sendEMailToAdmins(
                    f"SendInBlue email budget {credits} ({idx}. warning)",
                    f"The SendInBlue email budget reached {credits} credits "
                    f"for {data['email']}. Please increase soon.",
                )
                entity["latest_warning_for"] = limit
                break
        else:
            # Credits are above all limits
            entity["latest_warning_for"] = None

        db.Put(entity)


if mailjet_dependencies:
    class EmailTransportMailjet(EmailTransport):
        @staticmethod
        def deliverEmail(*, sender: str, dests: list[str], cc: list[str], bcc: list[str], subject: str, body: str,
                         headers: dict[str, str], attachments: list[dict[str, bytes]], **kwargs):
            api_key = conf.get("viur.email.mailjet_api_key")
            api_secret = conf.get("viur.email.mailjet_api_secret")

            if not (api_key and api_secret):
                raise RuntimeError("Mailjet config missing, check 'mailjet_api_key' and 'mailjet_api_secret'")

            email = {
                "from": EmailTransportMailjet.splitAddress(sender),
                "htmlpart": body,
                "subject": subject,
                "to": [EmailTransportMailjet.splitAddress(dest) for dest in dests],
            }

            if bcc:
                email["bcc"] = [EmailTransportMailjet.splitAddress(b) for b in bcc]

            if cc:
                email["cc"] = [EmailTransportMailjet.splitAddress(c) for c in cc]

            if headers:
                email["headers"] = headers

            if attachments:
                email["attachments"] = []

                for att in attachments:
                    if not (mimetype := att["mimetype"]):
                        # try to guess mimetype using puremagic
                        try:
                            mimetype = puremagic.from_string(att["content"], mime=True)
                        except puremagic.PureError:
                            mimetype = "application/octet-stream"

                email["attachments"].append({
                    "filename": att["filename"],
                    "base64content": base64.b64encode(att["content"]).decode("ASCII"),
                    "mimetype": mimetype
                })

            mj_client = mailjet_rest.Client(
                auth=(api_key, api_secret),
                version="v3.1"
            )

            result = mj_client.send.create(data={"messages": [email]})
            assert 200 <= result.status_code < 300, "Received a non 2XX Status Code!"
            return result.content.decode("UTF-8")
