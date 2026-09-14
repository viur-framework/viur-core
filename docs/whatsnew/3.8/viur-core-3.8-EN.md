# What's new in viur-core 3.8?

This document describes the most significant changes in viur-core 3.8.

## General

viur-core 3.8 is now only compatible with Python 3.12 and Python 3.13. All versions below these are no longer supported. The documentation is now also generated with the latest Sphinx under Python 3.13.

In viur-core 3.8, the compatibility flags for old Admin and Vi versions are disabled by default, so that only the new formats are used.

The following lines can now be completely removed from projects ported to viur-core 3.8:

```py
# These lines can be removed:
conf.compatibility.remove("json.bone.structure.keytuples")
conf.compatibility.remove("json.bone.structure.camelcasenames")
conf.compatibility.remove("bone.select.structure.values.keytuple")
conf.compatibility.remove("json.bone.structure.inlists")
```

In addition, `conf` now runs in strict mode, i.e., compatibility with old `conf` accesses such as `conf["mainApp"]` is no longer allowed.

In the renderers, the modules `render.json.user` and `render.vi.user` have been completely removed without replacement. References to these should be removed in old projects. Only the respective default class is now used for all renderers.

## Internationalization (i18n)

All Bone validations now provide translated error messages (previously only available in English).

The flag `conf.i18n.auto_translate_bones` can now be used to set globally whether `descr` and `params.category` should be automatically translated for Bones or not (default: True, as before).

## Database

## `db` module is back in viur-core

The `db` module, the ViUR abstraction for low-level Cloud Datastore database access, is now part of `viur-core` itself again.

The module was spun off into its own package `viur-datastore` in viur-core 3.1. This was done partly to improve performance at the time, and partly to connect to other databases—which never happened. Ultimately, this split led to major problems and inconsistencies in further development, and Google's own implementation of the Datastore API is now faster again.

The re-integrated `db` API contains the familiar functions such as `db.put`, `db.get`, `db.delete`, etc. However, these are now written in snake case in accordance with PEP-8, so that using the old functions generates a deprecation warning.

