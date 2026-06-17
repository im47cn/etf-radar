#!/usr/bin/env bash
# 一次性启用仓库共享的 git hooks (.githooks/).
# 等价于: git config core.hooksPath .githooks
set -eu
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
echo "OK: git core.hooksPath = $(git config core.hooksPath)"
echo "Active hooks:"
ls -1 .githooks/ | sed 's/^/  - /'
