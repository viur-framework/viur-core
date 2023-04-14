# This is the place where the viur-core version number is defined;
# For pre-releases, postfix with ".betaN" or ".rcN" where `N` is an incremented number for each pre-release.
# This will mark it as a pre-release as well on PyPI.

__version__ = "3.4.0.rc1"
assert __version__.count(".") == 3  # semantic version number is mandatory!
