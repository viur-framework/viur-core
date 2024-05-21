<div align="center">
    <img src="https://github.com/viur-framework/viur-artwork/raw/main/icons/icon-core.svg" height="196" alt="A hexagonal logo of the viur-core" title="viur-core">
    <h1>viur-core</h1>
    <a href="https://github.com/viur-framework/viur-core/actions/workflows/python-test.yaml">
        <img src="https://github.com/viur-framework/viur-core/actions/workflows/python-test.yaml/badge.svg" alt="Badge for Python test suite" title="Python test suite">
    </a>
    <a href="https://core.docs.viur.dev/en/main/">
        <img src="https://readthedocs.org/projects/viur-core/badge/?version=main" alt="Badge for readthedocs.org build status" title="readthedocs.org/viur-core">
    </a>
    <a href="https://pypi.org/project/viur-core/">
        <img alt="Badge showing current PyPI version" title="PyPI" src="https://img.shields.io/pypi/v/viur-core">
    </a>
    <a href="https://github.com/viur-framework/viur-core/blob/main/LICENSE">
        <img src="https://img.shields.io/github/license/viur-framework/viur-core" alt="Badge displaying the license" title="License badge">
    </a>
    <br>
    This is the core component of the <a href="https://www.viur.dev">ViUR framework</a>.
</div>

## About

ViUR is an application development framework for the Google App Engine™.

ViUR was developed to meet the needs and requirements of both designers and developers. It provides a clear concept for the implementation of agile data management software systems. It is written in Python™ and has already attracted a growing community that is constantly supporting and improving ViUR.

## Getting started

To get started with ViUR, check out [viur-base](https://github.com/viur-framework/viur-base). It comes with a pre-configured and well documented project template to immediately start with.

## Migration

### from `<=v3.5` to `v3.6`
In [#833](https://github.com/viur-framework/viur-core/pull/833) the config has
changed from a dict to an object.
To migrate the access expressions like `conf["option"]` in your project
to `conf.option` the viur-core provides a migration script.
Install the _viur-core_ in your project, open a (virtual) environment shell
and `viur-core-migrate-config` will be available.
After checking the result with `viur-core-migrate-config ./deploy/ -d`
you can apply the changes with `viur-core-migrate-config ./deploy/ -x`.

## Contributing

Help of any kind to extend and improve or enhance this project in any kind or way is always appreciated.

We take great interest in your opinion about ViUR. We appreciate your feedback and are looking forward to hear about your ideas. Share your vision or questions with us and participate in ongoing discussions.

See our [contribution guidelines](CONTRIBUTING.md) for details.

## License

Copyright © 2024 by Mausbrand Informationssysteme GmbH.<br>
Mausbrand and ViUR are registered trademarks of Mausbrand Informationssysteme GmbH.

Licensed under the MIT license. See LICENSE for more information.
