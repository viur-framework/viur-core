"""
The `text` module contains the `Textbone` and a custom HTML-Parser
to validate and extract client data for the `TextBone`.
"""
import html
import string
import typing as t
import warnings
from html.parser import HTMLParser
from viur.core import db, conf, i18n, utils
from .base import ReadFromClientError, ReadFromClientErrorSeverity
from .raw import RawBone


class HtmlBoneConfiguration(t.TypedDict):
    """A dictionary containing configurations for handling HTML content in TextBone instances."""

    validTags: list[str]
    """A list of valid HTML tags allowed in TextBone instances."""

    validAttrs: dict[str, list[str]]
    """A dictionary mapping valid attributes for each tag. If a tag is not listed, this tag accepts no attributes."""

    validStyles: list[str]
    """A list of allowed CSS directives for the TextBone instances."""

    validClasses: list[str]
    """A list of valid CSS class names allowed in TextBone instances."""

    singleTags: list[str]
    """A list of self-closing HTML tags that don't have corresponding end tags."""


class CollectBlobKeys(HTMLParser):
    """
    A custom HTML parser that extends the HTMLParser class to collect blob keys found in the "src" attribute
    of <a> and <img> tags.
    """

    def __init__(self):
        super(CollectBlobKeys, self).__init__()
        self.blobs = set()

    def handle_starttag(self, tag, attrs):
        """
        Handles the start tag in the HTML content being parsed. If the tag is an <a> or <img> element, the method
        extracts the blob key from the "src" attribute and adds it to the "blobs" set.

        :param str tag: The current start tag encountered by the parser.
        :param List[Tuple[str, str]] attrs: A list of tuples containing the attribute name and value of the current tag.
        """
        if tag in ["a", "img"]:
            for k, v in attrs:
                if k == "src":
                    file = getattr(conf.main_app.vi, "file", None)
                    if file and (filepath := file.parse_download_url(v)):
                        self.blobs.add(filepath.dlkey)


