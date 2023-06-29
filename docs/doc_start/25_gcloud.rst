#################################
ViUR and the Google Cloud Console
#################################

At the time of writing every ViUR system is written on top of the Google App Engine.
To be able to develop software with a ViUR system you need to follow some basic

steps in the Google Cloud Console.

.. Note::
  Please be aware that the Google products can produce costs to your Google Billing Account.
  Even if the **development** of software on the Google Cloud Platform mostly stays within the free contingent,

  you should get an overview of the `Google Cloud Billing <https://cloud.google.com/billing/docs>`_ documentation.

Google Cloud Console configuration:

The following steps are to be performed on the `Google Cloud Console <https://console.cloud.google.com/>`_

1. Register on the Google Cloud Console
2. Open the Google Cloud Console dashboard
3. `Create a new Google Cloud Project <https://developers.google.com/workspace/guides/create-project>`_

.. Note::
  Please be aware of juristical restrictions in your area, country and continent,

  such as GDPR  and configure your project accordingly.

4. Your project creation will trigger a task from Google, so please be patient while the task runs.
   This may take a while, grab a coffee, tea or beer meanwhile.

5. Visit your `Organisation Policy <https://cloud.google.com/resource-manager/docs/organization-policy/overview>`_ and enable Service Account creation.
   (You can find more information about that topic `here <https://cloud.google.com/iam/docs/service-accounts-create>`_)

The next steps are to be performed, if you are working as a team on the ViUR project:

6. Visit the `IAM & Admin <https://console.cloud.google.com/iam-admin/iam?>`_ menu of your Google Cloud Console
7. Add principals and roles to you project according to your project needs (You can find more information about this topic `here <https://developers.google.com/apps-script/guides/admin/assign-cloud-permissions?hl=en>`_)
