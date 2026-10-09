---
title: Release version integrity
description: Understand kube-saver tag, source, package and CLI version checks, explicit publication guards, and
  the historical version mismatch.
---

# Release version integrity

Release tags must match `src/kube_saver/version.py`, wheel/sdist metadata,
the embedded version files, and the installed CLI. The CI `release-check` job
verifies those values, artifact filenames, and SHA256 checksums on every run.
Versions use canonical `major.minor.patch`, optionally followed by `aN`, `bN`,
`rcN`, or `.postN`; local-version suffixes are rejected because the same version
is used in Docker tags.

## Build-only runs

Normal pushes, pull requests, and manual dispatches with `publish_release: false`
build and test artifacts without publishing them. The manual option defaults to
false. Release and Docker publishing also require successful wheel and Docker
smoke jobs. Every checkout is pinned to the triggering commit SHA, including
PR merge commits. The workflow defaults to a read-only repository token; only
the gated release job receives `contents: write`. Publishing runs are serialized
and an in-progress publication is not automatically cancelled.

## Publishing a future release

After reviewing the intended version, updating the source version, and completing
the [release testing procedure](release-testing.md):

1. Obtain approval to create the new tag and publish the release.
2. Create `v<source-version>` at the approved `main` commit.
3. Dispatch CI on `main` with that exact `release_tag` and `publish_release: true`.
4. CI checks that the existing tag points to the checked commit and validates
   source, wheel, sdist and CLI versions before any publishing job runs. Downloaded
   assets and the current remote tag are checked again in the release job; the
   remote tag is also checked before Docker publication.
5. GitHub release creation fails if the release already exists. Docker publishing
   runs only after successful creation of the new GitHub release, loading the exact
   Linux/amd64 image that passed kind smoke checks instead of rebuilding it.

The workflow does not automatically create tags or publish on tag pushes. An
existing release is not edited on retry. If Docker publishing fails after a new
GitHub release is created, investigate and obtain approval for recovery rather
than expecting a full-workflow rerun to edit that release.

A remote tag could still be moved by another authorized actor between its last
check and publication. Before publishing, protect release tags against updates
and deletion with repository rules. Those settings are outside this PR. GitHub
and Docker publication are separate operations: a Docker push can fail after a
GitHub release exists, or after only one Docker tag was updated. Recovery needs
separate approval. The one-day tested-image artifact retention also limits
late job reruns; do not rerun publishing jobs without checking what already exists.

## Historical mismatch

As reviewed on 2026-10-08 UTC, the published `v1.8.0` release has wheel/sdist
assets named `1.3.0`, and current source also reports `1.3.0`. The source/tag
history alone cannot establish the intended next version. Preserve historical
releases; decide the next version and any historical correction separately.

## Local validation

Install the built wheel in a clean environment before checking CLI identity:

```bash
python -m pip install dist/*.whl
sha256sum dist/*.whl dist/*.tar.gz > dist/SHA256SUMS.txt
python scripts/verify_release.py --dist-dir dist --require-checksums
# When preparing a release, add --tag v<source-version>
```

This script only reads local files and invokes the version command. It does not
create a tag, upload assets, or contact a publishing API.
