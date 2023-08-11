"""
The `text` module contains the `Textbone` and a custom HTML-Parser
to validate and extract client data for the `TextBone`.
"""
import string
from base64 import urlsafe_b64decode
from datetime import datetime
from html import entities as htmlentitydefs
from html.parser import HTMLParser
from typing import Dict, List, Optional, Set, Tuple, Union

from viur.core import db, utils
from viur.core.bones.base import BaseBone, ReadFromClientError, ReadFromClientErrorSeverity

_defaultTags = {
    "validTags": [  # List of HTML-Tags which are valid
        'b', 'a', 'i', 'u', 'span', 'div', 'p', 'img', 'ol', 'ul', 'li', 'abbr', 'sub', 'sup',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'br',
        'hr', 'strong', 'blockquote', 'em'],
    "validAttrs": {  # Mapping of valid parameters for each tag (if a tag is not listed here: no parameters allowed)
        "a": ["href", "target", "title"],
        "abbr": ["title"],
        "span": ["title"],
        "img": ["src", "alt", "title"],  # "srcset" must not be in this list. It will be injected by ViUR
        "td": ["colspan", "rowspan"],
        "p": ["data-indent"],
        "blockquote": ["cite"]
    },
    "validStyles": [
        "color"
    ],  # List of CSS-Directives we allow
    "validClasses": ["vitxt-*", "viur-txt-*"],  # List of valid class-names that are valid
    "singleTags": ["br", "img", "hr"]  # List of tags, which don't have a corresponding end tag
}
"""
A dictionary containing default configurations for handling HTML content in TextBone instances.

- validTags (list[str]):
    A list of valid HTML tags allowed in TextBone instances.
- validAttrs (dict[str, list[str]]):
    A dictionary mapping valid attributes for each tag. If a tag is not listed, no attributes are allowed for that tag.
- validStyles (list[str]):
   A list of allowed CSS directives for the TextBone instances.
- validClasses (list[str]):
    A list of valid CSS class names allowed in TextBone instances.
- singleTags (list[str]):
   A list of self-closing HTML tags that don't have corresponding end tags.
"""


def parseDownloadUrl(urlStr: str) -> Tuple[Optional[str], Optional[bool], Optional[str]]:
    """
    Parses a file download URL in the format `/file/download/xxxx?sig=yyyy` into its components: blobKey, derived,
    and filename. If the URL cannot be parsed, the function returns None for each component.

    :param str urlStr: The file download URL to be parsed.
    :return: A tuple containing the parsed components: (blobKey, derived, filename).
            Each component will be None if the URL could not be parsed.
    :rtype: Tuple[Optional[str], Optional[bool], Optional[str]]
    """
    if not urlStr.startswith("/file/download/") or "?" not in urlStr:
        return None, None, None
    dataStr, sig = urlStr[15:].split("?")  # Strip /file/download/ and split on ?
    sig = sig[4:]  # Strip sig=
    if not utils.hmacVerify(dataStr.encode("ASCII"), sig):
        # Invalid signature, bail out
        return None, None, None
    # Split the blobKey into the individual fields it should contain
    try:
        dlPath, validUntil, _ = urlsafe_b64decode(dataStr).decode("UTF-8").split("\0")
    except:  # It's the old format, without an downloadFileName
        dlPath, validUntil = urlsafe_b64decode(dataStr).decode("UTF-8").split("\0")
    if validUntil != "0" and datetime.strptime(validUntil, "%Y%m%d%H%M") < datetime.now():
        # Signature expired, bail out
        return None, None, None
    blobkey, derived, fileName = dlPath.split("/")
    derived = derived != "source"
    return blobkey, derived, fileName


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
                    blobKey, _, _ = parseDownloadUrl(v)
                    if blobKey:
                        self.blobs.add(blobKey)


