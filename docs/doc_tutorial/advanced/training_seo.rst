---
SEO
---

ViUR offers the possibility to make URLs SEO-friendly in multiple languages.
For this you can define seo-identifiers for each url component.


Module
------
The module name is the first part of a URL.
SEO-identifiers have to be set as class-attribute ``seo_language_map`` of type ``dict[str, str]`` in the module.
It maps a *language* to the according *identifier*.

.. code-block:: python
    :name: module seo-map
    :caption: modules/myorders.py
    :emphasize-lines: 4-7

    from viur.core.prototypes import List

    class MyOrders(List):
        seo_language_map = {
            "de": "bestellungen",
            "en": "orders",
        }

By default the module would be available under */myorders*, the lowercase module name.
With the defined :attr:`seo_language_map`, it will become available as */de/bestellungen* and */en/orders*.

Great, this part is now user and robot friendly :)


Method
------
The method name is usually the second part of a URL.
SEO-Identifiers can be provided to the :meth:`exposed<core.exposed>` decorator of type ``dict[str, str]``.
It maps a *language* to the according *identifier*.

.. code-block:: python
    :name: method seo-map
    :caption: modules/myorders.py
    :emphasize-lines: 10-13

    from viur.core.prototypes import List
    from viur.core import exposed

    class MyOrders(List):
        seo_language_map = {
            "de": "bestellungen",
            "en": "orders",
        }

        @exposed({
            "de": "warenkorb",
            "en": "cart",
        })
        def view_the_cart(self):
            ...

By default the method would be available under */myorders/view_the_cart*.
With the defined `seo_language_map`, it will become available as */de/bestellungen/warenkorb* and */en/orders/cart*.

Great, this part is now user and robot friendly as well :)


Entry
-----
The entry key is usually used as third part of a URL if you use explicit the view method.
By default the :meth:`index<core.prototypes.list.List.index>` method
of the :class:`List prototype<core.prototypes.list.List>`
can handle keys or seo-identifiers of an entry as well.

SEO-Identfiers of an entry (a :class:`Skeleton<core.skeleton.Skeleton>` instance) are defined in the
method :meth:`getCurrentSEOKeys<core.skeleton.Skeleton.getCurrentSEOKeys>` inside your Skeleton.
This gives you the possibility to use whatever you want as identifier:
A timestamp, a bone value, a composition of bones values, ….


.. code-block:: python
    :name: entry seo-map
    :caption: skeletons/myorders.py
    :emphasize-lines: 20-38

    from typing import Union, Dict

    from viur.core.skeleton import Skeleton
    from viur.core.bones import *

    class MyOrdersSkel(Skeleton):
        first_name = stringBone(
            descr="Customer's firstname",
        )
        last_name = stringBone(
            descr="Customer's lastname",
        )
        # [...]

        order_number = numericBone(
            descr="Ordernumber",
            required=True
        )

        @classmethod
        def getCurrentSEOKeys(cls, skelValues) -> Union[None, Dict[str, str]]:
            """Return the seo-identifiers for this entry.

            Return a dictionary of language -> SEO-Friendly key
            this entry should be reachable under.

            The German and English identifiers are identical,
            they consist of the lastname (of the customer)
            and the (6 chars zero padded) order number.

            If the name is already in use for this module,
            the core will automatically append some random string
            to make it unique.
            """
            return {
                "de": f"{skelValues['last_name']}-{skelValues['order_number']:06}",
                "en": f"{skelValues['last_name']}-{skelValues['order_number']:06}",
            }


You can now reach your entries under */de/bestellungen/Mustermann-001234*

Great, we did it!

.. warning::

    Keep in mind that you can very easily guess the identifiers in this example.
    For obvious reasons orders should not be visible to everyone.
    In cases like this make the website noindexed and define a suitable :meth:`canView<core.prototypes.list.List.canView>`
    method inside your module, to restrict the access only to the account
    of the customer and seller.
