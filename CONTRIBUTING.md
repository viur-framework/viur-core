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

## Coding Convention

* Fundamentally, we try to follow [PEP 8](https://peps.python.org/pep-0008).
  Old code syntax, will be updated gradually so that there are only few breaking changes.
  * `snake_case` for variables, filenames, bone names
  * `PascalCase` for classes
  * `UPPER_CASE_WITH_UNDERSCORE` for constants, enums
* We use the [Sphinx docstring format](https://sphinx-rtd-tutorial.readthedocs.io/en/latest/docstrings.html#the-sphinx-docstring-format).
  Apart from that we follow [PEP 257](https://peps.python.org/pep-0257)
* bone names and skeletons should be written in Singular -- even if they are `multiple=True`
* _Skeleton_ classes should end with `Skel`, not `Skeleton`
* We use double quotes (`"`) for strings. Except, if we have to write a string inside an f-string
* We write bones always multiline; One line per argument
* Multiline dicts, lists and bones should end with a trailing comma `,` like
  ```py
  data = {
    "foo": 1,
    "bar": 2,  # <-- add here always a comma!
  }
  ```
* type hints should always be used everywhere. We do not write additional type definitions in the docstring.
  ```py
  # We import the `typing` module only aliased as the shorthand `t`:
  import typing as t

  # Furthermore we prefer generics over the typing types
  def the_preferred_way(data: dict[str, list[int]]) -> set[str]: ...
  def please_not_like_this(data: t.Dict[str, t.List[int]]) -> t.Set[str]: ...

  # If the types support it, we use the merge operator `|` (pipe) instead of t.Union
  MULTIPLE_TYPES_ALLOWED = list[str | int | db.Key]
  ```


## Documentation

Please document your changes and provide info in any form you can. We have established a documentation taskforce that takes care of chasing information from core developers, organizing and building the docs with sphinx/readthedocs. If you implement a feature or change, you can dump your documentation in the pull request and tag it accordingly ('doc-review' tag), so you do not need to waste time learning restructured text for sphinx or even correct English. The documentation team will pick up your text, translate and polish it so you can concentrate on coding and explaining in your own words.

## Versioning

`viur-core` uses the semantic versioning scheme.<br>
Any `major.minor.bugfix` release is being published to [PyPI](https://pypi.org/project/viur-core).

Furthermore, the following rules provided in [PEP-440](https://peps.python.org/pep-0440/#pre-releases) apply to pre-releases which are also made available to PyPI for open tests.

- `devN` for development and test releases (including release tests, may be broken)
- `alphaN` for feature-incomplete alpha releases
- `betaN` for feature-completed beta releases
- `rcN` for release-candidates, where bugs may be fixed

In all cases, `N` is a number counted upwards for every pre-release kind.

## Dependency management

`viur-core` has several dependencies, which are maintained in [`pyproject.toml`](/pyproject.toml).<br>
Please keep external dependencies low.

## Releasing

In case you have appropriate permissions, a release can be done this way:

- Bump version number in `src/viur/core/version.py`
- Update [`CHANGELOG.md`](/CHANGELOG.md) and also check version number there
  - To quickly generate a changelog, run `git log --pretty="- %s" main..develop`
  - todo: Changelog shall be generated automatically later.
- Build and publish the package (ensure `pipenv install` was run before and is up-to-date)
  - Ensure any old files are deleted by running `pipenv run clean`
  - Build the wheel using `pipenv run build`
  - Release the package `pipenv run release`
- When all went well, commit and create a tag equally to the version number in `src/viur/core/version.py`
- Finally, make sure all hotfixes from `main` are in `develop` as well (`git checkout develop && git pull && git merge main`)

## Branches

`viur-core` has currently 4 actively maintained branches.

- 1. **3.5** is the current stable LTS version as released on PyPI (3.5.x)
- 2. **3.6** is the current stable LTS version as released on PyPI (3.6.x)
- 3. **main** is the current version as released on PyPI (3.7.x)
- 4. **develop**  is the next minor version and may be released as release candidates to PyPI (3.8.x)

Pull request should be made against one of these branches.

## Maintenance

Maintainer of this project is [@phorward](https://github.com/phorward).
