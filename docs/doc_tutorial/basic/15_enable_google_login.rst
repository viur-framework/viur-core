ViUR and Google Auth
####################

This changes took effect on ViUR >=3.3. In case you're using a prior version, you need to handle it differently.


1. Open the Google Cloud Console website as an admin user
2. Open the `API & Services OAuth conset screen <https://console.cloud.google.com/apis/credentials/consent>`_ menu
3. Declare your user type and click the "Create" button
4. Fill in the App information "Save and Continue"
5. Click the Button "Add or Remove Scopes" and choose the following scopes:
    (a) *../auth/userinfo.mail*
    (b) *../auth/userinfo.profile*
    (c) *openid*

.. Note::
    Those Scopes are the generall Scopes to get user information

6. Save and Continue
7. Navigate to `API & Services Credentials <https://console.cloud.google.com/apis/credentials>`_
8. Press the button "+ create credentials"
9. Select "OAuth Client ID"
10. Enter your application type as "Web Application"
11. Enter a name for your OAuth 2.0 client
12. Click the "Add URI" button, under the "Authorized Javascript origins" headline
13. Enter your redirect URL's

    | For deployed Software we recommend:
    | "https://projectname.appspot.com"
    | If you want to use the Google LogIn in your development System you will also need to add:
    | "http://localhost:8080"
    | "http://localhost"

14. Click the "Create" buttton
15. Copy the client ID of the succes message to your clipboard
16. Open the main.py of your ViUR project and add the config variable and the id

#.. code-block:: python
#    # Insert your clientID as String
#    conf["viur.user.google.clientID"] = " "
#    # If you are a gsuitecustomer, you can whitelist mails form certain Domains
#    conf["viur.user.google.gsuiteDomains"] = ["viur.com"]

