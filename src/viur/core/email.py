import base64
import datetime
import json
import logging
import os
import smtplib
import ssl
import typing as t
from abc import ABC, abstractmethod
from email import encoders
from email.message import EmailMessage
from email.mime.base import MIMEBase
from urllib import request

import requests
from deprecated.sphinx import deprecated
from google.appengine.api.mail import Attachment as GAE_Attachment, SendMail as GAE_SendMail

from viur.core import db, utils
from viur.core.bones.text import HtmlSerializer
from viur.core.config import conf
from viur.core.tasks import CallDeferred, DeleteEntitiesIter, PeriodicTask

if t.TYPE_CHECKING:
    from viur.core.skeleton import SkeletonInstance

mailjet_dependencies = True
try:
    import mailjet_rest
except ModuleNotFoundError:
    mailjet_dependencies = False

"""
This module implements an email delivery system for ViUR.
Emails will be queued so that we don't overwhelm the email service.
As the App Engine does provide only an limited email api, we recommend to use
a 3rd party service to actually deliver the email in production.

This module includes implementation for various services, but own
implementations are possible too.
To enable a service, assign an instance of one of the implementation to
:attr:`core.config.conf.email.transport_class`.
By default :class:`EmailTransportAppengine` is enabled.

This module needs a custom queue (viur-emails, :attr:`EMAIL_KINDNAME`)
with a larger backoff value (so that we don't try to deliver the same email
multiple times within a short timeframe).

A suggested configuration for your `queue.yaml` would be:

.. code-block:: yaml

    - name: viur-emails
        rate: 1/s
        retry_parameters:
            min_backoff_seconds: 3600
            max_backoff_seconds: 3600
"""

EMAIL_KINDNAME: t.Final[str] = "viur-emails"
"""Kindname for the email-queue entities in datastore"""

EMAIL_QUEUE: t.Final[str] = "viur-emails"
"""Name of the Cloud Tasks queue"""

AttachmentInline = t.TypedDict("AttachmentInline", {
    "filename": str,
    "content": bytes,
    "mimetype": str,
})
AttachmentViurFile = t.TypedDict("AttachmentViurFile", {
    "filename": str,
    "file_key": db.Key | str,
})
AttachmentGscFile = t.TypedDict("AttachmentGscFile", {
    "filename": str,
    "gcsfile": db.Key | str,
})
Attachment: t.TypeAlias = AttachmentInline | AttachmentViurFile | AttachmentGscFile

AddressPair = t.TypedDict("AddressPair", {
    "email": str,
    "name": t.NotRequired[str],
})


@PeriodicTask(interval=datetime.timedelta(days=1))
def clean_old_emails_from_log(*args, **kwargs):
    """Periodically delete sent emails, which are older than :attr:`conf.email.log_retention` from datastore queue"""
    qry = (
        db.Query(EMAIL_KINDNAME)
        .filter("isSend =", True)
        .filter("creationDate <", utils.utcNow() - conf.email.log_retention)
    )
    DeleteEntitiesIter.startIterOnQuery(qry)


