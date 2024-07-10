import random, logging
from viur.core import utils, i18n, current
from viur.core.bones import NumericBone


class SpamBone(NumericBone):

    def __init__(self, required=True, precision=0, *args, **kwargs):
        super().__init__(required=required, precision=0, *args, **kwargs)
        self.defaultNumbers = ["eins", "zwei", "drei", "vier", "fÃ¼nf", "sechs", "sieben", "acht", "neun"]

    def _getRandomNumber(self):
        num = 0
        while num == 0:
            num = int(random.random() * 10)

        return num

    @property
    def descr(self):
        session = current.session.get()
        a = session.get("spamBone.a")
        b = session.get("spamBone.b")

        if a is None or b is None:
            a = session["spamBone.a"] = self._getRandomNumber()
            b = session["spamBone.b"] = self._getRandomNumber()
            session.markChanged()

        return i18n.translate(
            "spambone.confirm",
            "<strong>SPAM * - Addiere {{a}} plus {{b}}. Antwort als Ziffer.</strong>"
        ).translate(
            a=i18n.translate("spambone.%d" % a, self.defaultNumbers[a - 1]).translate(),
            b=i18n.translate("spambone.%d" % b, self.defaultNumbers[b - 1]).translate()
        )

    @descr.setter
    def descr(self, value):
        pass

    def isInvalid(self, value):
        session = current.session.get()

        a = session.get("spamBone.a") or 0
        b = session.get("spamBone.b") or 0

        if a and b:
            del session["spamBone.a"]
            del session["spamBone.b"]
            session.markChanged()

            try:
                value = int(value)
            except:
                return False

        logging.debug("a=%r, b=%r, value=%r, expecting=%r", a, b, value, a+b)
        if value != a + b:
            return i18n.translate("spambone.invalid", "Deine Antwort war falsch. Bitte versuche es erneut.").translate()
