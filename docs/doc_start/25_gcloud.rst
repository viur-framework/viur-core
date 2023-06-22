#################################
ViUR and the Google Cloud Console
#################################

At the time of writing every ViUR System is written on top of the Google App Engine.
To be able to develop Software with a ViUR System you need to follow some basic
steps in the Google Cloud Console.

.. Note::
  Please be aware that the Google products can produce costs to your Google Billing Account.
  Even if the **Development** of Software on the Google Cloud Platform mostly stays within the free contingent,
  you should get an Overview of the `Google Cloud Billing <https://cloud.google.com/billing/docs>`_ Documentation.

Google Cloud Console configuration:

The Following Steps are to be Performed on the `Google Cloud Console <https://console.cloud.google.com/>`_

1. Register on the Google Cloud Console
2. Open the Google Cloud Console Dashboard
3. `Create a new Google Cloud Project <https://developers.google.com/workspace/guides/create-project>`_

.. Note::
  Please be aware of juristicial restrictions in your Area, Country and Continent,
  such as GDPR etc. and Configure your Project accordingly.

4. Your project creation will trigger a Task from Google, so please be Patient while the Task runs. Optionally you can Grab a Coffee or Tea
5. Visit your `Organisation Policy <https://cloud.google.com/resource-manager/docs/organization-policy/overview>`_ and enable Service Account Creation. (You can find more informations about that topic `here <https://cloud.google.com/iam/docs/service-accounts-create>`_)

The next steps are to be performed, if you are working as a Team on the ViUR Project:

6. Visit the `IAM & Admin <https://console.cloud.google.com/iam-admin/iam?>`_ Menu of your google cloud console
7. Add Principals and Roles to you Project according to your project needs (You can find more information about this topic `here <https://developers.google.com/apps-script/guides/admin/assign-cloud-permissions?hl=en>`_)
