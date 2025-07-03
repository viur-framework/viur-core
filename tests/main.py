#!/usr/bin/env python3
import pathlib
import sys
import unittest

# top_level_dir is the parent-folder of "tests" and "core"
tld = pathlib.Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    # initialize the test suite
    loader = unittest.TestLoader()
    suite = loader.discover("tests", top_level_dir=str(tld))

    # initialize a runner, pass it your suite and run it
    runner = unittest.TextTestRunner(verbosity=3)
    result = runner.run(suite)
    sys.exit(int(not result.wasSuccessful()))