The configuration of `db`-specific settings is done via [`conf.db`](https://core.docs.viur.dev/en/develop/viur/core/config/index.html#core.config.Database).

### Query limits

> [!IMPORTANT]
> Starting with viur-core 3.8, it is no longer necessary to explicitly pass `/example/list?limit=99` when calling list modules externally in order to obtain more than 30 records. This has been improved, so please take advantage of the new options!

ViUR always expected additional records to be reloaded via cursor, which in Jinja templates could only be solved with JavaScript and would be quite complicated. These limits (30 and 100) were previously hard-coded.

This can now be modified globally and individually in the project using the following `conf` variables:

- `conf.db.query_default_limit` (default: 30) is the standard limit for queries.
- `conf.db.query_external_limit` (default: 100) is the maximum limit for queries that can be set via external calls. This prevents users of a ViUR system from setting a limit of 30,000 from outside, even though only `conf.db.query_default_limit = 100` has been set.

A project that is configured in main.py, for example, with

```py
conf.db.query_default_limit = 200
```

will always retrieve up to 200 entries for all queries, so you can save yourself the `?limit=99` if, for example, you expect 120 records and want "the maximum possible number" because the internal limit has already been set to 200.

### Skeleton API

The Skeleton API (formerly `skeleton.py`) has now been split into a module with several files.

#### `viur-relations` and `RelationalConsistency`

Furthermore, the entire `viur-relations` handling has been completely refactored around the function `update_relations()`. This means that RelationalBones in RecordBones are also updated. RelationalConsistency consistency checks are now also handled by `update_relations()`—this was previously done by the `processRemovedRelations` function, which has been replaced by the refactoring and is now obsolete.

#### RelationalBone.fromClient() refactored

`RelationalBone.fromClient()` has also been refactored to accept RelationalConsistency settings and remove generally terrible code. This prevents the saving of relations to records that no longer exist in the case of a set RelationalConsistency. If no RelationalConsistency is set, the bone behaves exactly as before.

#### RefSkel.read()

You can now read the target skeleton of a RelationalBone directly using [RefSkel.read()](https://core.docs.viur.dev/en/develop/viur/core/skeleton/relskel/index.html#core.skeleton.relskel.RefSkel.read).

```py
# Read user
user_skel = UserSkel()
assert user_skel.read(key)

# Read company for user
company_skel = user_skel["company"]["dest"].read()  # entire CompanySkel (already possible in v3.7)

# ... you can also create (dynamic) SubSkels (only from v3.8):
company_skel = user_skel["company"][‘dest’].read(subskel=("select",))  # SubSkel defined in subSkels
company_skel = user_skel["company"]["dest"].read(bones=(‘name’, "city",))  # dynamic SubSkel
```

#### Skeleton.readonly()

Set all bones of a skeleton to `readOnly=True`, e.g. for ActionSkels:
```py
channel_skel.readonly()
```

#### Skeleton.dump()

Generate a JSON-serializable representation directly from a skeleton:
```py
channel_skel.dump()
```

Previously, you had to do something crazy like this:
```py
from viur.core.render.json.default import DefaultRender as JsonRender
#...
JsonRender().renderSkelValues(channel_skel)
```

### Bones

#### `searchable=True` for `RawBone`

RawBones can now be `searchable=True`. In addition, the extraction of search terms has been changed to regular expressions and generalized between string, text, and RawBone.

#### ImageBone

The `ImageBone` should be used generally for images and was introduced for accessibility and to clearly define an image in the data.

It is configured as

```py
class ImageBone(FileBone):
    type = FileBone.type + ".image"

    def __init__(
        self,
        *,
        public: bool = True,
        using: t.Optional[RelSkel] = ImageBoneRelSkel,
        validMimeTypes: None | t.Iterable[str] = ["image/*"],
        **kwargs,
    ):
        super().__init__(
            public=public,
            using=using,
            validMimeTypes=validMimeTypes,
            **kwargs,
        )
```

The `ImageBoneRelSkel` contains translated fields for alt texts.

![ImageBone](imagebone.png)

## `Module.skel()`

In general, there is now a `skel()` function for modules. This is equivalent to `baseSkel()`, only shorter. It will play an even greater role in viur-core>=4.

```py
assert (skel := self.skel().read(key))  # everything is there! :-D
```

## `File` module

The function [`File.write()`](https://core.docs.viur.dev/en/develop/viur/core/modules/file/index.html#core.modules.file.File.write) now allows the optional specification of a repository and a path. This allows files written by the ViUR system to be written directly to a directory in the File module. The directory is created automatically if it does not exist.

```py
conf.main_app.file.write(
    f"test-{utils.utcNow().strftime("%d-%m-%Y_%H-%M-%S")}.txt",
    b"Hello World",
    folder=("My text files", str(utils.utcNow().year))
)
```

![File.write() with repository and path](file-write-folder.png)

## `History` module

For the first time, there is now a ViUR standard history module. This consists of the components [`History` (a list module)](https://core.docs.viur.dev/en/develop/viur/core/modules/history/index.html#core.modules.history.History) and the `HistoryAdapter`.

The History module writes to the ViUR system by default, but can also write to BigQuery optionally. This is configured via the [History Config](https://core.docs.viur.dev/en/develop/viur/core/config/index.html#core.config.History).

To use the module, it must be subclassed once in the system (just like `File`):

```py
from viur.core.modules.history import History

class History(History):
    adminInfo = History.adminInfo | {
        "moduleGroup": "system",  # here, for example, the module is placed in another module group
    }
```

A skeleton that is to generate history entries must be configured as follows:

```py
from viur.core.skeleton import Skeleton, ViurTagsSearchAdapter
from viur.core.bones import *
from viur.core.modules.history import HistoryAdapter


class ExampleSkel(Skeleton):
    database_adapters = (
        ViurTagsSearchAdapter(),
        HistoryAdapter(),
    )
```

Additional settings can be made via the [HistoryAdapter](https://core.docs.viur.dev/en/develop/viur/core/modules/history/index.html#core.modules.history.HistoryAdapter), e.g., which bones should be ignored.

## `User` module

### `is_admin()` function

The `is_admin()` function of the User module defines which users are considered administrators. This can be defined on a project-specific basis. Previous checks of the type `if "root" in user["access"]:` should be replaced by `if conf.main_app.user.is_admin(user):`.

Checks for `"root" in user["access"]` should really only be used in cases where superuser rights are actually necessary (e.g., maintenance functions).

### Login process changed to ActionSkels

The login process in the user module has been changed so that ActionSkels are now output to guide the user through the login process using a specific login method. This has been implemented in the admin area and will soon be relevant for several projects.

> [!IMPORTANT]
> This is a minor breaking change, but it could only cause problems in specific projects, as the /vi/user/login function now either displays an ActionSkel with the possible login methods (if there are several) or redirects to the only existing login method. The function with the ridiculously stupid name /vi/user/getAuthMethods, which previously did exactly the same thing as /vi/user/login, is now deprecated and will soon be removed.

### `User.adminInfo` is now a function

You can no longer do something like this, as you could before:

```py
from viur.core.modules.user import User

class User(User):
    adminInfo = User.adminInfo | {
        # ...more settings...
    }
```
Instead, you must now explicitly do the following:
```py
from viur.core.modules.user import User

class User(User):
    def adminInfo(self):
        return super().adminInfo() | {
        # ...further settings...
    }
```

> [!IMPORTANT]
> This is a minor breaking change that could cause an error when starting the project in some projects. Please correct as above.

## SkeletonMaintenanceTask

The server task `rebuildSearchIndex` has been removed and replaced by `SkeletonMaintenanceTask`.

With this task, only ‘root’ users can perform one or more of the following actions on their children

- Refresh (formerly rebuildSearchIndex)
- Delete
- Count

Filtering can be performed to pre-filter the data selection (normal filtering).

In addition, logics can be used to define a programmed conditional expression that is applied to each data record and refreshes, deletes, or counts it.

![SkeletonMaintenanceTask](skeleton-maintenance-task.png)

> [!IMPORTANT]
> The condition `False  # fused: by default, doesn't affect anything.`, which is always preset, is like a security prompt.
> If left as is, NO data records will be refreshed, deleted, or counted. Therefore, you must explicitly enter `True` or something regulatory there.
