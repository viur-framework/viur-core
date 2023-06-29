#####################
My first ViUR Project
#####################

After completing the first steps in the Google Cloud Console you can start programming your first ViUR Application.
To start, you will need to set up you ViUR system localy.

.. warning::
    Before performing the following Steps, please make sure to visit `Awesome ViUR <https://awesome.viur.dev>`_
    and perform the ViUR setup steps for your operating system.

Start with ViUR
###############

1. Install the ViUR CLI Tool in your standard python environment:

.. code-block:: bash

    pip install viur-cli

2. Check your installation success

.. code-block:: bash

    which viur
    # The console output should look like this:
    /home/user/.local/bin/viur

3. Create a new local ViUR project for the appengine project you have already created

  .. note::
    If you don't know what i am speaking about, please revisit `ViUR and the Google Cloud Console`_

  .. code-block:: bash

    viur create projectname

  This commmand will prompt you to enter a application name and a develop version name.
  We recommend naming the application name after your appengine project.
  The develop version name should be the same, but with a "-dev" postfix.

  .. code-block:: bash

    application name: projectname
    develop version name: projectname-dev


  3.1. Choose if you want to use a prebuild version of ViUR Vi

  3.2. Choose if you want to add ViUR Vi as a git submodule

  3.3. Choose if you want to configure your project as a new gcloud project

4. Install your development dependencies
  Since we want to have the flexibility to work on different versions of our software, we use virtual environments.
  You can find more information about pipenv `here <https://pipenv.pypa.io/en/latest/>`_.

  .. code-block:: bash

    pipenv install --dev

5. Check your installation success.

  .. code-block:: bash

    $EDITOR Pipfile


  Your output should look like this.

  .. code-block:: bash

    [[source]]
    url = "https://pypi.org.sample"
    verify_ssl = true
    name = "pypi"

    [packages]
    viur-core = "*"

    [dev-packages]
    viur-cli = "*"
    pycodestyle = "*"
    watchdog = "*"

    [requires]
    python_version = "3.11"

6. Start your pipenv

  .. code-block:: bash

    pipenv shell

  This command will start a new virtual environment, installing packages in this environment will not install anything globally.
  So feel free to fool around and experiment with packages.

7. Finish you GCloud setup

  .. code-block:: bash

    #This script enables API's and configures some more appengine stuff
    ./viur-gcloud-setup.sh projectname

8. Try out your installation by running your dev server

 .. code-block:: bash

    viur run

 .. warning::

    | On the first start of your development server your console will show you an admin E-Mail and a generated admin password.
    | You can log into the Vi and change both the username and password by hand afterwards.

    | It will look similar to this:

 .. code-block:: bash

    #ViUR created a new admin-user for you!
    #Username: admin@projectname-viur.com
    #Password: ThisIsARandomStr1ng!

9. Open http://localhost:8080 and http://localhost:8080/vi to check if the front and backend of your system is working.

10. After your first deployment open https://appspot.com
11. Visit the `IAM & Admin <https://console.cloud.google.com/iam-admin/iam?>`_ and press the "+ GRANT ACCESS" Button
12. Select the user: "projectname@appspot.gserviceaccount.com"
13. Assign following roles:
  (a) Cloud Datastore User
  (b) Storage Object Admin

Reset my admin user:

____________________
In case you have locked yourself out of your own system. There is a possible way back in, but you will need to sacrifice
all your user data and log ins.

.. warning::
    All your user data will be deleted in the Appengine and it will not be recoverable.
    We only recommend this, if you see no other option of logging into your administration system

.. Note::
    The ViUR-Developers recommmend the usage of a Password Manager

1. Open https://console.cloud.google.com and navigate to your project
2. Navigate to the `Datastore Entities Site <https://console.cloud.google.com/datastore/databases/-default-/entities>`_ of your project.
3. Search and delete all entries of the kind *user*
4. Search and delete all entries of the kind *user_name_uniquePropertyIndex*
5. Start your dev server again

Optional:

6. Recover from stress and anxiety
