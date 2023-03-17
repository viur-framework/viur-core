# Contribution guidelines

Thanks that you want to contribute to ViUR!

## Issues

In case you encounter a bug, or you miss a feature, please [file an issue](https://github.com/viur-framework/viur-core/issues/new).

## Pull Requests

If you created a solution for a problem or added a feature, please make a pull request.
This can also be done as a draft, in case you want to discuss a change or aren't finished.

### Conventional Commits

When creating a pull request, try to follow the [Conventional Commit](https://www.conventionalcommits.org) paradigm.
This is also part of the pull requests naming scheme, as pull requests are usually squash merged.

| Type | | SemVer |
| --- | --- | --- |
| any of following types | - A commit that has a footer:<br />`BREAKING CHANGE: <description>`<br /><br />AND/OR<br /><br /> - A commit that has a ! after the type or optional scope:<br />`<type>[optional scope]!: <description>`  |    `MAJOR`<br />Breaking Change |conventional commit
| `feat` | A new feature, introducing a new feature to the codebase | `MINOR` |
| `fix`  | A bug fix, patching a bug in your codebase | `PATCH` |
| `refactor` | A change that neither fixes a bug nor adds a feature | - |
| `docs` | Documentation only changes | - |
| `style` | Changes that do not affect the meaning of the code (white-space, formatting, missing semi-colons, etc) | - |
| `perf` | A code change that improves performance | - |
| `test` | Adding missing or correcting existing tests | - |
| `chore` | Changes to the build process or auxiliary tools and libraries such as documentation generation | - |
| `ci` | Changes to the continuous integration | - |
| `build` | Changes to the build process or code generation | - |

Visit [Vahid Hallaji's Blog](https://hallaji.com/blog/summary-of-conventional-commits) for a nice a short explanation.

### Review

ViUR needs you! All developers are invited to review pull requests, so we can merge PRs as soon as possible and make changes according to our standards and that only works, if people help out.
If you are not on the reviewers list, just add yourself or ask a maintainer to configure access for you.

If there are documentation changes to review, there should be a 'doc-review' tag added to the issue or pull request

## Documentation

Please document your changes and provide info in any form you can. We have established a documentation taskforce that takes care of chasing information from core developers, organizing and building the docs with sphinx/readthedocs. If you implement a feature or change, you can dump your documentation in the pull request and tag it accordingly ('doc-review' tag), so you do not need to waste time learning restructured text for sphinx or even correct English. The documentation team will pick up your text, translate and polish it so you can concentrate on coding and explaining in your own words.

## Versioning

`viur-core` uses the semantic versioning scheme.<br>
Any `major.minor.bugfix` release is being published to [PyPI](https://pypi.org/project/viur-core).

Furthermore, the following rules apply to hidden pre-releases which are also made to PyPI for open tests.

- Release candidates which are almost feature-complete is given a suffix named `-rcN`.
- Beta versions with incomplete features is given a suffix named `-betaN`.

In both cases, `N` is a number counted upwards for every pre-release.

## Releasing

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

## Branches

`viur-core` has two actively maintained branches:

- **main** is the current stable version as released on PyPI.
- **develop**  is the next minor version and may be released as release candidates to PyPI.

## Maintenance

Maintainer of this project is [@phorward](https://github.com/phorward).
