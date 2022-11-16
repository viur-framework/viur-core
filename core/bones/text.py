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


def parseDownloadUrl(urlStr: str) -> Tuple[Optional[str], Optional[bool], Optional[str]]:
    """
        Parses a file download-url (/file/download/xxxx?sig=yyyy) into it's components
        blobKey, derived (yes/no) and filename. Will return None for each component if the url
        could not be parsed.
    """
    if not urlStr.startswith("/file/download/"):
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
    def __init__(self):
        super(CollectBlobKeys, self).__init__()
        self.blobs = set()

    def handle_starttag(self, tag, attrs):
        if tag in ["a", "img"]:
            for k, v in attrs:
                if k == "src":
                    blobKey, _, _ = parseDownloadUrl(v)
                    if blobKey:
                        self.blobs.add(blobKey)


class HtmlSerializer(HTMLParser):  # html.parser.HTMLParser
    def __init__(self, validHtml=None, srcSet=None):
        global _defaultTags
        super(HtmlSerializer, self).__init__()
        self.result = ""  # The final result that will be returned
        self.openTagsList = []  # List of tags that still need to be closed
        self.tagCache = []  # Tuple of tags that have been processed but not written yet
        self.validHtml = validHtml
        self.srcSet = srcSet

    def handle_data(self, data):
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
        self.flushCache()
        self.result += "&#%s;" % (name)

    def handle_entityref(self, name):  # FIXME
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
        """ Delete all tags except for legal ones """
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
        """ Append missing closing tags """
        self.flushCache()
        for tag in self.openTagsList:
            endTag = '</%s>' % tag
            self.result += endTag

    def sanitize(self, instr):
        self.result = ""
        self.openTagsList = []
        self.feed(instr)
        self.close()
        self.cleanup()
        return self.result


class TextBone(BaseBone):
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
        return value

    def singleValueFromClient(self, value, skel, name, origData):
        err = self.isInvalid(value)  # Returns None on success, error-str otherwise
        if not err:
            return HtmlSerializer(self.validHtml, self.srcSet).sanitize(value), None
        else:
            return self.getEmptyValue(), [ReadFromClientError(ReadFromClientErrorSeverity.Invalid, err)]

    def getEmptyValue(self):
        return ""

    def isInvalid(self, value):
        """
            Returns None if the value would be valid for
            this bone, an error-message otherwise.
        """
        if value == None:
            return "No value entered"
        if len(value) > self.maxLength:
            return "Maximum length exceeded"

    def getReferencedBlobs(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> Set[str]:
        """
            Parse our html for embedded img or hrefs pointing to files. These will be locked,
            so even if they are deleted from the file browser, we'll still keep that blob alive
            so we don't have broken links/images in this bone.
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
            Re-parse our text. This will cause our src-set to rebuild.
        """
        if self.srcSet:
            val = skel[boneName]
            if self.languages and isinstance(val, dict):
                skel[boneName] = {k: self.singleValueFromClient(v, skel, boneName, None)[0] for k, v in val.items()}
            elif not self.languages and isinstance(val, str):
                skel[boneName] = self.singleValueFromClient(val, skel, boneName, None)[0]

    def getSearchTags(self, skel: 'viur.core.skeleton.SkeletonInstance', name: str) -> Set[str]:
        result = set()
        for idx, lang, value in self.iter_bone_value(skel, name):
            if value is None:
                continue
            for line in str(value).splitlines():
                for word in line.split(" "):
                    result.add(word.lower())
        return result

    def getUniquePropertyIndexValues(self, valuesCache: dict, name: str) -> List[str]:
        if self.languages:
            # Not yet implemented as it's unclear if we should keep each language distinct or not
            raise NotImplementedError()

        return super().getUniquePropertyIndexValues(valuesCache, name)
