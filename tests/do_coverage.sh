#!/usr/bin/env sh

set -ex

# Ensure we're in the *tests* dir
cd "$(dirname "$0")"

# clean up
coverage erase
rm -rf htmlcov
# generate coverage
coverage run -m unittest discover
coverage report
coverage html
coverage-badge -fo coverage.svg
# use relative paths
find ./htmlcov/ -type f -exec \
	sed -i 's:'$(dirname $(pwd))'/core/::g' {} +
# serve files
python -m http.server 4242 -d htmlcov
