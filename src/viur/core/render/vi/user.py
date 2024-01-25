from viur.core import current
from viur.core.render.json.user import UserRender as user
import string, json


class UserRender(user):
    kind = "json.vi"

    def loginSucceeded(self, **kwargs):
        """
        This loginSuccess method generates a HTML site, which redirects by meta-refresh to the Vi,
        but can also be easily read by Ajax requests.
        """
        if current.request.get().context.get("vi-admin"):
            return json.dumps(kwargs.get("msg", "OKAY"))
        msg = "".join([x for x in kwargs.get("msg", "OKAY") if x in string.digits + string.ascii_letters + "-"])

        return f"""
        <html>
            <head>
                <meta http-equiv="refresh" content="0; URL=/vi/s/main.html">
            </head>
            <body style="text-align: center;">
                You will be redirected to <a href="/vi/s/main.html">/vi/s/main.html</a> in a short moment...
                <div style="display: none;" id="msg">JSON(({json.dumps(msg)}))</div>
            </body>
        </html>
        """
