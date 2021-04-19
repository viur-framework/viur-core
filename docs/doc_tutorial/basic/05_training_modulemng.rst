
-----------------
Module management
-----------------

In ViUR, any custom modules are established on top of one of the four module prototypes. The modules are the linchpin of every ViUR application. They provide interfaces to securely add, edit, delete or view entries, to perform custom operations and tasks, to prepare output data or validate input data.

The most commonly used module prototype is :class:`List<core.prototypes.list.List>`, which provides a flat list of database entries with the same entity kind. To become more familiar with the management of modules in general, the next sections are mostly using the :class:`~server.prototypes.list.List` module prototype again as its base. Moreover, the other module prototypes and their specialities are discussed later on, when the basics of the :class:`~server.prototypes.list.List` module are understood so far.


Creating modules
----------------

Creating a module is simple. It just requires to put a class named like the new module as a single Python file in the ``modules/`` directory of the current application.

.. code-block:: python
   :caption: modules/person.py
   :linenos:

   #-*- coding: utf-8 -*-
   from server.prototypes import List

   class Person(List):
      pass

This is already everything needed so far. The **import**-statement in line 2 imports the :class:`List<core.prototypes.list.List>` prototype. Certainly, it is also possible to import from another prototype or to import an already pre-build module from the server or from the current application itself. Any way of inheritance mechanism can be used here.

The **class**-statement in line 4 finally introduces the class of the new module, which inherits from the :class:`List<core.prototypes.list.List>` prototype. So this class initially provides all the features and functions provided by the :class:`List<core.prototypes.list.List>` class.

The naming of the class has also two important purposes:

1. The module tries to resolve for a skeleton named after the module in lower-case order with a trailing "Skel" that is used as data model. So in this example, "personSkel" will be the name of the skeleton ViUR will try to resolve. This detection can be completely bypassed, by overriding :meth:`baseSkel<core.prototypes.list.List.baseSkel>` and returning an appropriate skeleton instance.

2. If the default project setup has been done, the module is automatically imported in lower-case order (person) into the application, so it can be accessed by ``/person`` or ``/renderer/person`` as first part of the URL. This naming convention can be entirely changed by importing the module manually in the file ``modules/__init__.py``.

.. Note::

    If you reload the Vi now, you'll already see the new module showing up.
    But it isn't usable yet as it has no skeleton to work on.
    See :doc:`basics</doc_tutorial/basic/index>` to learn how skeletons and modules interact.

Data modification interfaces
----------------------------

All module prototypes provide several externally exposed functions for data modifications, serving as an interface to the web-application.

These functions are:

- **add** for adding a new entry (:meth:`List.add() <core.prototypes.list.List.add>`, :meth:`Hierarchy.add() <core.prototypes.hierarchy.Hierarchy.add>`, :meth:`Tree.add() <core.prototypes.tree.Tree.add>`),
- **delete** for deleting an existing entry (:meth:`List.delete() <core.prototypes.list.List.delete>`, :meth:`Hierarchy.delete() <core.prototypes.hierarchy.Hierarchy.delete>`, :meth:`Tree.delete() <core.prototypes.tree.Tree.delete>`),
- **edit** for updating an existing entry (:meth:`List.edit() <core.prototypes.list.List.edit>`, :meth:`Singleton.edit() <core.prototypes.singleton.Singleton.edit>`, :meth:`Hierarchy.edit() <core.prototypes.hierarchy.Hierarchy.edit>`, :meth:`Tree.edit() <core.prototypes.tree.Tree.edit>`),
- **view** for just viewing an existing entry (:meth:`List.view() <core.prototypes.list.List.view>`, :meth:`Singleton.view() <core.prototypes.singleton.Singleton.view>`, :meth:`Hierarchy.view() <core.prototypes.hierarchy.Hierarchy.view>`, :meth:`Tree.view() <core.prototypes.tree.Tree.view>`).

These functions are entirely working on the skeleton API as described above. Every module also provides more, module-specific functions for data management, but this is not covered here.


Post-processing functions
-------------------------

Usually, the standard data modification functions from above should not be overridden in sub-classed modules, because they implement a secure and enclosed workflow. Nevertheless, it is possible to engage into these functions by overriding the so called event-driven functions, all taking the skeleton object of the specific operation, for further tasks or logics required.

- **onItemAdded** after an item is newly added (:meth:`List.onItemAdded() <core.prototypes.list.List.onItemAdded>`, :meth:`Hierarchy.onItemAdded() <core.prototypes.hierarchy.Hierarchy.onItemAdded>`, :meth:`Tree.onItemAdded() <core.prototypes.tree.Tree.onItemAdded>`),
- **onItemDeleted** after an existing item is deleted (:meth:`List.onItemDeleted() <core.prototypes.list.List.onItemDeleted>`, :meth:`Hierarchy.onItemDeleted() <core.prototypes.hierarchy.Hierarchy.onItemDeleted>`, :meth:`Tree.onItemDeleted() <core.prototypes.tree.Tree.onItemDeleted>`),
- **onItemEdited** after an existing entry is updated (:meth:`List.onItemEdited() <core.prototypes.list.List.onItemEdited>`, :meth:`Singleton.onItemEdited() <core.prototypes.singleton.Singleton.onItemEdited>`, :meth:`Hierarchy.edit() <core.prototypes.hierarchy.Hierarchy.onItemEdited>`, :meth:`Tree.edit() <core.prototypes.tree.Tree.onItemEdited>`),
- **onItemViewed** right before an existing entry is viewed (:meth:`List.onItemViewed() <core.prototypes.list.List.onItemViewed>`, :meth:`Singleton.onItemViewed() <core.prototypes.singleton.Singleton.onItemViewed>`, :meth:`Hierarchy.onItemViewed() <core.prototypes.hierarchy.Hierarchy.onItemViewed>`, :meth:`Tree.onItemViewed() <core.prototypes.tree.Tree.onItemViewed>`).


Access rights
-------------

Modules automatically provide access rights for *view*, *add*, *edit* and *delete*, which can be configured in the standard user module via the ``access`` bone for every user.