class HtmlSerializer(HTMLParser):
    """
    A custom HTML parser that extends the HTMLParser class to sanitize and serialize HTML content
    by removing invalid tags and attributes while retaining the valid ones.

    :param dict validHtml: A dictionary containing valid HTML tags, attributes, styles, and classes.
    :param dict srcSet: A dictionary containing width and height for srcset attribute processing.
    """
    __html_serializer_trans = str.maketrans(
        {"<": "&lt;",
         ">": "&gt;",
         "\"": "&quot;",
         "'": "&#39;",
         "\n": "",
         "\0": ""})

    def __init__(self, validHtml: HtmlBoneConfiguration = None, srcSet=None, convert_charrefs: bool = True):
        super().__init__(convert_charrefs=convert_charrefs)
        self.result = ""  # The final result that will be returned
        self.openTagsList = []  # List of tags that still need to be closed
        self.tagCache = []  # Tuple of tags that have been processed but not written yet
        self.validHtml = validHtml
        self.srcSet = srcSet

    def handle_data(self, data):
        """
        Handles the data encountered in the HTML content being parsed. Escapes special characters
        and appends the data to the result if it is not only whitespace characters.

        :param str data: The data encountered by the parser.
        """
        data = str(data).translate(HtmlSerializer.__html_serializer_trans)
        if data.strip():
            self.flushCache()
            self.result += data

    def handle_charref(self, name):
        """
        Handles character references in the HTML content being parsed and appends the character reference to the
        result.

        :param str name: The name of the character reference.
        """
        self.flushCache()
        self.result += f"&#{name};"

    def handle_entityref(self, name):  # FIXME
        """
        Handles entity references in the HTML content being parsed and appends the entity reference to the result.

        :param str name: The name of the entity reference.
        """
        if name in html.entities.entitydefs.keys():
            self.flushCache()
            self.result += f"&{name};"

    def flushCache(self):
        """
        Flush pending tags into the result and push their corresponding end-tags onto the stack
        """
        for start, end in self.tagCache:
            self.result += start
            self.openTagsList.insert(0, end)
        self.tagCache = []

    def handle_starttag(self, tag, attrs):
        """
        Handles start tags in the HTML content being parsed. Filters out invalid tags and attributes and
        processes valid ones.

        :param str tag: The current start tag encountered by the parser.
        :param List[Tuple[str, str]] attrs: A list of tuples containing the attribute name and value of the current tag.
        """
        filterChars = "\"'\\\0\r\n@()"
        if self.validHtml and tag in self.validHtml["validTags"]:
            cacheTagStart = '<' + tag
            isBlankTarget = False
            styles = None
            classes = None
            for k, v in attrs:
                k = k.strip()
                v = v.strip()
                if any([c in k for c in filterChars]) or any([c in v for c in filterChars]):
                    if k in {"title", "href", "alt"} and not any([c in v for c in "\"'\\\0\r\n"]):
                        # If we have a title or href attribute, ignore @ and ()
                        pass
                    else:
                        # Either the key or the value contains a character that's not supposed to be there
                        continue
                elif k == "class":
                    # Classes are handled below
                    classes = v.split(" ")
                    continue
                elif k == "style":
                    # Styles are handled below
                    styles = v.split(";")
                    continue
                elif k == "src":
                    # We ensure that any src tag starts with an actual url
                    checker = v.lower()
                    if not (checker.startswith("http://") or checker.startswith("https://") or checker.startswith("/")):
                        continue

                    file = getattr(conf.main_app.vi, "file", None)
                    if file and (filepath := file.parse_download_url(v)):
                        v = file.create_download_url(
                            filepath.dlkey,
                            filepath.filename,
                            filepath.is_derived,
                            expires=None
                        )

                        if self.srcSet:
                            # Build the src set with files already available. If a derived file is not yet build,
                            # getReferencedBlobs will catch it, build it, and we're going to be re-called afterwards.
                            srcSet = file.create_src_set(
                                filepath.dlkey,
                                None,
                                self.srcSet.get("width"),
                                self.srcSet.get("height")
                            )
                            cacheTagStart += f' srcSet="{srcSet}"'
                if not tag in self.validHtml["validAttrs"].keys() or not k in self.validHtml["validAttrs"][tag]:
                    # That attribute is not valid on this tag
                    continue
                if k.lower()[0:2] != 'on' and v.lower()[0:10] != 'javascript':
                    cacheTagStart += f' {k}="{v}"'
                if tag == "a" and k == "target" and v.lower() == "_blank":
                    isBlankTarget = True
            if styles:
                syleRes = {}
                for s in styles:
                    style = s[: s.find(":")].strip()
                    value = s[s.find(":") + 1:].strip()
                    if any([c in style for c in filterChars]) or any(
                           [c in value for c in filterChars]):
                        # Either the key or the value contains a character that's not supposed to be there
                        continue
                    if value.lower().startswith("expression") or value.lower().startswith("import"):
                        # IE evaluates JS inside styles if the keyword expression is present
                        continue
                    if style in self.validHtml["validStyles"] and not any(
                           [(x in value) for x in ["\"", ":", ";"]]):
                        syleRes[style] = value
                if len(syleRes.keys()):
                    cacheTagStart += f""" style=\"{"; ".join([(f"{k}: {v}") for k, v in syleRes.items()])}\""""
            if classes:
                validClasses = []
                for currentClass in classes:
                    validClassChars = string.ascii_lowercase + string.ascii_uppercase + string.digits + "-"
                    if not all([x in validClassChars for x in currentClass]):
                        # The class contains invalid characters
                        continue
                    isOkay = False
                    for validClass in self.validHtml["validClasses"]:
                        # Check if the classname matches or is white-listed by a prefix
                        if validClass == currentClass:
                            isOkay = True
                            break
                        if validClass.endswith("*"):
                            validClass = validClass[:-1]
                            if currentClass.startswith(validClass):
                                isOkay = True
                                break
                    if isOkay:
                        validClasses.append(currentClass)
                if validClasses:
                    cacheTagStart += f""" class=\"{" ".join(validClasses)}\""""
            if isBlankTarget:
                # Add rel tag to prevent the browser to pass window.opener around
                cacheTagStart += " rel=\"noopener noreferrer\""
            if tag in self.validHtml["singleTags"]:
                # Single-Tags do have a visual representation; ensure it makes it into the result
                self.flushCache()
                self.result += cacheTagStart + '>'  # dont need slash in void elements in html5
            else:
                # We opened a 'normal' tag; push it on the cache so it can be discarded later if
                # we detect it has no content
                cacheTagStart += '>'
                self.tagCache.append((cacheTagStart, tag))
        else:
            self.result += " "

    def handle_endtag(self, tag):
        """
        Handles end tags in the HTML content being parsed. Closes open tags and discards invalid ones.

        :param str tag: The current end tag encountered by the parser.
        """
        if self.validHtml:
            if self.tagCache:
                # Check if that element is still on the cache
                # and just silently drop the cache up to that point
                if tag in [x[1] for x in self.tagCache] + self.openTagsList:
                    for tagCache in self.tagCache[::-1]:
                        self.tagCache.remove(tagCache)
                        if tagCache[1] == tag:
                            return
            if tag in self.openTagsList:
                # Close all currently open Tags until we reach the current one. If no one is found,
                # we just close everything and ignore the tag that should have been closed
                for endTag in self.openTagsList[:]:
                    self.result += f"</{endTag}>"
                    self.openTagsList.remove(endTag)
                    if endTag == tag:
                        break

    def cleanup(self):  # FIXME: vertauschte tags
        """ Append missing closing tags to the result."""
        self.flushCache()
        for tag in self.openTagsList:
            endTag = f'</{tag}>'
            self.result += endTag

    def sanitize(self, instr):
        """
        Sanitizes the input HTML string by removing invalid tags and attributes while retaining valid ones.

        :param str instr: The input HTML string to be sanitized.
        :return: The sanitized HTML string.
        :rtype: str
        """
        self.result = ""
        self.openTagsList = []
        self.feed(instr)
        self.close()
        self.cleanup()
        return self.result