class EmailTransport(ABC):
    """Transport handler to deliver emails.

    Implement for a specific service and set the instance to :attr:`conf.email.transport_class`
    """
    max_retries = 3
    """maximum number of attempts to send a email."""

    @abstractmethod
    def deliver_email(
        self,
        *,
        sender: str,
        dests: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        headers: dict[str, str],
        attachments: list[Attachment],
        **kwargs: t.Any,
    ) -> t.Any:
        """
        This method handles the actual sending of emails.

        It must be implemented by each type. All email-addresses can be either in the form of
        "mm@example.com" or "Max Mustermann <mm@example.com>". If the delivery was successful, this method
        should return normally, if there was an error delivering the message it *must* raise an exception.

        :param sender: The sender to be used on the outgoing email
        :param dests: List of recipients
        :param cc: List of carbon copy-recipients
        :param bcc: List of blind carbon copy-recipients
        :param subject: The subject of this email
        :param body: The contents of this email (may be text/plain or text/html)
        :param headers: Custom headers to send along with this email
        :param attachments: List of attachments to include in this email

        :return: Any value that can be stored in the datastore in the queue entity as `transportFuncResult`.
        """
        ...

    def validate_queue_entity(self, entity: db.Entity) -> None:
        """
        This function can be implemented to pre-validate the queue entity before it's deferred into the queue.
        Must raise an exception if the email cannot be send (f.e. if it contains an invalid attachment)
        :param entity: The entity to validate
        """
        ...

    def transport_successful_callback(self, entity: db.Entity):
        """
        This callback can be implemented to execute additional tasks after an email
        has been successfully send.
        :param entity: The entity which has been sent
        """
        ...

    def split_address(self, address: str) -> AddressPair:
        """
        Splits a Name/Address Pair into a dict,
        i.e. "Max Mustermann <mm@example.com>" into
        {"name": "Max Mustermann", "email": "mm@example.com"}
        :param address: Name/Address pair
        :return: split dict
        """
        pos_lt = address.rfind("<")
        pos_gt = address.rfind(">")
        if -1 < pos_lt < pos_gt:
            email = address[pos_lt + 1:pos_gt]
            name = address.replace(f"<{email}>", "", 1).strip()
            return {"name": name, "email": email}
        else:
            return {"email": address}

    def validate_attachment(self, attachment: Attachment) -> None:
        """Validate attachment before queueing the email"""
        if not isinstance(attachment, dict):
            raise TypeError(f"Attachment must be a dict, not {type(attachment)}")
        if "filename" not in attachment:
            raise ValueError(f"Attachment {attachment} must have a filename")
        if not any(prop in attachment for prop in ("content", "file_key", "gcsfile")):
            raise ValueError(f"Attachment {attachment} must have content, file_key or gcsfile")
        if "content" in attachment and not isinstance(attachment["content"], bytes):
            raise ValueError(f"Attachment content must be bytes, not {type(attachment['content'])}")

    def fetch_attachment(self, attachment: Attachment) -> AttachmentInline:
        """Fetch attachment (if necessary) in send_email_deferred deferred task

        This allows sending emails with large attachments,
        and prevents the queue entry from exceeding the maximum datastore Entity size.
        """
        # We need a copy of the attachments to keep the content apart from the db.Entity,
        # which will be re-written later with the response.
        attachment = attachment.copy()
        if file_key := attachment.get("file_key"):
            if attachment.get("content"):
                raise ValueError(f'Got {file_key=} but also content in attachment {attachment.get("filename")=}')
            blob, content_type = conf.main_app.vi.file.read(key=file_key)
            attachment["content"] = blob.getvalue()
            attachment["mimetype"] = content_type
        elif gcsfile := attachment.get("gcsfile"):
            if attachment.get("content"):
                raise ValueError(f'Got {gcsfile=} but also content in attachment {attachment.get("filename")=}')
            blob, content_type = conf.main_app.vi.file.read(path=gcsfile)
            attachment["content"] = blob.getvalue()
            attachment["mimetype"] = content_type
        return attachment


