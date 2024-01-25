############
Introduction
############

`ViUR`_ is a free software development framework for the `Google App Engine`_ platform.

It provides a clear concept for implementing agile data management software that runs on top of the Google cloud platform. It is written in `Python`_ for a maximum flexibility and easy-to-manage code. Its underlying database is `Google Cloud Datastore`_, which is a scalable document database.

The framework targets to the implementation of *information systems*, which are integrated, web-based applications or services performing data management and deployment operations of any kind. Therefore, ViUR is explicitly not claimed to be a content management system, although content management can be a part of a ViUR information system.

.. _ViUR: https://www.viur.dev
.. _Google App Engine: https://cloud.google.com/appengine/docs/python/
.. _Python: https://www.python.org/
.. _Google Cloud Datastore: https://cloud.google.com/datastore/docs/concepts/overview

================
Why to use ViUR?
================

Based on top of the Google Cloud Platform, ViUR provides a higher abstraction layer to easily write applications with quick results. It helps to manage data of any kind and for any purpose, to connect this data, to query it and to display it.

It uses the well-known MVC design pattern to modularize the data model, the controller and the viewer layer. It heavily relies on the object-oriented aspects provided by the Python programming language, and comes with a lot of build-in functionality. Several pre-defined and extendible modules for various use cases, e.g. a user-module, a file-module or a order module for web-shops, help to rapidly implement new applications.

The plugin-enabled data administration tools provided by ViUR automatically generate input masks from the data models, so no data management frontend development is required. Therefore, in early development stages, the definition of the data model and some module stubs suffices to setup a system with a basic data recording functionality.

====================
Who should use ViUR?
====================

ViUR is made for agile software development. The data model can be entirely changed during the development process without the loss of already captured information. The system can easily be extended to more, new modules, build-in functionality can be overridden, hooked and customized.

The system is not only intended to be used by developers. With the use of `Jinja`_ as its template engine for HTML, ViUR is also interesting for designers. A lot of build-in functions, a clear template implementation concept and a collection of macros for data rendering and dynamic input form creation help to connect their creative visions and ideas with a powerful software development framework.

.. _Jinja: https://jinja.palletsprojects.com/

=================
Who created ViUR?
=================

ViUR is developed and maintained by `Mausbrand Informationssysteme GmbH`_, a nice company from Dortmund, Germany.

We are a software company consisting of young, enthusiastic software developers, designers and social media experts, working on exciting projects for different kinds of customers. All of our newer projects are implemented with ViUR, from tiny web-pages to huge company extranets with hundreds of users.

Help of any kind to extend, improve and enhance this project in any kind or way is always appreciated.

.. _Mausbrand Informationssysteme GmbH: https://www.mausbrand.de/en

===============================
Where to find more information?
===============================

This manual is intended to be the official documentation and reference manual for ViUR, and should be a place to start with. But don't be afraid to talk to us and our community if you have questions or encounter problems.

Bugs or feature requests can be submitted to the different ViUR components and their maintainers on `GitHub <https://github.com/viur-framework>`_.

