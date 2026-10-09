#!/usr/bin/env bash
# Read-only check: the remote tag must still identify the tested event commit.
set -euo pipefail
tag=${1:?release tag required}
expected=${2:?tested commit required}
git check-ref-format "refs/tags/$tag"
[[ "$tag" == v* && ${#tag} -le 128 && "$expected" =~ ^[0-9a-f]{40}$ ]] || exit 1
refs=$(git ls-remote --exit-code origin "refs/tags/$tag" "refs/tags/$tag^{}")
commit=$(printf '%s\n' "$refs" | awk '$2 ~ /\^\{\}$/ {print $1}')
if [[ -z "$commit" ]]; then
  commit=$(printf '%s\n' "$refs" | awk -v ref="refs/tags/$tag" '$2 == ref {print $1}')
fi
if [[ "$commit" != "$expected" ]]; then
  echo 'Remote release tag must point to the tested event commit.' >&2
  exit 1
fi