class HtmlSerializer(HTMLParser):  # html.parser.HTMLParser
    """
    A custom HTML parser that extends the HTMLParser class to sanitize and serialize HTML content
    by removing invalid tags and attributes while retaining the valid ones.

    :param dict validHtml: A dictionary containing valid HTML tags, attributes, styles, and classes.
    :param dict srcSet: A dictionary containing width and height for srcset attribute processing.
    """

    def __init__(self, validHtml=None, srcSet=None):
        global _defaultTags
        super(HtmlSerializer, self).__init__()
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
        data = str(data) \
            .replace("<", "&lt;") \
            .replace(">", "&gt;") \
            .replace("\"", "&quot;") \
            .replace("'", "&#39;") \
            .replace("\0", "")
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
        self.result += "&#%s;" % (name)

    def handle_entityref(self, name):  # FIXME
        """
        Handles entity references in the HTML content being parsed and appends the entity reference to the result.

        :param str name: The name of the entity reference.
        """
        if name in htmlentitydefs.entitydefs.keys():
            self.flushCache()
            self.result += "&%s;" % (name)

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
                    blobKey, derived, fileName = parseDownloadUrl(v)
                    if blobKey:
                        v = utils.downloadUrlFor(blobKey, fileName, derived, expires=None)
                        if self.srcSet:
                            # Build the src set with files already available. If a derived file is not yet build,
                            # getReferencedBlobs will catch it, build it, and we're going to be re-called afterwards.
                            fileObj = db.Query("file").filter("dlkey =", blobKey) \
                                .order(("creationdate", db.SortOrder.Ascending)).getEntry()
                            srcSet = utils.srcSetFor(fileObj, None, self.srcSet.get("width"), self.srcSet.get("height"))
                            cacheTagStart += ' srcSet="%s"' % srcSet
                if not tag in self.validHtml["validAttrs"].keys() or not k in self.validHtml["validAttrs"][tag]:
                    # That attribute is not valid on this tag
                    continue
                if k.lower()[0:2] != 'on' and v.lower()[0:10] != 'javascript':
                    cacheTagStart += ' %s="%s"' % (k, v)
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
                    cacheTagStart += " style=\"%s\"" % "; ".join(
                        [("%s: %s" % (k, v)) for (k, v) in syleRes.items()])
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
                    cacheTagStart += " class=\"%s\"" % " ".join(validClasses)
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
                    self.result += "</%s>" % endTag
                    self.openTagsList.remove(endTag)
                    if endTag == tag:
                        break

    def cleanup(self):  # FIXME: vertauschte tags
        """ Append missing closing tags to the result."""
        self.flushCache()
        for tag in self.openTagsList:
            endTag = '</%s>' % tag
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


