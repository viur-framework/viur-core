#!/usr/bin/env bash
# Usage: scripts/release.sh
# Releases the current branch: bumps the patch level, adds a CHANGELOG.md entry, commits and tags. Does not push.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

f=src/viur/core/version.py
old=$(sed -nE 's/^__version__ = "(.*)"/\1/p' "$f")
new="${old%.*}.$(( ${old##*.} + 1 ))"

log=$(git log --no-merges --pretty="- %s" "v$old.." | grep -v "^- Bump version" | sort || true)
[ -n "$log" ] || { echo "No changes since v$old"; exit 1; }

sed -i "s/^__version__ = \"$old\"/__version__ = \"$new\"/" "$f"

# insert the new section before the first "## [" heading
awk -v e="## [$new]\n\n$log\n" '!d && /^## \[/ {print e; d=1} 1' CHANGELOG.md > CHANGELOG.md.tmp \
    && mv CHANGELOG.md.tmp CHANGELOG.md

# review and edit the changelog before committing
${EDITOR:-vi} CHANGELOG.md

git commit -am "Bump version $new"
git tag "v$new"
echo "Done. To publish: git push && git push origin v$new"
