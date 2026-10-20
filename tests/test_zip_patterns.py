import re

from abstract import ViURTestCase


def zip_code_patterns() -> dict[str, str]:
    # Imported here, not at module level: importing viur.core needs the mocks of ViURTestCase.setUp
    from viur.core.data.zip_patterns import ZIP_CODE_PATTERNS
    return ZIP_CODE_PATTERNS


def literal_dashes_in_classes(pattern: str) -> list[str]:
    """Character classes containing a "-" that is not a range, i.e. a literal dash without escape.

    Browsers compile the HTML `pattern` attribute with the `v` flag, which rejects such a dash
    and then ignores the whole pattern.
    """
    found = []
    for cls in re.findall(r"\[((?:\\.|[^\]\\])*)\]", pattern):
        atoms = re.findall(r"\\.|.", cls)
        i = 0
        while i < len(atoms):
            if atoms[i] == "-":
                # a range needs an atom on both sides that is not itself the end of a range
                if i == 0 or i == len(atoms) - 1 or (i >= 2 and atoms[i - 2] == "-"):
                    found.append(f"[{cls}]")
                    break
            i += 1
    return found


class TestZipCodePatterns(ViURTestCase):

    def test_patterns_compile(self):
        for country, pattern in zip_code_patterns().items():
            with self.subTest(country=country):
                re.compile(pattern)

    def test_no_literal_dash_in_a_character_class(self):
        for country, pattern in zip_code_patterns().items():
            with self.subTest(country=country):
                self.assertEqual([], literal_dashes_in_classes(pattern))

    def test_examples(self):
        for country, zip_code in (("pl", "12-345"), ("pl", "12345"), ("pt", "1234-567"), ("us", "12345-6789"),
                                  ("lt", "LT-12345"), ("ai", "AI-2640"), ("de", "12345")):
            with self.subTest(country=country, zip_code=zip_code):
                self.assertRegex(zip_code, zip_code_patterns()[country])