class TextBone(RawBone):
    """
    A bone for storing and validating HTML or plain text content. Can be configured to allow
    only specific HTML tags and attributes, and enforce a maximum length. Supports the use of
    srcset for embedded images.

    :param validHtml: A dictionary containing allowed HTML tags and their attributes.
        Defaults to `conf.bone_html_default_allow`.
    :param max_length: The maximum allowed length for the content. Defaults to 200000.
    :param languages: If set, this bone can store a different content for each language
    :param srcSet: An optional dictionary containing width and height for srcset generation.
        Must be a dict of "width": [List of Ints], "height": [List of Ints], eg {"height": [720, 1080]}
    :param indexed: Whether the content should be indexed for searching. Defaults to False.
    :param escape_html: If set to False, the content is stored as-is, without any sanitizing.
        Only allowed together with `validHtml=None`.
    :param kwargs: Additional keyword arguments to be passed to the base class constructor.

    ..Warning: Setting `escape_html=False` disables any server-side sanitizing and therefore leads to
        security vulnerabilities like reflected XSS unless the content is either otherwise
        validated/stripped or comes from a trusted source. Additionally, the bone stops tracking
        referenced files, so blobs linked from within the content are no longer protected from
        being deleted.
    """

    class __undefinedC__:
        pass

    type = "text"

    def __init__(
        self,
        *,
        validHtml: None | HtmlBoneConfiguration = __undefinedC__,
        max_length: int = 200000,
        srcSet: t.Optional[dict[str, list]] = None,
        indexed: bool = False,
        escape_html: bool = True,
        **kwargs
    ):
        """
            :param validHtml: If set, must be a structure like `conf.bone_html_default_allow`
            :param languages: If set, this bone can store a different content for each language
            :param max_length: Limit content to max_length bytes
            :param indexed: Must not be set True, unless you limit max_length accordingly
            :param srcSet: If set, inject srcset tags to embedded images. Must be a dict of
                "width": [List of Ints], "height": [List of Ints], eg {"height": [720, 1080]}
            :param escape_html: If set to False, the content is stored without any sanitizing;
                neither tags are filtered nor special characters are escaped, and line breaks are
                kept. Requires `validHtml=None`.
        """
        # fixme: Remove in viur-core >= 4
        if "maxLength" in kwargs:
            warnings.warn("maxLength parameter is deprecated, please use max_length", DeprecationWarning)
            max_length = kwargs.pop("maxLength")
        super().__init__(indexed=indexed, **kwargs)

        if validHtml == TextBone.__undefinedC__:
            validHtml = conf.bone_html_default_allow

        if not escape_html and validHtml is not None:
            raise ValueError("escape_html=False is only allowed with validHtml=None")

        self.validHtml = validHtml
        self.max_length = max_length
        self.srcSet = srcSet
        self.escape_html = escape_html

    def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        """
        Serializes a single value of the TextBone instance for storage.

        This method takes the value as-is without any additional processing, since it's already stored in a format
        suitable for serialization.
        """
        return value

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        if err := self.isInvalid(value):  # Returns None on success, error-str otherwise
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

        if not self.escape_html:
            return value, None

        return HtmlSerializer(self.validHtml, self.srcSet, False).sanitize(value), None

    def getEmptyValue(self):
        """
        Returns an empty value for the TextBone instance.

        This method is used to represent an empty or unset value for the TextBone.

        return: An empty string.
        :rtype: str
        """
        return ""

    def isInvalid(self, value):
        """
        Checks if the given value is valid for this TextBone instance.

        This method checks whether the given value is valid according to the TextBone's constraints (e.g., not
        None and within the maximum length).

        :param value: The value to be checked for validity.
        :return: Returns None if the value is valid, or an error message string otherwise.
        :rtype: Optional[str]
        """

        if value is None:
            return i18n.translate("core.bones.error.novalueentered", "No value entered")
        if len(value) > self.max_length:
            return i18n.translate("core.bones.error.maximumlengthexceeded", "Maximum length exceeded")

    def getReferencedBlobs(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> set[str]:
        """
        Extracts and returns the blob keys of referenced files in the HTML content of the TextBone instance.

        This method parses the HTML content of the TextBone to identify embedded images or file hrefs,
        collects their blob keys, and ensures that they are not deleted even if removed from the file browser,
        preventing broken links or images in the TextBone content.

        :param SkeletonInstance skel: A SkeletonInstance object containing the data of an entry.
        :param str name: The name of the TextBone for which to find referenced blobs.
        :return: A set containing the blob keys of the referenced files in the TextBone's HTML content.
            Always empty when `escape_html` is disabled, as the content is then not treated as HTML.
        :rtype: Set[str]
        """
        if not self.escape_html:
            return set()

        collector = CollectBlobKeys()

        for idx, lang, value in self.iter_bone_value(skel, name):
            if value:
                collector.feed(value)

        blob_keys = collector.blobs

        if blob_keys and self.srcSet:
            derive_dict = {
                "thumbnail": [
                                 {"width": x} for x in (self.srcSet.get("width") or [])
                             ] + [
                                 {"height": x} for x in (self.srcSet.get("height") or [])
                             ]
            }
            from viur.core.bones.file import ensureDerived
            for blob_key in blob_keys:
                file_obj = db.Query("file").filter("dlkey =", blob_key) \
                    .order(db.QueryOrder("creationdate")).getEntry()
                if file_obj:
                    ensureDerived(file_obj.key, f"{skel.kindName}_{name}", derive_dict, skel["key"])

        return blob_keys

    def refresh(self, skel, boneName) -> None:
        """
        Re-parses the text content of the TextBone instance to rebuild the src-set if necessary.

        This method is useful when the src-set configuration has changed and needs to be applied
        to the existing HTML content. It re-parses the content and updates the src-set attributes
        accordingly.

        When `escape_html` is disabled, the content is unescaped instead, to revert values that
        have been escaped by a previous configuration of this bone. Note that line breaks removed
        by the former sanitizing cannot be restored.

        :param SkeletonInstance skel: A SkeletonInstance object containing the data of an entry.
        :param str boneName: The name of the TextBone for which to refresh the src-set.
        """
        if not self.escape_html:
            # TODO: duplicate code, this is the same iteration logic as in StringBone
            new_value = {}
            for _, lang, value in self.iter_bone_value(skel, boneName):
                if value is not None:
                    value = utils.string.unescape(value)
                new_value.setdefault(lang, []).append(value)

            if not self.multiple:
                # take the first one
                new_value = {lang: values[0] for lang, values in new_value.items() if values}

            if self.languages:
                skel[boneName] = new_value
            else:
                # just the value(s) with None language
                skel[boneName] = new_value.get(None, [] if self.multiple else self.getEmptyValue())

            return

        if self.srcSet:
            val = skel[boneName]
            if self.languages and isinstance(val, dict):
                skel[boneName] = {k: self.singleValueFromClient(v, skel, boneName, None)[0] for k, v in val.items()}
            elif not self.languages and isinstance(val, str):
                skel[boneName] = self.singleValueFromClient(val, skel, boneName, None)[0]

    def structure(self) -> dict:
        return super().structure() | {
            "valid_html": self.validHtml,
            "escape_html": self.escape_html,
        }
