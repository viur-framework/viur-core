# Changelog for the ViUR Server (https://github.com/viur-framework/server)


## [Unreleased]

## [2.1.0] - 2017-10-25

### Added
 - New edit form templates following the ViUR ignite standard
 - Pass the error description of HTTPException to the underlying webob framework
 - ignore/hide parameter to our renderEditForm jinja2 function
 - New parameter "params" to explicitly pass additional values to the template / json response
 - Retrieving the viewSkel Structure by calling modulePath/view/structure
 - \_\_iter\_\_ function to skeletons
 - embedSvg function to html render
 - onLogout hook to the user module
 - Expose the unique property in skel-structures in json render
 - viur.emailHandler config variable for easy integration of 3rd party email services

### Changed
 - Pre-translate the descriptions of selectOne/selectMulti bones in add or edit calls (as done in views)
 - Listing and calling user-callable tasks is now also possible for the vi render
 - Internally switched to more efficient membership tests for dicts
 - userBones with creation- or update-magic set are not forced to be invisible anymore
 - Don't set skel["key"] to None if skel.delete() is called
 - Relational bones can now include properties from ref-/rel-skel bones in search indexes
 - Setting update- or creation-magic on userBones don't force them to be invisible anymore
 - *[Breaking]* Internal representation of relations are now dicts, not instances of Ref- or Rel-Skels

### Fixed
 - handle ValueError in int() or float() in numericBone:buildDbFilter
 - serializing a textBone failing in getSearchDocumentFields if valuesCache[name] is None
 - Correctly handle None values in numericBones getSearchDocumentFields()
 - Added missing imports to dbtransfer.py
 - Several issues with writing search api indexes for relationalBones
 - Usage of old Skeleton-API in orders module
 - Users without access to the vi/admin render couldn't logout using these renders
 - Call setSystemInitialized on all skeletons (not only skels having kindName set)
 - Type-mismatch in html-render causing errors if a RelSkel is present
 - Parsing dates containing non-unicode characters

### Removed
 - *[Breaking]* "key"-Parameter from skeleton.setValues()


## [2.0.3] - 2017-08-30

### Changed
 - If URL-Based language method is used and none is set, also evaluate X-Appengine-Country as a hint which language should be used 
 - Descriptions of selectOne/selectMultiBone are now translated before passed to the template
 
### Fixed
 - Prevent an exception if querying an selectOneBone which has an empty values dict
 - Clone function in hierarchy moving entries instead of duplicating them


## [2.0.2] - 2017-05-19

### Added
 - Santy-Check for secret keys in timebased otp (check for even string length)

### Changed
 - setBoneValue for relationalBone now also accepts encoded datastore keys in unicode
 - Deferred tasks are not called with \_\_undefinedFlag\_\_ as first argument if no other args had been given anymore

### Fixed
 - Spaces being removed around tag boundaries in textBone
 - boneWasInvalid marker always being true
 - Fixed %B and other localizions not working on dateBones with localized=True
 - Html-Render selecting the correct template for timebased otp
 - Deselecting every option in selectMultiBone is possible agian
 - relationalBone erroneously raising the "Use [] to access your bones" safeguard
 - Unserializing of bones sharing the same name-prefix
 - CaptchaBone

 
## [2.0.1] - 2017-01-04

### Added
 - IDs of entries tranferred with dbtransfer are now marked as in-use inside the datastore
 - conf["viur.cacheEnvironmentKey"] can now raise RuntimeError to indicate that this request cannot be cached
 - Added the render attribute to BasicApplications

### Changed
 - getEntry in html-render now evaluates canView() if present
 - Reduced batch-size in rebuildSearchIndex to 25 and made exceptions raise
 - Setting a bone to None is now equivalent of deleting it from the skeleton 

### Fixed
 - Values not part of the subskel currently written are preserved again
 - Supplying a key from a different module doesn't cause an server error anymore
 - Fixed password-recovery function in auth_userpassword
 - Correctly set clearUpdateTag on rebuildSearchIndex
 - FileBone and FileSkel are now refreshing the servingUrl on rebuildSearchIndex again
 - Ensure that year is always >= 1900 in dateBone:fromClient

 
## [2.0.0] - 2016-12-22

### (Start of changelog)