@CallDeferred
def send_email_deferred(key: db.Key):
    """
    Task that send an email.

    This task is enqueued into the Cloud Tasks queue viur-email (see :attr:`EMAIL_QUEUE`) by :meth:`send_email`.
    Send the email by calling the implemented :meth:`EmailTransport.deliver_email`
    of the configures :attr:`conf.email.transport_class`.

    :param key: Datastore key of the email to send
    """
    logging.debug(f"Sending deferred email {key!r}")
    if not (queued_email := db.get(key)):
        raise ValueError(f"Email queue entity with {key=!r} went missing!")

    if queued_email["isSend"]:
        return True

    transport_class = conf.email.transport_class  # First, ensure we're able to send email at all
    if not isinstance(transport_class, EmailTransport):
        raise ValueError(f"No or invalid email transportclass specified! ({transport_class=})")

    if queued_email["errorCount"] > transport_class.max_retries:
        raise ChildProcessError("Error-Count exceeded")

    try:
        # A datastore entity has no empty lists or dicts, these values always
        # become `None`. Therefore, the type must be restored here with `or []`.
        result_data = transport_class.deliver_email(
            dests=queued_email["dests"] or [],
            sender=queued_email["sender"],
            cc=queued_email["cc"] or [],
            bcc=queued_email["bcc"] or [],
            subject=queued_email["subject"],
            body=queued_email["body"],
            headers=queued_email["headers"] or {},
            attachments=queued_email["attachments"] or [],
        )
    except Exception:
        # Increase the errorCount and bail out
        queued_email["errorCount"] += 1
        db.put(queued_email)
        raise

    # If that transportFunction did not raise an error that email has been successfully send
    queued_email["isSend"] = True
    queued_email["sendDate"] = utils.utcNow()
    queued_email["transportFuncResult"] = result_data
    queued_email.exclude_from_indexes.add("transportFuncResult")

    db.put(queued_email)

    try:
        transport_class.transport_successful_callback(queued_email)
    except Exception as e:
        logging.exception(e)


def normalize_to_list(value: None | t.Any | list[t.Any] | t.Callable[[], list]) -> list[t.Any]:
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


