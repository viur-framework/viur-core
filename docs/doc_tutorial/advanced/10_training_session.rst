--------
Sessions
--------

ViUR has a built-in session management system provided by :class:`server.session`.

This allows storing information between different http-requests.
Sessions are automatically created as needed. As the first information is stored inside the session
a cookie is placed on the clients browser used to identify that session.

Storing and retrieving data is easy:

.. code-block:: python

    from server import session

    # Store data inside the session
    session.current[key] = value
    # Get returns none if key doesn't exist:
    val = session.current.get(key)
    # Throws exception if key doesn't exist:
    val = session.current[key]


You can store any json-serializable type inside the session, including lists and nested dicts.
All data inside the session is only stored server-side, it's never transferred to the client. So it's safe to store
confidential data inside sessions.

.. Warning::
        - For security-reasons, the session is reset if a user logs in or out.
          All data (except the language chosen) is erased. You can set "viur.session.persistentFieldsOnLogin" and
          "viur.session.persistentFieldsOnLogout" in server.config to explicitly white-list properties that should
          survive login/logout actions.
        - Also for security-reasons, the session-module uses two independent cookies, one for unencrypted http
          and one for a secure SSL channel. If the session is created by a request arriving via unencrypted http,
          the SSL-Cookie cannot be set. If the connection later changes to SSL, the contents of the session are
          also erased.
        - Sometimes the session-module is unable to detect changes made to that data (usually if val is something
          that can be modified inplace (eg a nested dict or list)). In this case its possible to notify the session that
          the contents have been changed by calling session.current.markChanged().


