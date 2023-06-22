
-----------------
Viur3 on Windows
-----------------
Although Viur3 is made to run on Linux and Apple OS, there is a workaround for it to function on Windows operating systems.

We can only assure the following steps to work on devices using the Windows 10 operating system and Ubuntu as a subsystem.

Installing Linux Subsystem 2 (WSL2) for Windows 10
---------------------------------------------------

Step 1: Prepare your Device for WSL2
____________________________________

Some devices are per default prepared for the usage of WSL2.

If your system is not prepared for the usage of WSL2 you can follow this manual:

https://docs.microsoft.com/de-de/windows/wsl/install-win10#manual-installation-steps

Step 2: Install the Ubuntu sub system for Windows
_________________________________________________

If you do not own a Linux distribution for your Windows device you can download Ubuntu in the Microsoft Store.

https://www.microsoft.com/en-us/p/ubuntu/9nblggh4msv6?activetab=pivot:overviewtab

By starting the Program after your installation you prepare your device for the usage of Ubuntu.
After typing in your username and password you can use the console fully.

Step 3 (Optional): Install the Windows Terminal
_______________________________________________

To avoid problems with the Ubuntu console and for usability and accessibility reasons you can additionally download the Windows Terminal.

https://www.microsoft.com/de-de/p/windows-terminal/9n0dx20hk701?activetab=pivot

You can use your Ubuntu console using the :command:`bash` command

Installing Prerequisites for Viur3
----------------------------------
Viur3 is a framework for the Google App Engine. Therefore, you need install the Google Cloud SDK and some features of it.

Step 1: Install the Google SDK
______________________________
To install the basics of the Google Cloud SDK you need to follow this tutorial:

https://cloud.google.com/sdk/docs/install

After installing the Google Cloud SDK you need to install the following additional Components:

1. google-cloud-sdk-app-engine-python:
:command:`sudo apt-get isntall google-cloud-sdk-app-engine-python`

2. google-cloud-sdk-app-engine-python-extras:
:command:`sudo apt-get isntall google-cloud-sdk-app-engine-python-extras`

3. google-cloud-sdk-datastore-emulator:
:command:`sudo apt-get isntall google-cloud-sdk-datastore-emulator`

4. google-cloud-sdk-cloud-build-local:
:command:`sudo apt-get isntall google-cloud-sdk-cloud-build-local`


Step 2: Check for Python2 and Python3
_____________________________________
Check if your system recognizes your python installation.
GAE will need python2 **and** python3 to work.

You can check your status with these commands:
1. :command:`python2 --version`
2. :command:`python3 --version`

If one of the Versions is not installed you can manually reinstall them by using the following commands:
:command:`sudo apt-get install python2`
:command:`sudo apt-get install python3`


Step 3: install python-is-python3
_________________________________
For Ubuntu 20 the default Python command is undefined. Therefore, most packages will depend explicitly on the :command:`python2` or :command:`python3` command.

By using python-is-python3 we can globally avoid errors thrown by the unnumbered :command:`python` command.

To install python-is-python3 use the following command:
:command:`sudo apt-get install python-is-python3`


You can read more about python-is-python3 here:
https://packages.ubuntu.com/focal/python-is-python3

Step 4: Install the Python3 Virtual Environment
_______________________________________________
For Viur3 to run you will need a Python Virtual Environment.

To install the Virtual Environment use the following command:
:command:`sudo apt-get install python-venv`



