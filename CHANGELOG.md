# Changelog

This file documents any relevant changes done to ViUR-core since version 3.

## [3.6.6]

- fix: Don't obfuscate any route with character replacements (#1161)
- feat: View script by path (#1156)
- fix: Make `Translation`-module `admin_info` configurable (#1158)
- fix: Support `/deploy/admin` folder as well (#1159)

## [3.6.5]

- feat: Implement `fromClient(amend=True)` feature (#1150)
- chore: Update dependencies (fix for CVE-2024-28219) (#1151)
- fix: Fix deprecated `parse_bool` call (#1149)
- fix: `list` should handle unsatisfiable queries (#1148)

## [3.6.4]

- fix: Enfore serialized values are always strings in the datastore (#1146)
- fix: RelationalBone `serialize` add super call (#1119)
- fix: Add missing import of `PIL.ImageCms` (#1144)
- fix: Re-add `StringBone`s `max_length` check (#1142)
- fix: Replace deprecated `utils.getCurrentUser` (#1139)

## [3.6.3]

- fix: Avoid `*AbstractSkel`s from being initialized (#1136)
- fix: Replace old dict `conf` access with attribute access (#1137)

## [3.6.2]

- fix: Remove comma in f-string (#1135)
- fix: target_version was always `None` (used the default version) (#1134)
- fix: Improve `List.default_order` to respect languages config (#1132)

## [3.6.1]

- fix: Add `_call_deferred`-parameter for super-calls (#1128)
- feat: Implement `translation_key_prefix` for `SelectBone` values (#1126)
- fix: Pass arguments in `JsonBone.__init__()` to `super()` call (#1129)
- fix: Improving several `User` auth method handling (#1125)
- fix: `TimeBasedOTP.start()` should use UserSkel (#1124)
- fix: Broken access to methods in `File` class by refactoring (#1122)

## [3.6.0]

- fix: Add `is None`-check for bone values with languages (#1120)
- feat: Provide `LoginSkel` on `UserPassword.login` (#1118)
- feat: `default_order` should support multiple orders as well (#1109)
- fix: Add `_prevent_compute` for computed bones (#1111)
- feat: Set icon in admin_info of translation module (#1113)
- fix: Handle non-ASCII characters in username comparison (#1112)
- fix: file module typo `UnprocessableEntity` (#1105)
- feat: Allow `None` as defaultValue in BooleanBone (#988)
- feat: Support `*`-wildcard postfix in `refKeys` for `RelationalBones` (#1022)
- feat: Implement `utils.parse.timedelta` (#1086)
- refactor: `File.getUploadURL()` (#1050)
- fix: Improving `utils` deprecation handling (#1089)
- refactor: Remove old code (#1094)
- feat: Add deprecation handling to `skeleton` (#984)
- fix: `vi.canAccess` based on fnmatch config setting (#1088)
- fix: `compute` and `unserialize_raw_value` for `JsonBone` (#1093)
- chore: Update requirements to latest patchlevels (#1091)
- feat: Add closed system (#1085)
- feat: `UserPrimaryAuthentication.next_or_finish` handler (#997)
- refactor: Replace securitykey duration with `timedelta` (#1083)
- feat: `utils.json` module / improving `JsonBone` (#1072)
- refactor: Remove `extjson`, fallback to `json` (#1084)
- feat: Require abstract `METHOD_NAME` for any `UserAuthentication` (#1059)
- feat: Allow `None` in `skel setBoneValue` (#1053)
- feat: Provide `default_order` for `List` and `Tree` (#1076)
- feat: securitykey  create duration allow timedelta (#1078)
- fix: Remove `self` from `create_src_set` (#1079)
- fix: `read_all_modules` after  #1073 and #1037 and merge 2a2b76ec16 (#1074)
- fix: Make ViUR runable again after the extremely security-relevant PR #1037 (#1075)
- fix: Remove default `P.html = True` from prototypes (#1037)
- fix: new icon naming scheme in modules (#1069)
- refactor: `tasks` module (#1016)
- fix: Use `__getattribute__` instead of `__getattr__` for super call in utils (#1065)
- fix: correctly set `refKeys` to get merged in (#1066)
- refactor: `RelationalBone`s `refKeys` and `parentKeys` as set (#1058)
- feat: Improve `UserBone` to additional defaults (#1055)
- fix: patch_user_skel (fix for #983) (#1060)
- feat: `UserAuthentication`s with skeleton patch capability (#983)
- refactor_ value for `tasks_custom_environment_handler` to new abstract class `CustomEnvironmentHandler` (#946)
- fix: f-string in `RelationalBone` introduced in #950 (#1054)
- fix: Further refactoring and fixing of `File`-module for #1046 (#1049)
- fix: Add missing import in #950 (#1048)
- refactor: Modularization of `File` (#1046)
- fix: compute for relational bones (#950)
- feat: Collect modules recursivly in `read_all_modules` (#1041)
- feat: Collect modules recursivly in `vi/config` (#995)
- fix: customize `iter_bone_value` for `NumericBone` (#1044)
- fix: Wrong f-strings introducted by #1025 (#1043)
- fix: Help and comments on `UserPassword.pwrecover` (#1042)
- feat: `clone`-action for `List` and `Tree`, recursive tree cloning (#1036)
- feat: `Skeleton.ensure_is_cloned()` (#1040)
- refactor: `Skeleton.toDB` method (#973)
- feat: Support for nested modules in `getStructure()` (#1031)
- refactor: Replace `%`-formattings by f-string (#1025)
- fix: Get rid of the catch all index behavior in vi renderer (#960)
- feat: Show project, python- and core-versions on startup (#1009)
- refactor: `Skeleton.fromDB` method (#968)
- feat: Add and improve check on root node in `Tree` prototype (#1030)
- feat: Improve translations & provide `Translation` module (#969)
- feat: Support compute for multilang and/or multiple bones (#1029)
- fix: `@property` in module causes problems during warmup (#1020)
- fix: config regression after incorrect merge 537f0e2 (#1021)
- refactor: Improved type annotations (#986)
- fix: Some more fixes for #833 (#1014)
- fix: Provide "moduleGroups" in `/vi/config` (#994)
- chore: Updating dependencies and requirements.txt
- feat: Implement `@property` support in `Skeleton`s (#1001)
- fix: Adding linter settings for flake8 as well (#998)
- feat: Refactoring and renamed `utils`, adding `utils.string.unescape` (#992)
- feat: Implement `InstancedModule` (#967)
- feat: Improved and slightly refactored `PasswordBone` (#990)
- feat: Add requirements for the memcache (#830)
- feat: Add `File.read` method (#975)
- fix: wrong conf var access (#989)
- chore: Update all requirements, bump version v3.6.0.dev3
- fix: Start explicit with `main_app` in `findBoundTask()` (#980)
- fix: Set correct stacklevel to deprecation warning on `utils.escapeString` (#981)
- fix: Admin-tool specific settings (#979)
- refactor: static skey marker (#945)
- feat: Implement migration script for new core config (#924)
- fix: `vi`-render returns wrong config (regression introduced by #833) (#977)
- fix: merge error in StringBone.singleValueFromClient
- fix: Add `try`/`except` around task emulation call (#970)
- fix: `@retry_n_times` does not work on local server during warmup (#971)
- feat: Add logging with the name of the bone where the serialization failed (#959)
- feat: Add stacklevels to `warning.warn` calls (#966)
- refactor: Replace the `replace` function with `translate` (#953)
- fix: `defaultValue` type hint in `SelectBone` (#957)
- chore: Sort and translate module names in `Rebuild Search Index` task Skeleton (#947)
- refactor: Rename `StringBone`'s `maxLength` into `max_length` (#942)
- feat: Add `min_length` to `StringBone` (#940)
- feat: use `CustomJsonEncoder` class in `json.dumps` call (#937)
- fix: invalid `conf` refactoring (#929)
- fix: Clean-up Skeletons `key` default bone (#926)
- fix: Refactor usage of `SeoKeyBone` in `Skeleton` (#927)
- feat: Provide computed `name`-bone for `Skeleton` (#925)
- feat: Add new error template with a nonce and custom image (#867)
- feat: Implement the config as a class (#833)
- feat: `utils.is_prefix`-function (#910)
- refactor: Replace `Tree.handler` by @property (#909)
- fix: Second Factor `start` (#890)
- feat: Provide `indexed`-parameter to `securitykey.create` (#886)
- fix: TimebaseOTP rename possible_user to user (#887)
- feat: `UserPrimaryAuthentication` with unified `can_handle()` (#878)
- feat: Implement `__all__` in root's `__init__` and `decorators` to support easier imports (#859)
- feat: Add missing type hints for `current` module (#871)

## [3.5.17]

- fix: Handle non-ASCII characters in username comparison (#1112)

## [3.5.16]

- chore: Dependency updates
- fix: Improvement `conf["viur.paramFilterFunction"]` (#1106)
- fix: User roles: Automatic "view" right when "edit" or "delete" is provided (#1102)

## [3.5.15]

- fix: Several improvements on `ModuleConf` (#1073)

## [3.5.14]

- fix: `current.user` unset in deferred task calls (#1067)

## [3.5.13]

- fix: `RelationalBone` locking bug (#1052)
- fix:  `_validate_request` in `tasks` (#1051)

## [3.5.12]

- feat: Provide script configuration in `ModuleConf` (#1034)
- fix: Make `UserPassword.pwrecover` ready for action-skels (#1033)

## [3.5.11]

- fix: Improve and refactor `BaseSkel.fromClient()` to handle empty/unset data (#1023)
- fix: Add check for `db.Key` in `KeyBone.singleValueFromClient` (#1008)
- fix: Provide `User.msg_missing_second_factor` customization (#1026)
- fix: Finetuning `ViurTagsSearchAdapter` defaults (#1010)
- fix: support for tasks emulator (#1004)

## [3.5.10]

- fix: handling alpha channel within thumbnail generation if icc profile is present (#1006)
- fix: Broken use of tasks emulator in combination with the app_server (#1003)
- fix: Undocumented and uninitialized `conf["viur.user.google.gsuiteDomains"]` (#1002)

## [3.5.9]

- feat: Provide `UserPassword.on_login()` hook (#987)
- fix: disable cookie's `SameSite` and `Secure` for local server (#961)

## [3.5.8]

- fix: Callable task `TaskVacuumRelations` (#963)
- fix: `exclude_from_indexes` has to be a `set` (#964)
- fix: kwargs checks must be underline (`_`) prefixed as well (#962)
- fix: Modules using `@property` crash on `_update_methods` (#952)
- fix: Support `@cache`-decorator for both functions and `Method`-instance (#948)
- fix: Invalid `maxLength` check in `StringBone` (#941)

## [3.5.7]

- fix: Update dependencies, urllib3 CVE-2023-45803 (#938)
- fix: User-module default customAction triggers require skey (#939)

## [3.5.6]

- fix: `access` in method description must not be a generator object (#936)
- fix: Always set `Secure` mode for session cookie (#931)

## [3.5.5]

- fix: Raise an `AttributeError` in case of `KeyError` in `SkeletonInstance.boneMap` (#930)
- fix: refactor `pathlist` to `path_list` (#928)
- feat: Add user admin login context (#901)

## [3.5.4]

- fix: Add `allow_empty=True` for tasks/execute (#922)
- fix: `pipenv run clean` for packaging
- docs: Improve and correct tasks docs tutorial (#915)

## [3.5.3]

- docs: Improve basics and getting started tutorials (#916)
- docs: remove old configs, fix RST-Syntax and adjustments for server->core (#913)
- docs: Fix SEO training after renaming in #800 (#912)
- docs: Improve and correct session docs (#914)
- ci: Add python 3.11 to matrix in test workflow (#917)
- chore: Downgrade urllib3 to `1.26.17` (#918)
- fix: Add `google-api-core[grpc]` and `googleapis-common-protos[grpc]` (#911)
- feat: Add a way to disable `Module.describe()` caching (#906)

## [3.5.2]

- fix: Built a standardized way for the return of errors in 2Factor (#900)
- fix: `Formmailer` expects a `skey` parameter, but it uses the `@skey` decorator (#903)
- chore: Update dependencies to latest version (#899)
- fix: Prefix `project_id` to all admin emails (#885)
- fix: Remove `@`-marker from request context destillation (#884, #888)
- fix: Downgrade debug level for emulated deferred tasks (#883)

## [3.5.1]

- fix: Accept `staticSecurityKey` from sessions created by viur-core < 3.5 (#877)
- fix: Replace unused `otpTemplate` by new `second_factor_login_template` (#876)
- fix(docs): Add and lock all docs dependencies (#875)
- fix: Remove the `style` which is reserved for template completely from the request kwargs (#870)
- fix: Re-add missing `skel.fromDB()` in `Tree.move` (#874)
- ci: Fixed codecov path

## [3.5.0]

- fix: Move warning-email "Debug mode enabled" (#869)
- fix: Add logging for raised `HTTPException` (#864)
- fix: Remove replace of `.` to `_` (#865)
- fix: Reactivate old-style `trace*CallRouting` for backward compatibility (#866)
- fix: Remove `viur.core` decorator import advise (#868)
- feat: Add `onAdd()`-hook in `User.add()` method (#863)
- fix: Include `requirements.txt` in dist wheel again (#862)
- fix: Additional fixing for `@skey(allow_empty=True)` (#861)
- fix: Re-include `templates/` folder as data-files (#858)
- fix: For #850, return skel in transaction (#857)
- fix: `html.Render.getTemplateFileName()` should be deterministic (#855)
- fix: Updating admin info stuff (#852)
- fix: @skey-requirement determination and `/user/verify` (#850)
- fix: Customizable template name for `second_factor_choice` (#845)
- fix: Clean-up user/view and user/edit with "self" (#848)
- fix: For #842, use `self.kwargs` for list parsing (#849)
- fix: mixed up and blurred methods and concepts in User.otp (#846)
- fix: Replace call to `utils.getCurrentUser()` (#847)
- fix: import qrcode's element with an alias (#844)
- refactor: Refactor `Router` & collect context-variables to `current.request.get().context` (#842)
- feat: Second factor OTP login using Authenticator App (#578)
- fix: Add default value for `token`-parameter in `GoogleAccount.login()` (#843)
- feat: Avoid multiple CSRF-security-key validation (#841)
- refactor: Use `parse_bool()` for bool Method type annotations (#840)
- feat: Implement `utils.parse_bool` (#838)
- feat: Extend `Method` to examine function signature and parse type annotations (#837)
- refactor: Prototype action functions (#831)
- refactor: Some clean-up on #800 (#828)
- feat: Add `secret` module to access values from GC secret manager (#815)
- fix: `Method.__name__` improves #800 (#827)
- fix: Add missing import on #800 (#826)
- feat: Implement a new `Module`/`Method` concept with new decorators (#800)
- feat: Implement `retry_n_times` decorator (#655)
- refactor: Refactor password recovery process in stock `User`-module (#682)
- chore: Update pipenv and requirements.txt (#824)
- fix: Update `PasswordBone`s test_threshold and its structure rendering  (#823)
- fix: `renderEditForm` failed when `ignore` or `bone` was None (#819)
- fix: `Tree.getRootNode` failed when parentrepo was None (#818)
- feat: custom actions for user maintenance and debug triggers (#712)
- feat: Add `bones` parameter for `renderEditForm` (#812)
- refactor: User-module `TimeBasedOTP` (#802)
- feat: Implement natural sorting in `StringBone` (#809)
- feat: Implement a `PeriodicTask` to check the remaining SIB email quota (#808)
- chore: Upate viur-datastore (#814)
- fix: Add 'session_bound=False' for the skey during email verification (#810)
- fix: docs configuration after #804 (#807)
- refactor: Package and folder layout (#804)
- refactor: Changed package folder layout
- fix: pillow replaces `Image.ANTIALIAS` by `Image.LANCZOS`
- fix: guessTimeZone() fails with Python 3.11 (#789)
- feat: Make recipients for `sendEMailToAdmins` configurable (#798)
- test: Update test-suite Pipfile and add tests for `DateBone` (#797)
- refactor: Improving `DateBone.singleValueFromClient()` (#733)
- refactor: `singleValueFromClient` with type hints and docstrings (#685)
- docs: fixed all Auto-API build Errors (#783)
- feat: Compute `creationdate` and `changedate` using the new `compute`-feature (#785)
- fix: Add `Count` to db.__all__ (#792)
- feat: Improve `BaseBone._compute` function (#786)
- docs(build): set sphinx to an older version (as in the Pipfile) to get the build working again (#784)
- feat: Add `compute`-feature to `BaseBone` (#639)
- docs: Improve type hints in sphinx (#746)
- docs: fixed toctree problems (#781)
- docs: Tutorials for preliminaries and initial setup (#765)
- feat: Extend User module to built-in role system (#736)
- feat: Rewrite of session-based securitykeys (#764)
- chore: Support for Python 3.11 (#767)
- perf: Avoid structure rendering in JSON render list (#774)
- feat: Delete old pending `FileSkeletons` (#739)
- feat: Add search for error template in `html/error` (#658)
- fix: `File.getUploadURL` with HttpExceptions (#743)
- feat: Set `cls` to `CustomJsonEncoder` in Jinja's `json.dumps_kwargs` (#744)
- fix: __undefined to _undefined (#737)
- fix: Remove leading `Subject: ` from task notify emails (#740)
- fix: readd StringBone type (#738)
- chore: Rename `__systemIsIntitialized_` into `__system_initialized` (#730)
- chore: Rename `__undefindedC__` into `__undefined` (#731)
- chore: Rename all `rawValue`-parameters to just `value` (#732)
- docs: Documentation for entire `bones`-module (#723)
- docs: Add more selectors to theme.css to list styling from latest rdt theme (#729)
- docs: Watch the normal python code path in the doc build watcher too (#728)
- docs: Set language in readthedocs config and add jQuery (#721)
- docs: removed hierarchyBone, changed to Python 3.10+ and removed wiki and community landing page (#707)
- fix: `CredentialBone` without escaping (#702)
- chore: Improve `StringBone` (#714)

## [3.4.8]

- chore: Update viur-datastore to 1.3.11 (#814)

## [3.4.7]

- chore: Update viur-datastore to 1.3.10 (#805)

## [3.4.6]

- fix(seo): Incoming url is compared wrong (#801)

## [3.4.5]

- fix: Add missing fallback for `NumericBone.refresh()` destroying valid data (#793)
- fix: `getCurrentUser()` should clone `current.user` for use with Jinja (#791)
- fix: Extend MetaBaseSkel reserved keywords to "structure" (#788)
- chore: Reject pointless `BooleanBone(multiple=True)` (#773)

## [3.4.4]

- chore: Update dependencies (#762)
- fix: Missing german translation for "password too short" message (#763)
- fix: ensure the correct default defaultValue of a multiple/multi-lang `BooleanBone` (#759)
- fix: Move super-call in `JsonBone.__init__()` to the begin (#758)

## [3.4.3]

- fix: #747 broke vi-renderer

## [3.4.2]

- fix: Fixes TypeError when password is unset (#748)
- fix: `DateBone.fromClient()` should regard tzinfo (#749)
- feat/fix: Allow `duration` argument for skey (#751)
- fix: `CredentialBone` without escaping (#702) (#750)
- fix: Add path_list to the __init__ of BrowseHandler (#747)

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
