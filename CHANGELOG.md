# Changelog

This file documents any relevant changes done to ViUR Core since version 3.0.0.
For the 2.x changelog see the [viur/server](https://github.com/viur-framework/server) repository


## [develop] - Current development version

## Added
- Added validations to catch invalid recipient addresses early in sendEmail
- 'connect-src': self and 'upgrade-insecure-requests' CSP directives by default
- versionHash and appVersion variables to utils and jinja2 render 
- The ability to import blobs that have been copied client-side from the old (non cloud-storage) blobstore

## Changed
- [Breaking] srcSetFor function in jinja2 now needs a list with or height instead of deriving from groups
- Replaced *.ggpht.com and *.googleusercontent.com CSP directives by storage.googleapis.com
- Migrated Login with Google from Google Sign-In to Identity Services


### Fixed
- AdminInfo for tree modules without a leaf skel
- Referencing viurCurrentSeoKeys in relationalBones
- Helptext support in Jinja2 translation extension
- Bones with different languages can now be tested with {% if skel["bone"] %} as expected
- Querying by keybones with a list of keys
- Several bugs regarding importing data from an ViUR2 instance
- Correctly exclude non-indexed but translated bones from the datastore index
- Reenabled changelist evaluation in updateRelations

### Removed
- Internals resorting of values in selectBone. They will be shown in the order specified

## [3.0.0]

### Changed
- Rewritten to run on Python >= 3.7
- Blobstore has been replaced with cloud store
- Serving-URLs are not supported any more. Use the derive-function from fileBones instead
- The deferred API is now based on cloud tasks
- Login with google is now based on oAuth and must be configured in the cloud console
- Support for appengine.mail api has been removed. Use the provided Send in Blue transport (or any other 3rd party) instead
- The hierarchy and tree prototype have been merged
- Support for translation-dictionaries shipped with the application has been removed. Use the viur-translation datastore kind instead
- The cache (viur.core.cache) is now automatically evicted in most cases based on entities accessed / queries run.

### Removed
- Memcache support. Caching for the datastore is not supported anymore
- Full support for the dev_appserver. Now a gcp project is required for datastore/cloud store access 

[develop]: https://github.com/viur-framework/viur-core/compare/master...develop

