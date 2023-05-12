# Changelog

This file documents any relevant changes done to ViUR-core since version 3.0.0.

## [3.4.1]

- fix: enable to serialize complex custom config structures (#735)

## [3.4.0]

- fix: SelectBone `defaultValue` type annotation (#719)
- fix: comparison in `SelectBone.singleValueFromClient` (#726)
- fix: Jinja rendering for SelectBones using Enums (#720)
- fix: Use static handler "tree.simple.file" in File (#717)
- fix: Check for "status" in `User.onEdited` (#722)
- chore: Conventional commits and clarifications (#692)
- fix: Improvements and clarifications on version string (#706)
- security: Ensure active status in authenticateUser (#710)
- fix: bump viur-datastore to 1.3.9 (#708)
- fix: Run render_structure recursively on "using" and "relskel" (#705)
- feat: Implement naive mode for `DateBone` (#667)
- fix: SkelList.get_orders must be in the `__slots__` (#703)
- chore: Bump viur-datastore to 1.3.8 (#700)
- feat: Allow `Enum` for `SelectBone`-values and implement `User`s status as `Enum`  (#683)
- fix: Keep filename synchronous in both skeleton and blob (#699)
- refactor: Re-implement password encoding using Python's `hashlib` and `secrets` module (#680)
- fix: continue thumbnailing when image is broken (#697)
- feat: Inject "sortindex" attribute to bone structure (#698)
- fix: ignore downloadUrls without signature (#696)
- refactor: Replace `doClear*` by `DeleteEntitiesIter` (#694)
- fix: Update URL to viur.dev in error.html (#695)
- feat: Add `manage` access right (#693)
- feat: UserSkel improvements (`firstname`, `lastname`, `sync`) and Google Auth user information synchronization (#677)
- fix: Return JSON-encoded response for internal server errors too (#690)
- refactor: rename `Skeleton.toDB()`s `clearUpdateTag` into `update_relations` (#688)
- feat: Support JSON Schema validation for `JsonBone` (#657)
- feat: Implement `script` system-module for Scriptor tree (#664)
- fix: Capitalize internal classes to be PEP8 compliant (#681)
- fix: `viewSkel()`: It's a member of the user module, not the auth-provider (#674)
- feat: Improve `PasswordBone` parametrization (#619)
- fix: Add `RelationalUpdateLevel` to__all__ (#675)
- fix: spelling of "readonly" in renderEditForm (#670)
- fix: Add structure for numericBone (#672)
- fix: Fallback to `SkelModule` as replacement for `BasicApplication` (#665)
- refactor: `securitykey` module (#656)
- feat: Improve Cloud Tasks creation in `CallDeferred` and `QueryIter` (#654)
- refactor: DateBone: Refactored test if to use guessTimeZone into guessTimeZone itself (#644)
- feat: `current`-module to handle ContextVars, new `current.user` ContextVar (#635)
- feat: Move structure dict rendering from the renders into the bones (#637)
- feat: Add `admin_config` to UserSkel (#636)
- remove: session change in validateSecurityKey (#645)
- feat: Add `conf["viur.dev_server_cloud_logging"]` (#638)
- fix: module import in formmailer, introduced in #611 (#640)
- refactor: Substitute `BaseApplication` by `Module` and `SkelModule` prototypes (#611)
- refactor: Cleaning up the `session`-module (#544)
- fix: Implement a refresh method in the `NumericBone` (#617)
- feat: Render JSON-encoded error message on Exception raise in `/json` or `/vi` pathes (#614)
- refactor: Improvements for User module (#620)
- refactor: Make MetaBaseSkel.generate_bonemap available (#621)
- feat: Add `JsonBone` (#558)
- fix: Fixes a deprecation warning introduced by #582 (#613)
- refactor: Move projectBasePath and coreBasePath (#582)
- feat: Provide colorized local debug (#592)
- fix: added back kindName for userSkel (#600)
- fix: Improving MetaBaseSkel.fill_bonemap_recursive (#601)
- fix: `DateBone(localize=True)` becomes default setting (#595)
- refactor: Code clean-up for core user module (#591)
- feat: Improve the linter workflow: Use error annotations (#581)

## [3.3.5]

- Fix: Copy TextBone `_defaultTags` in `ModuleConfSkel` (#628)

## [3.3.4]

- Bump viur-datastore from 1.3.6 to 1.3.7 (#627)
- Fix: Reset renderPreparation in renderEmail (#625)
- Fix: `flushCache` used ViUR2-call to decode str-encoded key (#624)
- Fix: Use editSkel() in Tree edit/delete (#610)

## [3.3.3]

- Fix growing instance's Request header (#609)
- Provide `defaultvalue` in bone structure (#608)
- Refactoring `render.vi.getStructure` (#607)
- Change metaserver zone-request into region-request (#606)

## [3.3.2]

- Bump requirement certifi==2021.10.8 (#588)
- Bump setuptools from 62.0.0 to 65.5.1 (#602)
- Bump viur-datastore from 1.3.5 to 1.3.6 (#603)
- Fix stacklevel parameter for more precise deprecation messages (#596)
- Export RelationalUpdateLevel with viur.core.bones (#599)

## [3.3.1]

- Fixed user module renderer calls from password recovery (#597)
- Fixed path of index.yaml in packaged version (#590)

## [3.3.0]

- Fixed `import logging` must stay behind other imports in `__init__.py` (#573)
- Added distinctive type `select.country` for `SelectCountryBone` (#575)
- Added `Conf`-class to be used by global `conf`-variable (#567)
- Removed unused keys from `conf`: `conf["viur.capabilities"]`, `conf["viur.db.caching"]` and `apiVersion`
- Added system-module `ModuleConf` (#551, #577)
- Added `indexed`-flag in bone structures (#568)
- Renamed `utils.projectID` to `conf["viur.instance.project_id"]` (#562)
- Renamed `utils.isLocalDevelopmentServer` to `conf["viur.instance.is_dev_server"]` (#562)
- Changed default conf settings for `conf["viur.render.json.downloadUrlExpiration"]` and `conf["viur.render.json.downloadUrlExpiration"]` to `None` (#552)
- **BREAKING**: Renamed `conf["viur.downloadUrlFor.expiration"]` into `conf["viur.render.html.downloadUrlExpiration"]` (#552)
- Fixed HTTP reason phrase not be translated according to RFC2616 (#549)
- Updated dependency `viur-datastore` from 1.3.2 to 1.3.5 (#563, #576)
- Updated dependency `pillow` from 9.1.1 to 9.3.0 (#560)
- Added `is_deferred` flag to `currentRequest` for determination if a request runs deferred (#556)
- Added fine-grained `required`-flag to `BaseBone` to specify requirement for specific languages (#511)
- Added PEP-8 linting and push action (#554, #545, #543, #539, #540, #504)
- Removed obsolete `skey == ""` check from add/edit methods (#548)
- Refactored `getReferencedBlobs` and `getSearchTags` (#528)
- Fixed `utils.sanitizeFileName` to quote non-ASCII-characters in filename (#547)
- Refactored strings to be accepted as `True` values of booleans defined in `conf["viur.bone.boolean.str2true"]` (#533)
- Added support for custom Jinja tests (#532)
- Dependency upgrade readthedocs to v2 (#535)
- Added replaceable image deriver (#512)
- Removed obsolete methods getSearchDocumentFields (#527)
- Added enforce use of Python>=3.10 (#525)
- Add `RelationalUpdateLevel` (`Enum`) (#523, #534)
- Fixed check and reporting for `conf["viur.maxPostParamsCount"]` (#526)
- Fixed and refactored internally used `__reserved_keywords` (#529)
- Removed default logging handler which caused redundant logging output on local dev app server (#521)
- Fixed updateRelations to use `skel.refresh()` (#524)
- Refactored and cleaned up CallDeferred (#513)
- Added project zone retrieval by `metadata.google.internal` (#519)
- Added bone classes to `bones.__all__` (#522)
- Added automatic hmac-key creation for `conf["viur.file.hmacKey"]` (#516)
- Added `isEmpty`-function for StringBone (#514)
- Refactoring default renders for HTML/JSON/XML (#494)
- Fixed UNB Task and add Logging (#508)
- Fixed `generateOtps` function to work on python3 (#509)
- Added `SpatialBone` bounds checking and use `float` instead of `int` (#507)
- Refactored `fieldPath` for more precisely error reporting (#505)
- Added optional key existence check to `KeyBone` (#497)
- Fixed `translate` to explicitly cast non-str-values to str (#501)
- Added `maxLength` for `StringBone` (#500)
- Fixed max-value for `SortIndexBone` (#499)
- Fixed and improved system translations (#491)
- Added valid mime types to the bone structure (#498)
- Removed unused functions from renderers (#492)
- Added several improvements to KeyBone (`allowed_kinds`-flag, use of `singleValueFromClient`) (#493)
- Fixed `Skeleton.toDB()` to use the skeleton's class for instantiation (#487)
- Added `Skeleton.__len__()` to allow for `len(skel)` (#488)

## [3.2.4]

- Fix broken multi-language relations (#515)
- Bump protobuf from 3.20.1 to 3.20.2 (#517)
- Bump protobuf from 3.20.1 to 3.20.2 in /tests (#518)

## [3.2.3]

- Fixed setup.py requirements extraction to respect conditionals
- Fixed getReferencedBlobs of TextBone so it allows multiple=True data to be saved (#490)
- Updated viur-datastore to v1.3.2

## [3.2.2]

- Updated viur-datastore to v1.3.1

## [3.2.1]

-  Fixing invalid datetime (de)serialization for tasks (#484)

## [3.2.0]

- Added [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Use setuptools' install_requires from requirements.txt (#475)
- Implement `errors.TooManyRequests` exception (#463)
- Improved logging to cope with the new logviewer (#461)
- Added ratelimit to login with username/password (#455)
- Providing a `SortIndexBone` (#446, #453)
- Unit test suite starting with bones (#432, #466)
- Ported `IndexMannager` (sic!) and renamed to `Pagination` (#481)
- Hint when `conf["viur.debug.traceExceptions"]` is set (#480)
- Customizable ViurTagsSearchAdapter (#474)
- Use of 4-spaces instead of tabs for PEP8-conformity (#470)
- Remove unused parameter in doClearSessions (#468)
- Improved logging to cope with the new logviewer (#461)
- Improve docstrings and type hints (#458)
- Add support for `Literal` type annotations in processTypeHint (#457)
- Fix docs logo and improve maintainability of CSS (#445)
- Fixing file module (#454)
- Remove keysOnly argument from some queries and remove unused cursor (#449)
- Remove the unused cursor parameter in doClearSKeys (#438)
- PEP8-compliant naming of Bone classes (#435, #452, #471)
- Fixed missing `import copy` in KeyBone (#482)
- Fixing empty string routing to exposed functions (#479)
- Allow removing a bone in a subclass by setting it to None (#472)
- Fix downloadURLs with special characters `(`, `)` or `=` inside of filenames (#467)
- Fixed uploading files using pre-signed calls to getUploadURL (#465)
- Fixed restoring relations in edit if the referenced entity has been deleted (#460)
- Fixed seoKey handling in skeletons and fixed seoURLtoEntry (#459)
- Use of original filename when a file is downloaded (#451)
- Fixed treeNodeBone enforcing "_rootNode" suffix on it's kind (#444)
- Fixed required=True bones could still be set empty if omitted from the postdata (#440)
- Removed dbtransfer and its usage (#477)

## [3.1.4]

- Fix unused language parameter of `utils.seoUrlToEntry()` (#439)
- Subdependencies updated (#442)
- Remove class `errors.ReadFromClientError`. Replaced by the new dataclass `bones.bone.ReadFromClienError`.  (#437, #443)

## [3.1.3]

- Re-enabled getEmptyValueFunc-parameter for baseBone (without mispelling)
- Fixed textBone to be indexed=False by default
- Cleaned up some code in baseBone.__init__()

## [3.1.2]

- Manage version number in `version.py` for usage both as `__version__` and in setup.cfg (#430)
- Refactoring all bone-related `__init__` functions (#426)

## [3.1.1]

- Updated viur-datastore to v1.2.2
- Serializing stringBones with languages without prior fromClient call (#421)
- Fixed seoKeyBone failing to serialize if no languages has been set on the project (#422)

## [3.1.0]

- `viur.db.engine` config variable to inject different database drivers
- `viur.render.json.downloadUrlExpiration` config variable to specifiy the expiration of downloadUrls generated by JSON render
- Global jinja2 function "translate" for instances where compile-time resolving is not possible
- Passing getEmptyValue() in the structure definition in json-render
- Support for srcsets in textBone
- `language` paramater in `BaseSkeleton.setBoneValue()`
- Support for pypi packaging
- Re-Added translation() jinja2 function
- get() function to skeleton
- Support for overriding the fileName under wich a blob will be downloaded
- Implement baseSkel for all module prototypes (#378)
- Replaced viur.core.db by viur-datastore (#400)
- selectBone() values accept for list, tuple or callable (#390)
- Improve SEO url integration: refactoring and redirect from old keys to the current
- Allow sec-fetch-site=same-site on local development server
- Set parentnode and parentrepo before fromClient() (#402)
- files embedded in textBones don't expire anymore and get correctly locked
- Several issues in randomSliceBone
- Recursive deletion in modules/file.py
- deleteRecursive function in tree-prototype
- killSessionByUser function
- Fixes on the Tree prototype (#381)
- Fixed deferred calls with _countdown set failing when called from a cronjob (#403)
- Fixed unique=True on multiple=True relationalBones (#401)
- `setBoneValue` works now for multiple and (multiple and language) bones (#410)
- default `defaultValue` for multiple and language `selectBone`
- randomSliceBone with limit=1 returning no result
- ratelimit module
- setBoneValue to allow setting back to empty
- Adding unique=True to existing skeletons
- Logins with second factor
- conf['viur.debug.traceQueries'] flag. It has to be set on the viur-datastore config (viur.core.db.config["traceQueries"]).
- the unused `skel` parameter from singleValueUnserialize

## [3.0.3]

- child-src to addCspRule in securityheaders
- Running two deferred tasks inside the same request

## [3.0.2]

- extendCsp function for overriding the CSP-Header on a per-request basis
- support for nonces and hashes in CSP-Rules
- Supply version_id in logging entries
- Default CSP-Rules needed for login with Google have been narrowed
- Rebuilding file dervies if the file is being referenced in relations
- Distinct-filters being ignored in datastore queries
- Queries that return more than 300 entities with active dbaccelerator


## [3.0.1]

- Added validations to catch invalid recipient addresses early in sendEmail
- 'connect-src': self and 'upgrade-insecure-requests' CSP directives by default
- versionHash and appVersion variables to utils and jinja2 render 
- The ability to import blobs that have been copied client-side from the old (non cloud-storage) blobstore
- Support for custom colorprofiles in thumbnails
- [Breaking] srcSetFor function in jinja2 now needs a list with or height instead of deriving from groups
- Replaced *.ggpht.com and *.googleusercontent.com CSP directives by storage.googleapis.com
- Migrated Login with Google from Google Sign-In to Identity Services
- AdminInfo for tree modules without a leaf skel
- Referencing viurCurrentSeoKeys in relationalBones
- Helptext support in Jinja2 translation extension
- Bones with different languages can now be tested with {% if skel["bone"] %} as expected
- Querying by keybones with a list of keys
- Several bugs regarding importing data from an ViUR2 instance
- Correctly exclude non-indexed but translated bones from the datastore index
- Reenabled changelist evaluation in updateRelations
- Thumbnailer is now ignoring images PIL cannot load (eg SVGs)
- Internals resorting of values in selectBone. They will be shown in the order specified

## [3.0.0]

- Rewritten to run on Python >= 3.7
- Blobstore has been replaced with cloud store
- Serving-URLs are not supported any more. Use the derive-function from fileBones instead
- The deferred API is now based on cloud tasks
- Login with google is now based on oAuth and must be configured in the cloud console
- Support for appengine.mail api has been removed. Use the provided Send in Blue transport (or any other 3rd party) instead
- The hierarchy and tree prototype have been merged
- Support for translation-dictionaries shipped with the application has been removed. Use the viur-translation datastore kind instead
- The cache (viur.core.cache) is now automatically evicted in most cases based on entities accessed / queries run.
- Memcache support. Caching for the datastore is not supported anymore
- Full support for the dev_appserver. Now a gcp project is required for datastore/cloud store access 

[develop]: https://github.com/viur-framework/viur-core/compare/main...develop
