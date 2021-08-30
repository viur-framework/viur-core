================================
Quickstart (the short version)
================================
    1) Ensure that you have Python3.7+, gcloud sdk and git installed
    2) Register a new application-id on https://console.cloud.google.com/
    3) Enable the Firestore in *datastore* mode in this project
    4) Run the following commands

.. code-block:: bash

    gcloud components update
    gcloud components install app-engine-python app-engine-python-extras
    gcloud auth application-default login
    git clone https://github.com/viur-framework/viur-base.git
    cd viur-base
    git submodule init
    git submodule update
    cd deploy
    ./dev_appserver.py . --application your-application-id


The long version is the rest of this document :)

================================
Getting started
================================


.. toctree::
   :maxdepth: 1
   :glob:

   *