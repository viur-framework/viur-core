import typing as t
from .file import FileBone
from .string import StringBone
from ..skeleton import RelSkel
from ..config import conf


class ImageBoneRelSkel(RelSkel):
    alt = StringBone(
        descr="Alternativ-Text",
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
