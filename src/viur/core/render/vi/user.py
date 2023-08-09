from viur.core.render.json.user import UserRender as user
import string, json


class UserRender(user):
    kind = "json.vi"

    def loginSucceeded(self, **kwargs):
        """
        This loginSuccess method generates a HTML site, which redirects by meta-refresh to the Vi,
        but can also be easily read by Ajax requests.
        """
        msg = "".join([x for x in kwargs.get("msg", "OKAY") if x in string.digits + string.ascii_letters + "-"])

        return """
        <html>
            <head>
                <meta http-equiv="refresh" content="0; URL=/vi/s/main.html">
            </head>
            <body style="text-align: center;">
                You will be redirected to <a href="/vi/s/main.html">/vi/s/main.html</a> in a short moment...
                <div style="display: none;" id="msg">JSON((%s))</div>
            </body>
        </html>
        """ % json.dumps(msg)
