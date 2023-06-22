ViUR and Google Auth
####################

This changes took effect on ViUR 3.3.5 if you are Using a Version prior to this one, you will need to handle it otherwise.

1. Open the Google Cloud Console website as an Admin User
2. Open the `API & Services OAuth conset screen <https://console.cloud.google.com/apis/credentials/consent>`_ Menu
3. Declare your User Type and Click the "Create" Button
4. Fill in the App Information "Save and Continue"
5. Click the Buttton "Add or Remove Scopes" and choose the folllowing Scopes
    (a) *../auth/userinfo.mail*
    (b) *../auth/userinfo.profile*
    (c) *openid*

.. Note::
    Those Scopes are the Generall Scopes to get User Information

6. Save and Continue
7. Navigate to `API & Services Credentials <https://console.cloud.google.com/apis/credentials>`_
8. Press the Button "+ Create Credentials"
9. Select "OAuth client ID"
10. Enter your application Type as "Web Application"
11. Enter a Name for your OAuth 2.0 Client
12. Click the "Add URI" button, under the "Authorized Javascript origins" headline
13. Enter your Rediect URL's

    | For deployed Software we recommend: "https://projectname.appspot.com"
    | If you want to use the Google LogIn in your development System you will also need to add:
    | "http://localhost:8080"
    | "http://localhost"

14. Click the "Create" buttton
15. Copy the Client ID of the Succes Message to your Clipboard
16. Open the main.py of your ViUR project and add the config variable and the id

#.. code-block:: python
#    # Insert your ClientID as String
#    conf["viur.user.google.clientID"] = " "
#    # If you are a gsuitecustomer, you can whitelist mails form certain Domains
#    conf["viur.user.google.gsuiteDomains"] = ["viur.com"]

