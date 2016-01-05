
DESCRIPTION
###########

**ViUR** is an application development framework that mainly focuses to
implement cloud-based information systems on top of the `Google AppEngine™`_.

By design, ViUR-based applications are build upon simple, clear, flexible,
extendible, versatile, high-scalable and easy-to-use concepts. To fit the
requirements of modern agile software development workflows, ViUR is entirely
written in the `Python programming language`_.

Applications implemented in ViUR are not only limited to websites or any other
kind of specialized web-application. Therefore, we call ViUR an information
system, because it goes beyond the limitations of a content-management-system
or other kinds of specialized web-application software.

ViUR helps to manage any kind of information. It comes with a set of four
pre-defined application kinds which can be used to build modules for any
desired tasks. The system comes with a variety of pre-defined modules, which
can easily be adapted for particular goals. New modules are simply created or
extended from other ones. Data structures can be defined, extended and changed
during the development workflow. Input masks and data management interfaces
for all informations hold in the information system are dynamically created
within the administration tools.

ViUR currently exists of three parts:

- The **server** is the core of a ViUR application. It provides the server-parts
  of the web-application, a library of pre-defined data-models, modules, tools
  and libraries for data management and much more, and several renders to
  support different output kinds.
- The **admin** is the client-based, cross-platform administration backend to
  manage a ViUR application. It focuses on power-users that want to manage
  their applications with the full power of a desktop client computer.
- The **vi** (visual interface), is the web-based administration backend for
  ViUR written in pure HTML5, to provide an easy-to-access management tool
  that directly runs system-independently in the web-browser of any desktop or
  even mobile devices.

Both administration tools support the integration of application-specific
plug-ins and can be used independently, depending on what is wanted and
required.

.. _Google AppEngine™: http://appengine.google.com
.. _Python programming language: http://www.python.org/

PREREQUISITES
#############

The server components of ViUR are written in **Python 2.7** because they are
based on the Google App Engine SDK. The `Google App Engine SDK
<https://cloud.google.com/appengine/downloads#Google_App_Engine_SDK_for_Python>`_
is required for testing and deployment in the latest version.

As client system, Windows, OS X and Linux are supported, but Linux will give
you the best platform for development tasks with ViUR.

QUICK START
###########

To quickly build a running ViUR web-application, you only have to follow these
few steps:

1. Install the prerequisites (Python, Google App Engine SDK).
2. Download server and desired admin packages.
3. Create a project directory of your choice.
4. Unpack server package under ``<project-dir>/server``.
5. Run ``<project-dir>/server/setup.py``.

Now you're done: Run

::

	dev_appserver.py <project-dir>

or deploy your app to the world with

::

	appcfg.py update <project-dir>``


WHO CREATED VIUR?
#################

ViUR is developed and maintained by mausbrand Informationssysteme GmbH,
from Dortmund, Germany.

We are a software company consisting of young, enthusted software developers,
designers and social media experts, working on exciting projects for different
kinds of customers. All of our newer projects are implemented with ViUR, from
tiny web-pages to huge company intranets with hundres of users.

Help of any kind to extend and improve or enhance this project in any kind or 
way is always appreciated.

LICENSING
#########

ViUR is Copyright (C) 2012-2016 by mausbrand Informationssysteme GmbH.

You may use, modify and distribute this software under the terms and conditions
of the GNU Lesser General Public License (LGPL).

See the file LICENSE provided in this package for more information.
