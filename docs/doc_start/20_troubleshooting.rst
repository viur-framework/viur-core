===============
Troubleshooting
===============


In this chapter will show you various pitfalls you might encounter when using ViUR, explain whats the root cause and
how to sort things out.

My new project did not create an admin user when deployed
---------------------------------------------------------

ViUR schedules a task that will ensure that there is at least one user in your user table on instance startup.
If you just fired up your new project and you did not get an email with credentials it's usually one of the following:

  - You did not use/import the user module or you have an syntax error that prevents the project from starting at all
  - The deferred task had not kicked off yet. Either, there is no instance started yet (opening <your appid>.appspot.com
    in your browser will kick one off) or the default queue is still suspended. The task queue will start a few
    minutes after your first deployment.
  - You are missing indexes required to check/create a new user. Start your project at least once locally to ensure
    the required indexes are written to index.yaml. Then wait until these indexes are build and ready to serve.
  - There had been a race condition between the first requirements that caused the user to be created but stopped the
    mail from being sent. Wait until these requirements are settled, then (using the cloud console) delete the user
    and the user-uniquePropertyIndex from the datastore, flush the memcache and kill all instances currently running.
    As soon as a new instance starts up, a new admin user is created.


I have data inside the datastore, but my query doesn't find and return it
-------------------------------------------------------------------------

First of all, check the logs. If there is anything wrong with your model preventing this query from succeeding, ViUR
will usually warn you. Look for lines complaining about "Invalid filtering", "Invalid searchfilter" or
"Invalid ordering". In case of relationalBones ViUR will also tell you wherever it expected an property named in
ref-/rel- Keys. Did you set an property to indexed=True or included it in ref-/rel- Keys after data had already been
written to the datastore? Use the rebuild search index task (vi --> gear icon top right or
admin --> "tasks" in your menu bar) to update data already in the datastore.
Check if you have the permission to retrieve that entry. Verify that the listFilter() function in your module doesn't
alter your query in a way that excludes these entries. Did you use query.filter() somewhere in your query? It does *not*
perform any error/type-checking. Check that your types match: qry.filter("test =", str("5")) is *not* equivalent to
qry.filter("test =", int(5)). If in doubt, check the entry, the types of it's values and wherever properties are indexed
using the cloud console. Temporary rewrite your query to use .mergeExternalFilter() and see if that succeeds.
If you had still no luck; set "viur.debug.traceQueries" in viur.core.config to True. It will log the raw filters and
orderings send to the datastore (and wherever it yields any results). Verify that the query looks like expected, then
manually run that query in the cloud console using GQL.


I got unicode encode/decode errors in my templates
--------------------------------------------------

ViUR is designed to handle unicode data. This usually happens if you supply non-unicode data that contains non-ascii
characters. Check your models that this template accesses. You'll probably miss the *u* (unicode marker) in a bone
description, somewhere in it's params or in the values in case of selectOne/selectMulti bones. So check it always reads
descr=u"My description" instead of descr="My description" in your bone definitions.


I got some wired exception in my templates im unable to spot
------------------------------------------------------------

Sometimes you'll get miss-leading tracebacks from the template engine where the traceback points to a totally different
and unrelated location. To nail down the root cause first remove the extends-clause from your template (if any).
Check if the issue still persists. If not, you're looking at the wrong template.
Then remove all begin block/end block markers from the template. If still no clue, remove macro imports (and calls).
If the issue still persists, it's usually triggered by a call to a server-side function, that itself tried to load and
parse another template. Usual suspects are execRequest() calls which embed other fragments. Enabling "viur.disableCache"
in the config helps tracing exceptions that appear infrequently.


Internationalization (i18n) does not work
-----------------------------------------

Verify that you selected a method for ViUR to determine the language acceptable for the current request
(check viur.core.config["viur.languageMethod"]). Working with different domains does not work on the development server,
the session (cookie) approach does not work for search engines like google. Check that your project has a "translations"
module, it contains tables for the languages you'll need and that it's importable without exception. Then ensure that
viur.core.config["viur.availableLanguages"] is filled (*after* viur.core.setup() had been called).


Still lost?
-----------
..
    #FIXME: Is this still active? How about issues, discussions, ...

Feel free to join our IRC channel #viur on freenode `<https://webchat.freenode.net?channels=viur&uio=d4>`_ and ask your
project-specific questions.