class TextBone(BaseBone):
    """
    A bone for storing and validating HTML or plain text content. Can be configured to allow
    only specific HTML tags and attributes, and enforce a maximum length. Supports the use of
    srcset for embedded images.

    :param Union[None, Dict] validHtml: A dictionary containing allowed HTML tags and their attributes. Defaults
        to _defaultTags. Must be a structured like :prop:_defaultTags
    :param int maxLength: The maximum allowed length for the content. Defaults to 200000.
    :param languages: If set, this bone can store a different content for each language
    :param Dict[str, List] srcSet: An optional dictionary containing width and height for srcset generation.
        Must be a dict of "width": [List of Ints], "height": [List of Ints], eg {"height": [720, 1080]}
    :param bool indexed: Whether the content should be indexed for searching. Defaults to False.
    :param kwargs: Additional keyword arguments to be passed to the base class constructor.
    """

    class __undefinedC__:
        pass

    type = "text"

    def __init__(
        self,
        *,
        validHtml: Union[None, Dict] = __undefinedC__,
        maxLength: int = 200000,
        srcSet: Optional[Dict[str, List]] = None,
        indexed: bool = False,
        **kwargs
    ):
        """
            :param validHtml: If set, must be a structure like :prop:_defaultTags
            :param languages: If set, this bone can store a different content for each language
            :param maxLength: Limit content to maxLength bytes
            :param indexed: Must not be set True, unless you limit maxLength accordingly
            :param srcSet: If set, inject srcset tags to embedded images. Must be a dict of
                "width": [List of Ints], "height": [List of Ints], eg {"height": [720, 1080]}
        """
        super().__init__(indexed=indexed, **kwargs)

        if validHtml == TextBone.__undefinedC__:
            global _defaultTags
            validHtml = _defaultTags

        self.validHtml = validHtml
        self.maxLength = maxLength
        self.srcSet = srcSet

    def singleValueSerialize(self, value, skel: 'SkeletonInstance', name: str, parentIndexed: bool):
        """
        Serializes a single value of the TextBone instance for storage.

        This method takes the value as-is without any additional processing, since it's already stored in a format
        suitable for serialization.
        """
        return value

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        if not (err := self.isInvalid(value)):  # Returns None on success, error-str otherwise
            return HtmlSerializer(self.validHtml, self.srcSet).sanitize(value), None
        else:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

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

        if value == None:
            return "No value entered"
        if len(value) > self.maxLength:
            return "Maximum length exceeded"

    def getReferencedBlobs(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> Set[str]:
        """
        Extracts and returns the blob keys of referenced files in the HTML content of the TextBone instance.

        This method parses the HTML content of the TextBone to identify embedded images or file hrefs,
        collects their blob keys, and ensures that they are not deleted even if removed from the file browser,
        preventing broken links or images in the TextBone content.

        :param SkeletonInstance skel: A SkeletonInstance object containing the data of an entry.
        :param str name: The name of the TextBone for which to find referenced blobs.
        :return: A set containing the blob keys of the referenced files in the TextBone's HTML content.
        :rtype: Set[str]
        """

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
                    .order(("creationdate", db.SortOrder.Ascending)).getEntry()
                if file_obj:
                    ensureDerived(file_obj.key, "%s_%s" % (skel.kindName, name), derive_dict, skel["key"])

        return blob_keys

    def refresh(self, skel, boneName) -> None:
        """
        Re-parses the text content of the TextBone instance to rebuild the src-set if necessary.

        This method is useful when the src-set configuration has changed and needs to be applied
        to the existing HTML content. It re-parses the content and updates the src-set attributes
        accordingly.

        :param SkeletonInstance skel: A SkeletonInstance object containing the data of an entry.
        :param str boneName: The name of the TextBone for which to refresh the src-set.
        """
        if self.srcSet:
            val = skel[boneName]
            if self.languages and isinstance(val, dict):
                skel[boneName] = {k: self.singleValueFromClient(v, skel, boneName, None)[0] for k, v in val.items()}
            elif not self.languages and isinstance(val, str):
                skel[boneName] = self.singleValueFromClient(val, skel, boneName, None)[0]

    def getSearchTags(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> Set[str]:
        """
        Extracts search tags from the text content of a TextBone.

        This method iterates over the values of the TextBone in the given skeleton, and for each non-empty value,
        it tokenizes the text by lines and words. Then, it adds the lowercase version of each word to a set of
        search tags, which is returned at the end.

        :param skel: A SkeletonInstance containing the TextBone.
        :param name: The name of the TextBone in the skeleton.
        :return: A set of unique search tags (lowercase words) extracted from the text content of the TextBone.
        """
        result = set()
        for idx, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue
            for line in str(value).splitlines():
                for word in line.split(" "):
                    result.add(word.lower())
        return result

    def getUniquePropertyIndexValues(self, valuesCache: dict, name: str) -> List[str]:
        """
        Retrieves the unique property index values for the TextBone.

        If the TextBone supports multiple languages, this method raises a NotImplementedError, as it's unclear
        whether each language should be kept distinct or not. Otherwise, it calls the superclass's
        getUniquePropertyIndexValues method to retrieve the unique property index values.

        :param valuesCache: A dictionary containing the cached values for the TextBone.
        :param name: The name of the TextBone.
        :return: A list of unique property index values for the TextBone.
        :raises NotImplementedError: If the TextBone supports multiple languages.
        """
        if self.languages:
            # Not yet implemented as it's unclear if we should keep each language distinct or not
            raise NotImplementedError()

        return super().getUniquePropertyIndexValues(valuesCache, name)

    def structure(self) -> dict:
        return super().structure() | {
            "valid_html": self.validHtml,
        }
