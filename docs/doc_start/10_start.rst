###############
Getting started
###############

This part of the documentation provides a first steps guide for quickly setting up an application with ViUR.
The following chapters will go much deeper into ViUR, its architecture and how it is used.
The Google App Engine™ is only introduced shortly here. Knowledge on what it is, how it works and how an
application is registered there is required before continuing.

=============
Prerequisites
=============

ViUR runs on top of the Google App Engine (GAE) platform for the Python Standard Environment. This means,
that a ViUR application has to be deployed to a project in the Google Cloud Platform when it is run on the internet.

Before you start your first ViUR project, make sure that at least the first of the following prerequisites are
installed on your system.

.. note::
    We strongly recommend to use a POSIX-like operating system like Linux or Mac OS for developing ViUR applications.

    Getting ViUR to run properly on Microsoft Windows is a nightmare for several reasons. The only well-working
    solution to use a Windows system for ViUR development is when
    `Windows Subsystem for Linux <https://en.wikipedia.org/wiki/Windows_Subsystem_for_Linux>`_ is used - otherwise,
    forget about it. A tutorial to set it up is available at :doc:`VIUR3 on Windows </doc_tutorial/basic/viur_on_windows>`


------------
Python & pip
------------

Since ViUR is a framework written in pure Python, it requires a Python interpreter to be installed.
ViUR currently only runs with Python 3.10+ and upwards, so this must be installed on your system.


`Pip <https://pypi.org/project/pip/>`_, the Python package installer, is also a necessary feature
to develop applications with ViUR.

----------
gcloud SDK
----------

For the deployment as well as a local development and testing environment, Google offers the
`gcloud SDK for Python <https://cloud.google.com/appengine/docs/standard/python3/setting-up-environment>`_.

Download and install the gcloud SDK natively from the above location for your platform. Mac OS, Linux and Windows
are supported. In case that Linux is used, your favorite package manager should be consulted first, maybe it
already supports packages for the gcloud SDK.

.. note::
    For now, Google offers its "Python Standard Environment" that ViUR is using only for Python 3.10+.


After you successfully installed the gcloud SDK, make sure that you install the following components:

- app-engine-python
- app-engine-python-extras
- cloud-datastore-emulator

To install all required gcloud components, just run

.. code-block:: bash

    gcloud components install app-engine-python app-engine-python-extras cloud-datastore-emulator


.. figure:: /images/start-gcloud-components-list.png
   :alt: Image showing the output of 'gcloud components list'

   This is how ``gcloud components list`` should look like.

---------------------
Further prerequisites
---------------------

For a full ViUR development environment, the following components must also be installed and made available on your system:

- Pyodide
- `{less} <http://lesscss.org/>`_ is a compiler for a *better* CSS-dialect. It is also required to build ViUR's
    web-based administration interface **vi**, but also by our design- and UI-framework
    `ignite <https://github.com/viur-framework/ignite>`_
- In most cases it is required to install `npm <https://www.npmjs.com/>`_ to get {less} and build-systems
    like gulp to work, which is also used by **ignite**.


=======================
Starting a ViUR project
=======================

For a professional project setup, we recommend to use our pre-configured
`base repository <https://github.com/viur-framework/viur-base>`_.
This repository can be used for a ViUR project setup that prepares the required
ViUR modules like ``viur-core``, ``vi-admin`` and ``ignite`` as dependencies into the repository.


---------------------------
Cloning the base repository
---------------------------

..
    #TODO: describe the way with the viur-cli!

Simply clone the base repository and afterwards run ``clean-base.py`` to obtain a stand-alone repository which can
immediately be executed or pushed wherever you like.

These are the commands to be executed in a shell:

.. code-block:: bash

   # Clone base repository into a project folder
   git clone https://github.com/viur-framework/viur-base.git hello-viur

   # Change into new project folder
   cd hello-viur

   # Run clean-base.py
   ./clean-base.py


.. figure:: /images/start-clean-base-run.png
   :alt: Image showing the output of the steps done to clone the ViUR base repository

   Cloning and setting up the ViUR base repository for a new project.


-------------
First startup
-------------

When the above steps where initially performed, you can _locally_ start your application. For this case,
the gcloud SDK offers the program ``dev_appserver.py``. This program can be used to emulate a Google App Engine
standard environment on the local development computer and is perfectly suitable for creating the data model and
basic functionality.

You can either start ``dev_appserver.py`` with its particular parameters by hand, or use the script
``local_run.sh`` which is generated from the ``clean-base.py`` run above.

.. code-block:: bash

   ./local_run.sh


.. figure:: /images/start-dev_appserver-run.png
   :alt: Image showing the output of the steps done when starting ``dev_appserver.py``

   First local start of the new ViUR application.

When the output on your console looks like above, fire up your favorite web-browser and open
`http://localhost:8080 <http://localhost:8080/>`_. You should see a warm welcome from your ViUR project!

.. figure:: /images/start-firstrun-frontend.png
   :alt: Display of the generated welcome page on http://localhost:8080

   Welcome to your new project!


----------
Logging in
----------

On the first startup, ViUR creates an new admin-user named ``admin@<your-app-id>.appspot.com`` with a random password
for you. This password is printed to the server's debug console, where you have to copy it out.

Watch out for a line that looks like this:
::
   ViUR created a new admin-user for you! Username: admin@hello-viur.appspot.com, Password: SU7juUIb1F2aZ

When the system is started in the cloud for the first time, an e-mail with this password is sent to all application administrators.

Alternatively, you can login with a simulated Google user. Both login forms are provided by the default server and can be done using the *Vi*.

------------
What's next?
------------

When you came to this point, you're ready to start with the :doc:`basic concepts </doc_tutorial/basic/index>` and do first steps in developing your project.
