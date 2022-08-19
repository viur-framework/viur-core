#!/usr/bin/env python3
from unittest import mock

import importlib.util
import os
import pathlib
import sys
import unittest
from types import ModuleType

# top_level_dir is the parent-folder of "tests" and "core"
tld = pathlib.Path(__file__).resolve().parent.parent


def monkey_patch():
    """Monkey patch libs to work without google cloud environment"""
    import sys

    MOCK_MODULES = ["google.cloud.logging",
                    "google.cloud.logging_v2",
                    "google.cloud.logging.resource",
                    "google",
                    "google.cloud",
                    "google.protobuf",
                    "google.auth",
                    "google.auth.default",
                    "google.cloud.tasks_v2",
                    "google.cloud.tasks_v2.services",
                    "google.cloud.tasks_v2.services.cloud_tasks.transports",
                    "google.cloud.exceptions"]

    for mod_name in MOCK_MODULES:
        sys.modules[mod_name] = mock.Mock()

    import google
    google.auth.default = mock.Mock(return_value=(mock.Mock(), "unitestapp"))

    import logging
    class NoopHandler(logging.Handler):
        def __init__(self, *args, **kwargs):
            super().__init__(level=kwargs.get("level", logging.NOTSET))

        transport = mock.Mock()
        resource = mock.Mock()
        labels = mock.Mock()

    sys.modules["google.cloud.logging.handlers"] = tmp = mock.Mock()
    tmp.CloudLoggingHandler = NoopHandler

    sys.modules["google.cloud.logging_v2.handlers.handlers"] = tmp = mock.Mock()
    tmp.EXCLUDED_LOGGER_DEFAULTS = []

    db_attr = [
        "KEY_SPECIAL_PROPERTY", "DATASTORE_BASE_TYPES", "SortOrder", "Entity",
        "Key", "KeyClass", "Put", "Get", "Delete", "AllocateIDs", "CollisionError",
        "keyHelper", "fixUnindexableProperties", "GetOrInsert", "Query",
        "QueryDefinition", "IsInTransaction",
        "acquireTransactionSuccessMarker", "RunInTransaction",
        "startDataAccessLog", "endDataAccessLog"
    ]  # \ "config"
    viur_datastore = mock.Mock()
    for attr in db_attr:
        setattr(viur_datastore, attr, mock.Mock())
    viur_datastore.config = {}
    sys.modules["viur.datastore"] = viur_datastore

    os.environ["GAE_VERSION"] = "v42"
    os.environ["GAE_ENV"] = "unittestenv"

    original_cwd = os.getcwd()

    # top_level_dir is the parent-folder of "tests" and "core"
    tld = pathlib.Path(__file__).resolve().parent.parent

    # Change the current working dir to the parent of viur/core
    # Otherwise the core fails on skeleton.searchPath validation
    os.chdir(pathlib.Path(__file__).resolve().parent.parent.parent)

    # Create and register a dummy module as ViUR namespace
    m = ModuleType("viur")
    sys.modules[m.__name__] = m

    # Import the ViUR-core into the viur package
    spec = importlib.util.spec_from_file_location(
        "viur.core", f"{tld}/core/__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    # Change back the cwd for the unittests
    os.chdir(original_cwd)


if __name__ == "__main__":
    monkey_patch()

    # initialize the test suite
    loader = unittest.TestLoader()
    suite = loader.discover("tests", top_level_dir=str(tld))

    # initialize a runner, pass it your suite and run it
    runner = unittest.TextTestRunner(verbosity=3)
    result = runner.run(suite)
    sys.exit(int(not result.wasSuccessful()))
