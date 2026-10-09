"""Pin the uploaded release bytes and fail closed on unsafe dispatch inputs."""

import hashlib

import pytest
from scripts.verify_pypi_release import (
    validate_artifacts,
    validate_release_ci,
    validate_request,
)

from tests.test_release_integrity import artifacts, checksum_manifest


@pytest.mark.parametrize("tag", ["2.0.0", "v2.00.0", "v2.0.0$(false)", "v2.0.0+local", "--help", "../v2.0.0"])
def test_unsafe_version_rejected(tag):
    with pytest.raises(ValueError):
        validate_request(tag, "a" * 40, "b" * 64)


@pytest.mark.parametrize("commit,checksum", [("main", "b" * 64), ("a" * 40, "wrong"), ("a" * 39, "b" * 64)])
def test_unpinned_inputs_rejected(commit, checksum):
    with pytest.raises(ValueError):
        validate_request("v2.0.0", commit, checksum)


def test_pinned_inputs_pass():
    assert validate_request("v2.0.0", "a" * 40, "b" * 64) == "2.0.0"


def test_checksum_manifest_replacement_rejected(tmp_path):
    source, dist = artifacts(tmp_path)
    checksum_manifest(dist)
    digest = hashlib.sha256((dist / "SHA256SUMS.txt").read_bytes()).hexdigest()
    validate_artifacts(source, dist, "v1.3.0", digest)
    # Replacing both an artifact and its checksum must still fail the reviewed pin.
    with next(dist.glob("*.whl")).open("ab") as stream:
        stream.write(b"changed")
    checksum_manifest(dist)
    with pytest.raises(ValueError, match="changed since review"):
        validate_artifacts(source, dist, "v1.3.0", digest)


def test_failed_latest_ci_cannot_be_hidden_by_an_older_success():
    run = {"path": ".github/workflows/ci.yml", "head_sha": "a" * 40,
           "event": "push", "head_branch": "main", "status": "completed"}
    payload = {"workflow_runs": [{**run, "conclusion": "failure"}, {**run, "conclusion": "success"}]}
    with pytest.raises(ValueError, match="latest"):
        validate_release_ci(payload, "a" * 40)


@pytest.mark.parametrize("change", [{"event": "pull_request"}, {"head_branch": "dev"},
                                     {"head_sha": "b" * 40}, {"status": "in_progress"}])
def test_wrong_or_pending_ci_rejected(change):
    run = {"path": ".github/workflows/ci.yml", "head_sha": "a" * 40, "event": "push",
           "head_branch": "main", "status": "completed", "conclusion": "success", **change}
    with pytest.raises(ValueError):
        validate_release_ci({"workflow_runs": [run]}, "a" * 40)


def test_successful_source_ci_accepted():
    run = {"path": ".github/workflows/ci.yml", "head_sha": "a" * 40, "event": "push",
           "head_branch": "main", "status": "completed", "conclusion": "success"}
    validate_release_ci({"workflow_runs": [run]}, "a" * 40)
