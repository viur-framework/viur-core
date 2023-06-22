#####################
My first ViUR Project
#####################

After completing the first Steps in the Google Cloud Console (Verlinkung!!) you can start programming your first ViUR Application.
To start, you will need to set up you ViUR System localy.

On the `Awesome ViUR <https://awesome.viur.de>`_ website you will find a collection of Resources related to the ViUR Ecosystem.

ViUR on Linux
#############
1. Install the ViUR CLI Tool in your standard python environment:

.. code-block:: bash

    pip install viur-cli

2. Check your installation succes

.. code-block:: bash

    which viur
    # The Console Output Should look like this
    # /home/user/.local/bin/viur

3. Create a new local ViUR Project for the appengine project you have already created (If you don't know what i am speaking about, pls revisit `ViUR and the Google Cloud Console`_)

  .. code-block:: bash

    viur create projectname

  This commmand will prompt you to enter a application name and a develop version name. We recomend naming the appliation name after your appengine proje. The develop version name should have the same name but with a "-dev" postfix.

  .. code-block:: bash

    application name: projectname
    develop version name: projectname-dev


  3.1. Choose if you want to use a prebuild Version of ViUR Vi (Verlikung zu Doku!)

  3.2. Choose if you want to add ViUR Vi as a git submodule

  3.3. Choose if u want to add additional flare application

  3.4. Choose if you want to configure your project as a new gcloud project

4. Install your development dependencies
  Since we want to have the flexibility to work on different Versions of our software, we use virtual environments. You can find more information about pipenv `here <https://pipenv.pypa.io/en/latest/>`_.

  .. code-block:: bash

    pipenv install --dev

5. Check your installation succes.

  .. code-block:: bash

    nano Pipfile


  Your output should look like this.

  .. code-block:: bash

    [[source]]
    url = "https://pypi.org.sample"
    verify_ssl = true
    name = "pypi"

    [packages]
    viur-core = "==3.3.5"

    [dev-packages]
    viur-cli = "==0.7.7"
    pycodestyle = "==2.10.0"
    watchdog = "==2.2.1"

    [requires]
    python_version = "3.11"

6. Start your pipenv

  .. code-block:: bash

    pipenv shell

  This command will start a new virtual environment, installing packages in this environment will not install anything globally. So feel free to fool around.

7. Finish you Gcloud Setup

  .. code-block:: bash

    #This Script Enables API's and configures some more appengine stuff
    ./viur-gcloud-setup.sh projectname

8. Try out your installation by running your dev server

 .. code-block:: bash

    viur run

 .. warning::

    | On the first Start of your development server your Console will show you an Admin E-Mail and a Genereated Admin Password.
    | Please write that down. You can log into the Vi and Change the Password by hand afterwards.
    | It will look similar to this:

 .. code-block:: bash

    #ViUR created a new admin-user for you!
    #Username: admin@projectname-viur.com
    #Password: AJSDvwahe2"§38721290bkash1!

9. Open http://localhost:8080 and http://localhost:8080/vi to check if the front and backend of your system is working.

10. After your first deployment open the https://appspot.com
11. Visit the `IAM & Admin <https://console.cloud.google.com/iam-admin/iam?>`_ and press the "+ GRANT ACCESS" Button
12. Select the User: "projectname@appspot.gserviceaccount.com"
13. Assign following Roles:
  (a) Cloud Datastore User
  (b) Storage Object Admin

Reset my Admin User:
____________________
In the Case you have locked yourself out of your own system. There is a possible way back in bu you will need to sacrifice all your User Data.

.. warning::
    All your User Data will be Deleted in the Appengine and it will not be usefully recoverable. Se be Cautiouas

1. Open https://console.cloud.google.com and Navigate to your Project
2. Navigate to the `Datastore Entities Site <https://console.cloud.google.com/datastore/databases/-default-/entities>`_ of your project.
3. Search and delete all entries of the Kind *user*
4. Search and delete all entries of the Kind *user_name_uniquePropertyIndex*
5. Start your dev server again

Optional:

6. Recover from stress and Anxiety

.. Note::
    The ViUR Developers recommmend the usage of a Password Manager

ViUR on Mac x86
###############

ViUR on Mac ARM
###############

ViUR on Windows
###############