def send_email(
    *,
    tpl: str = None,
    stringTemplate: str = None,
    skel: t.Union[None, dict, "SkeletonInstance", list["SkeletonInstance"]] = None,
    sender: str = None,
    dests: str | list[str] = None,
    cc: str | list[str] = None,
    bcc: str | list[str] = None,
    headers: dict[str, str] = None,
    attachments: list[Attachment] = None,
    context: db.DATASTORE_BASE_TYPES | list[db.DATASTORE_BASE_TYPES] | db.Entity = None,
    **kwargs,
) -> bool:
    """
    General purpose function for sending email.
    This function allows for sending emails, also with generated content using the Jinja2 template engine.
    Your have to implement a method which should be called to send the prepared email finally. For this you have
    to allocate *viur.email.transport_class* in conf.

    :param tpl: The name of a template from the deploy/emails directory.
    :param stringTemplate: This string is interpreted as the template contents. Alternative to load from template file.
        :param skel: The data made available to the template. In case of a Skeleton or SkelList, its parsed the usual way;\
        Dictionaries are passed unchanged.
    :param sender: The address sending this email.
    :param dests: A list of addresses to send this email to. A bare string will be treated as a list with 1 address.
    :param cc: Carbon-copy recipients. A bare string will be treated as a list with 1 address.
    :param bcc: Blind carbon-copy recipients. A bare string will be treated as a list with 1 address.
    :param headers: Specify headers for this email.
    :param attachments:
        List of files to be sent within the email as attachments. Each attachment must be a dictionary with these keys:
            - filename (string): Name of the file that's attached. Always required
            - content (bytes): Content of the attachment as bytes.
            - mimetype (string): Mimetype of the file. Suggested parameter for other implementations (not used by SIB)
            - gcsfile (string): Path to a GCS-File to include instead of content.
            - file_key (string): Key of a FileSkeleton to include instead of content.

    :param context: Arbitrary data that can be stored along the queue entry to be evaluated in
        transport_successful_callback (useful for tracking delivery / opening events etc).

    .. warning::
        As emails will be queued (and not send directly) you cannot exceed 1MB in total
        (for all text and attachments combined)!
    """
    # First, ensure we're able to send email at all
    transport_class = conf.email.transport_class  # First, ensure we're able to send email at all
    if not isinstance(transport_class, EmailTransport):
        raise ValueError(
            f"No or invalid email transport class specified! ({transport_class=}). "
            "In ViUR-core >= 3.7 the transport_class must be an instanced object, so maybe it's "
            f"`conf.email.transport_class = {transport_class.__name__}()` which must be assigned."
        )

    # Ensure that all recipient parameters (dest, cc, bcc) are a list
    dests = normalize_to_list(dests)
    cc = normalize_to_list(cc)
    bcc = normalize_to_list(bcc)

    assert dests or cc or bcc, "No destination address given"
    assert all(isinstance(x, str) and x for x in dests), "Found non-string or empty destination address"
    assert all(isinstance(x, str) and x for x in cc), "Found non-string or empty cc address"
    assert all(isinstance(x, str) and x for x in bcc), "Found non-string or empty bcc address"

    if not (bool(stringTemplate) ^ bool(tpl)):
        raise ValueError("You have to set the params 'tpl' xor a 'stringTemplate'.")

    if attachments := normalize_to_list(attachments):
        # Ensure each attachment has the filename key and rewrite each dict to db.Entity so we can exclude
        # it from being indexed
        for _ in range(0, len(attachments)):
            attachment = attachments.pop(0)
            transport_class.validate_attachment(attachment)

            if "mimetype" not in attachment:
                attachment["mimetype"] = "application/octet-stream"

            entity = db.Entity()
            for k, v in attachment.items():
                entity[k] = v
                entity.exclude_from_indexes.add(k)

            attachments.append(entity)

    # If conf.email.recipient_override is set we'll redirect any email to these address(es)
    if conf.email.recipient_override:
        logging.warning(f"Overriding destination {dests!r} with {conf.email.recipient_override!r}")
        old_dests = dests
        new_dests = normalize_to_list(conf.email.recipient_override)
        dests = []
        for new_dest in new_dests:
            if new_dest.startswith("@"):
                for old_dest in old_dests:
                    dests.append(old_dest.replace(".", "_dot_").replace("@", "_at_") + new_dest)
            else:
                dests.append(new_dest)
        cc = bcc = []

    elif conf.email.recipient_override is False:
        logging.warning("Sending emails disabled by config[viur.email.recipientOverride]")
        return False

    if conf.email.sender_override:
        sender = conf.email.sender_override
    elif sender is None:
        sender = conf.email.sender_default

    subject, body = conf.emailRenderer(dests, tpl, stringTemplate, skel, **kwargs)

    # Push that email to the outgoing queue
    queued_email = db.Entity(db.Key(EMAIL_KINDNAME))

    queued_email["isSend"] = False
    queued_email["errorCount"] = 0
    queued_email["creationDate"] = utils.utcNow()
    queued_email["sender"] = sender
    queued_email["dests"] = dests
    queued_email["cc"] = cc
    queued_email["bcc"] = bcc
    queued_email["subject"] = subject
    queued_email["body"] = body
    queued_email["headers"] = headers
    queued_email["attachments"] = attachments
    queued_email["context"] = context
    queued_email.exclude_from_indexes = {"body", "attachments", "context"}

    transport_class.validate_queue_entity(queued_email)  # Will raise an exception if the entity is not valid

    if conf.instance.is_dev_server:
        if not conf.email.send_from_local_development_server or transport_class is EmailTransportAppengine:
            logging.info("Not sending email from local development server")
            logging.info(f"""Subject: {queued_email["subject"]}""")
            logging.info(f"""Body: {queued_email["body"]}""")
            logging.info(f"""Recipients: {queued_email["dests"]}""")
            return False

    db.put(queued_email)
    send_email_deferred(queued_email.key, _queue=EMAIL_QUEUE)
    return True


@deprecated(version="3.7.0", reason="Use send_email instead")
def sendEMail(*args, **kwargs):
    return send_email(*args, **kwargs)


def send_email_to_admins(subject: str, body: str, *args, **kwargs) -> bool:
    """
    Sends an email to the root users of the current app.

    If :attr:`conf.email.admin_recipients` is set, these recipients
    will be used instead of the root users.

    :param subject: Defines the subject of the message.
    :param body: Defines the message body.
    """
    success = False
    try:
        users = []
        if conf.email.admin_recipients is not None:
            users = normalize_to_list(conf.email.admin_recipients)
        elif "user" in dir(conf.main_app.vi):
            for user_skel in conf.main_app.vi.user.viewSkel().all().filter("access =", "root").fetch():
                users.append(user_skel["name"])

        # Prefix the instance's project_id to subject
        subject = f"{conf.instance.project_id}: {subject}"

        if users:
            ret = send_email(dests=users, stringTemplate=os.linesep.join((subject, body)), *args, **kwargs)
            success = True
            return ret
        else:
            logging.warning("There are no recipients for admin emails available.")

    finally:
        if not success:
            logging.critical("Cannot send email to admins.")
            logging.debug(f"{subject = }, {body = }")

    return False


