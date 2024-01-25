--------
Sessions
--------

ViUR has a built-in session management system provided by :class:`core.session.Session`.

This allows storing information between different HTTP-requests.
Sessions are automatically created as needed. As the first information is stored inside the session
a cookie is placed on the clients browser used to identify that session.

Storing and retrieving data is easy:

.. code-block:: python

    from viur.core import current

    # Load the current session from the ContextVar
    session = current.session.get()
    # Store data inside the session
    session[key] = value
    # `get()` returns `None` if the key doesn't exist, the value otherwise:
    val = session.get(key)
    # Throws an exception if the key doesn't exist:
    val = session[key]


You can store any JSON-serializable type inside the session, including lists and nested dicts.
All data inside the session is only stored server-side, it's never transferred to the client. So it's safe to store
confidential data inside sessions.


.. Warning::
    - For security-reasons, the session is reset if a user logs in or out.
      All data (except the language chosen) is erased. You can set :ref:`config-viur-session-persistentFieldsOnLogin` and
      :ref:`config-viur-session-persistentFieldsOnLogout` in :mod:`core.config` to explicitly white-list properties that should
      survive login/logout actions.
    - Also for security-reasons, the session-module uses two independent cookies, one for unencrypted HTTP
      and one for a secure SSL channel. If the session is created by a request arriving via unencrypted HTTP,
      the SSL-Cookie cannot be set. If the connection later changes to SSL, the contents of the session are
      also erased.
    - Sometimes the session-module is unable to detect changes made to that data (usually if ``value`` is something
      that can be modified inplace (e.g. a nested dict or list)). In this case its possible to notify the session that
      the contents have been changed by calling :func:`current.session.get().markChanged()<core.session.Session.markChanged>`.
