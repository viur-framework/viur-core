import ast
import jinja2
import logics
from viur.core.bones.raw import RawBone


class CodeBone(RawBone):
    """
    Stores source code with optional language-specific syntax validation.

    The ``syntax`` parameter sets the type suffix used by the frontend for syntax
    highlighting, e.g. ``syntax="python"`` yields ``type = "raw.code.python"``.
    ``type_suffix`` can override this to an arbitrary suffix.

    Neither ``multiple`` nor ``languages`` are supported.
    Setting ``validate=False`` disables any syntax validation in subclasses.
    """

    type = "raw.code"

    def __init__(
        self,
        *,
        indexed: bool = False,
        languages=None,
        multiple: bool = False,
        syntax: str | None = None,
        type_suffix: str = "",
        validate: bool = True,
        **kwargs,
    ):
        assert not multiple, "CodeBone does not support multiple values"
        assert not languages, "CodeBone does not support language variants"
        self.syntax = syntax
        self.validate = validate
        if self.syntax:
            type_suffix = type_suffix or syntax
        super().__init__(indexed=indexed, type_suffix=type_suffix, **kwargs)


class LogicsBone(CodeBone):
    """
    Validates its value as a Logics expression (https://github.com/viur-framework/logics).
    Uses Python syntax highlighting in the frontend.
    """

    def __init__(self, *, syntax: str = "logics", **kwargs):
        super().__init__(syntax=syntax, type_suffix="python", **kwargs)

    def singleValueFromClient(self, value, skel, bone_name, client_data):
        if value := str(value or "").strip():
            value += "\n"
        return super().singleValueFromClient(value, skel, bone_name, client_data)

    def isInvalid(self, value):
        if self.validate and value:
            try:
                logics.Logics(value)
            except logics.ParseException as e:
                return str(e).replace("&eof", "end-of-expression")


class JinjaBone(CodeBone):
    """
    Validates its value as a Jinja2 template.
    """

    def __init__(self, *, syntax: str = "jinja2", **kwargs):
        super().__init__(syntax=syntax, **kwargs)

    def isInvalid(self, value):
        if self.validate and value:
            env = jinja2.Environment()
            try:
                env.parse(value)
            except jinja2.TemplateSyntaxError as e:
                return f"Syntax error in line {e.lineno}: {e.message}"
            except jinja2.TemplateError as e:
                return f"General error: {e}"


class PythonBone(CodeBone):
    """
    Validates its value as Python source code.
    """

    def __init__(self, *, syntax: str = "python", **kwargs):
        super().__init__(syntax=syntax, **kwargs)

    def isInvalid(self, value):
        if self.validate and value:
            try:
                ast.parse(value)
            except SyntaxError as e:
                return f"Syntax error in line {e.lineno}: {e.msg}"