@deprecated(version="3.7.0", reason="Use send_email_to_admins instead")
def sendEMailToAdmins(*args, **kwargs):
    return send_email_to_admins(*args, **kwargs)


class EmailTransportBrevo(EmailTransport):
    """Send emails with `Brevo`_, formerly Sendinblue.

    .. _Brevo: https://www.brevo.com
    """

    allowed_extensions = {"gif", "png", "bmp", "cgm", "jpg", "jpeg", "tif",
                          "tiff", "rtf", "txt", "css", "shtml", "html", "htm",
                          "csv", "zip", "pdf", "xml", "doc", "docx", "ics",
                          "xls", "xlsx", "ppt", "tar", "ez"}
    """List of allowed file extensions that can be send from Brevo"""

    def __init__(
        self,
        *,
        api_key: str,
        thresholds: tuple[int] | list[int] = (1000, 500, 100),
    ) -> None:
        """
        :param api_key: API key
        :param thresholds: Warning thresholds for remaining email quota.
        """
        super().__init__()
        self.api_key = api_key
        self.thresholds = thresholds

    def deliver_email(
        self,
        *,
        sender: str,
        dests: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        headers: dict[str, str],
        attachments: list[Attachment],
        **kwargs: t.Any,
    ) -> str:
        """
        Internal function for delivering emails using Brevo.
        """
        dataDict = {
            "sender": self.split_address(sender),
            "to": [],
            "htmlContent": body,
            "subject": subject,
        }
        for dest in dests:
            dataDict["to"].append(self.split_address(dest))
        # initialize bcc and cc lists in dataDict
        if bcc:
            dataDict["bcc"] = []
            for dest in bcc:
                dataDict["bcc"].append(self.split_address(dest))
        if cc:
            dataDict["cc"] = []
            for dest in cc:
                dataDict["cc"].append(self.split_address(dest))
        if headers:
            if "Reply-To" in headers:
                dataDict["replyTo"] = self.split_address(headers["Reply-To"])
                del headers["Reply-To"]
            if headers:
                dataDict["headers"] = headers
        if attachments:
            dataDict["attachment"] = []
            for attachment in attachments:
                attachment = self.fetch_attachment(attachment)
                dataDict["attachment"].append({
                    "name": attachment["filename"],
                    "content": base64.b64encode(attachment["content"]).decode("ASCII")
                })
        payload = json.dumps(dataDict).encode("UTF-8")
        headers = {
            "api-key": self.api_key,
            "Content-Type": "application/json; charset=utf-8"
        }
        reqObj = request.Request(url="https://api.brevo.com/v3/smtp/email",
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

    def validate_queue_entity(self, entity: db.Entity) -> None:
        """
        Validate the attachments (if any) against the list of supported file extensions by Brevo.

        :raises ValueError: If the attachment was not allowed

        .. seealso:: :attr:`allowed_extensions`
        """
        for attachment in entity.get("attachments") or []:
            ext = attachment["filename"].split(".")[-1].lower()
            if ext not in self.allowed_extensions:
                raise ValueError(f"The file-extension {ext} cannot be send using Brevo")

    @PeriodicTask(interval=datetime.timedelta(hours=1))
    @staticmethod
    def check_sib_quota() -> None:
        """Periodically checks the remaining Brevo email quota.

        This task does not have to be enabled.
        It automatically checks if the apiKey is configured.

        There are three default thresholds: 1000, 500, 100
        Others can be set via :attr:`thresholds`.
        An email will be sent for the lowest threshold that has been undercut.

        .. seealso:: https://developers.brevo.com/reference/getaccount
        """
        if not isinstance(conf.email.transport_class, EmailTransportSendInBlue):
            return  # no SIB key, we cannot check

        req = requests.get(
            "https://api.brevo.com/v3/account",
            headers={"api-key": conf.email.transport_class.api_key},
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
        logging.info(f"Brevo email credits: {credits}")

        # Keep track of the last credits and the limit for which a email has
        # already been sent. This way, emails for the same limit will not be
        # sent more than once and the remaining email credits will not be wasted.
        key = db.Key("viur-email-conf", "sib-credits")
        if not (entity := db.get(key)):
            logging.debug(f"{entity = }")
            entity = db.Entity(key)
            logging.debug(f"{entity = }")
        logging.debug(f"{entity = }")
        entity.setdefault("latest_warning_for", None)
        entity["credits"] = credits
        entity["email"] = data["email"]

        thresholds = sorted(conf.email.transport_class.thresholds, reverse=True)
        for idx, limit in list(enumerate(thresholds, 1))[::-1]:
            if credits < limit:
                if entity["latest_warning_for"] == limit:
                    logging.info(f"Already send an email for {limit = }.")
                    break

                send_email_to_admins(
                    f"SendInBlue email budget {credits} ({idx}. warning)",
                    f"The SendInBlue email budget reached {credits} credits "
                    f"for {data['email']}. Please increase soon.",
                )
                entity["latest_warning_for"] = limit
                break
        else:
            # Credits are above all limits
            entity["latest_warning_for"] = None

        db.put(entity)


@deprecated(version="3.7.0", reason="Sendinblue is now Brevo; Use EmailTransportBrevo instead")
class EmailTransportSendInBlue(EmailTransportBrevo):
    ...


if mailjet_dependencies:
    class EmailTransportMailjet(EmailTransport):
        """Send emails with `Mailjet`_.

        .. _Mailjet: https://www.mailjet.com/products/email-api/
        """

        def __init__(
            self,
            *,
            api_key: str,
            secret_key: str,
        ) -> None:
            super().__init__()
            self.api_key = api_key
            self.secret_key = secret_key

        def deliver_email(
            self,
            *,
            sender: str,
            dests: list[str],
            cc: list[str],
            bcc: list[str],
            subject: str,
            body: str,
            headers: dict[str, str],
            attachments: list[Attachment],
            **kwargs: t.Any,
        ) -> str:
            if not (self.api_key and self.secret_key):
                raise RuntimeError("Mailjet config invalid, check 'api_key' and 'secret_key'")

            email = {
                "from": self.split_address(sender),
                "htmlpart": body,
                "subject": subject,
                "to": [self.split_address(dest) for dest in dests],
            }

            if bcc:
                email["bcc"] = [self.split_address(b) for b in bcc]

            if cc:
                email["cc"] = [self.split_address(c) for c in cc]

            if headers:
                email["headers"] = headers

            if attachments:
                email["attachments"] = []

                for attachment in attachments:
                    attachment = self.fetch_attachment(attachment)
                    email["attachments"].append({
                        "filename": attachment["filename"],
                        "base64content": base64.b64encode(attachment["content"]).decode("ASCII"),
                        "contenttype": attachment["mimetype"]
                    })

            mj_client = mailjet_rest.Client(
                auth=(self.api_key, self.secret_key),
                version="v3.1",
            )

            result = mj_client.send.create(data={"messages": [email]})
            assert 200 <= result.status_code < 300, f"Received {result.status_code=} {result.reason=}"
            return result.content.decode("UTF-8")


class EmailTransportSendgrid(EmailTransport):
    """Send emails with `SendGrid`_.

    .. _SendGrid: https://sendgrid.com/en-us/solutions/email-api
    """

    def __init__(
        self,
        *,
        api_key: str,
    ) -> None:
        super().__init__()
        self.api_key = api_key

    def deliver_email(
        self,
        *,
        sender: str,
        dests: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        headers: dict[str, str],
        attachments: list[Attachment],
        **kwargs: t.Any,
    ) -> dict[str, str]:
        data = {
            "personalizations": [
                personalization := {
                    "to": [self.split_address(val) for val in dests],
                    "subject": subject,
                }
            ],
            "from": self.split_address(sender),
            "content": [{
                "type": "text/html",
                "value": body,
            }],
            "tracking_settings": {  # TODO: make the settings configurable
                "click_tracking": {
                    "enable": False,
                }
            },
        }

        if cc:
            personalization["cc"] = [self.split_address(val) for val in cc]
        if bcc:
            personalization["bcc"] = [self.split_address(val) for val in bcc]

        if attachments:
            assert isinstance(attachments, list)
            data["attachments"] = [
                {
                    "filename": attachment["filename"],
                    "content": base64.b64encode(attachment["content"]).decode(),
                    "type": attachment["mimetype"],
                    "disposition": "attachment",
                }
                for attachment in map(self.fetch_attachment, attachments)
            ]

        if headers:
            assert isinstance(headers, dict)
            data["headers"] = headers

        req = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json"
            },
            json=data,
        )
        if not req.ok:
            raise ValueError(f"{req.status_code} {req.reason} {req.json()}", req)
        return {k: v for k, v in req.headers.items() if k.startswith("X-")}  # X-Message-Id and maybe more in future


