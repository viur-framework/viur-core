# Contribution guidelines

Thanks that you want to contribute to ViUR!

## Issues

In case you encounter a bug, or you miss a feature, please [file an issue](https://github.com/viur-framework/viur-core/issues/new).

## Pull Requests

If you created a solution for a problem or added a feature, please make a pull request.
This can also be done as a draft, in case you want to discuss a change or aren't finished.

## Versioning

viur-core uses the semantic versioning scheme.
Any major/minor/bugfix release is being published to PyPI.
A pre-release is marked as "rc" for release-candidate and is also published.

# Release

In case you have appropriate permissions, a release can be done this way:

- Make sure all hotfixes from `main` are in `develop` as well (`git merge main`)
- Bump version number in `core/version.py`
  - For a release-candidate, add `-rcN` to the version number, and count N up.
- Update `CHANGELOG.md` and also check version number there
  - To quickly generate a changelog, run `git log --pretty="- %s" main..develop`
  - todo: Changelog shall be generated automatically later.
- Build and publish the package
  - Run `pipenv install` once
  - Ensure any old files are deleted by running `pipenv run clean`
  - Build the wheel using `pipenv run build`
  - Release the package
    - PyPI: `pipenv run release`
    - TestPyPI: `pipenv run develop`
- When all went well, finally create a tag equally to the version number in `core/version.py`
- In case this is a new minor release, remove all release candidate tags using
  ```
  for i in `git tag`; do if [[ $i == *-rc* ]]; then git tag -d $i; git push origin :$i; fi; done
  ```

## Branches

viur-core has two branches:

- **main** is the current stable version as released on PyPI.
- **develop**  is the next minor version and may be released as release candidates to PyPI.

## Maintenance

Maintainer of this project is [@phorward](https://github.com/phorward).