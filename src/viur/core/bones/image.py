import typing as t
from .. import i18n
from .file import FileBone
from .string import StringBone
from ..skeleton.relskel import RelSkel
from ..config import conf


class ImageBoneRelSkel(RelSkel):
    alt = StringBone(
        descr=i18n.translate(
            "viur.core.image.alt",
            defaultText="Alternative description",
        ),
        searchable=True,
        languages=conf.i18n.available_languages,
    )


class ImageBone(FileBone):
    type = FileBone.type + ".image"

    def __init__(
        self,
        *,
        public: bool = True,
        using: t.Optional[RelSkel] = ImageBoneRelSkel,
        validMimeTypes: None | t.Iterable[str] = ["image/*"],
        **kwargs,
    ):
        super().__init__(
            public=public,
            using=using,
            validMimeTypes=validMimeTypes,
            **kwargs,
        )