class EmailTransportSmtp(EmailTransport):
    """
    Send emails using the Simple Mail Transfer Protocol (SMTP).

    Needs an email server.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int = smtplib.SMTP_SSL_PORT,
        user: str,
        password: str,
    ) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.context = ssl.create_default_context()

    def deliver_email(
        self,
        *,
        sender: str,
        dests: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        headers: dict[str, str],
        attachments: list[Attachment],
        **kwargs: t.Any,
    ) -> dict[str, tuple[int, bytes]]:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = ", ".join(dests)
        message["Cc"] = ", ".join(cc)
        message["Bcc"] = ", ".join(bcc)
        for key, value in headers.items():
            message.add_header(key, value)

        message.set_content(body, subtype="html")
        message.add_alternative(HtmlSerializer().sanitize(body), subtype="text")

        for attachment in attachments:
            attachment = self.fetch_attachment(attachment)
            part = MIMEBase(*attachment["mimetype"].split("/", 1))
            part.set_payload(attachment["content"])
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{attachment["filename"]}"',
            )
            message.add_alternative(part)

        with smtplib.SMTP_SSL(self.host, self.port, context=self.context) as server:
            server.login(self.user, self.password)
            return server.sendmail(sender, (dests + cc + bcc), message.as_string())


class EmailTransportAppengine(EmailTransport):
    """
    Abstraction of the Google AppEngine Mail API for email transportation.

    .. warning: Works only in a deployed Google Cloud environment.

    .. seealso:: https://cloud.google.com/appengine/docs/standard/python3/services/mail
    """

    def deliver_email(
        self,
        *,
        sender: str,
        dests: list[str],
        cc: list[str],
        bcc: list[str],
        subject: str,
        body: str,
        headers: dict[str, str],
        attachments: list[Attachment],
        **kwargs: t.Any,
    ) -> None:
        # need to build a silly dict because the google.appengine mail api doesn't accept None or empty values ...
        params = {
            "to": [self.split_address(dest)["email"] for dest in dests],
            "sender": sender,
            "subject": subject,
            "body": HtmlSerializer().sanitize(body),
            "html": body,
        }

        if cc:
            params["cc"] = [self.split_address(c)["email"] for c in cc]

        if bcc:
            params["bcc"] = [self.split_address(c)["email"] for c in bcc]

        if attachments:
            params["attachments"] = []

            for attachment in attachments:
                attachment = self.fetch_attachment(attachment)
                params["attachments"].append(
                    GAE_Attachment(attachment["filename"], attachment["content"])
                )

        GAE_SendMail(**params)


# Set (limited, but free) Google AppEngine Mail API as default
if conf.email.transport_class is None:
    conf.email.transport_class = EmailTransportAppengine()
