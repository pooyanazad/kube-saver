"""Release metadata mismatches must fail before publishing."""

import io
import tarfile
import zipfile

import pytest
from scripts.verify_release import verify_release


def artifacts(tmp_path, wheel="1.3.0", sdist="1.3.0", embedded="1.3.0"):
    source = tmp_path / "version.py"
    source.write_text('VERSION = "1.3.0"\n')
    dist = tmp_path / "dist"
    dist.mkdir()
    with zipfile.ZipFile(dist / "kube_saver-1.3.0-py3-none-any.whl", "w") as z:
        z.writestr("kube_saver.dist-info/METADATA", f"Name: kube-saver\nVersion: {wheel}\n")
        z.writestr("kube_saver/version.py", f'VERSION = "{embedded}"\n')
    with tarfile.open(dist / "kube_saver-1.3.0.tar.gz", "w:gz") as t:
        for name, text in (
            ("kube_saver/PKG-INFO", f"Name: kube-saver\nVersion: {sdist}\n"),
            ("kube_saver/src/kube_saver/version.py", f'VERSION = "{embedded}"\n'),
        ):
            entry = tarfile.TarInfo(name)
            data = text.encode()
            entry.size = len(data)
            t.addfile(entry, io.BytesIO(data))
    return source, dist


def test_matching_versions_and_tag_pass(tmp_path):
    source, dist = artifacts(tmp_path)
    assert verify_release(source, dist, "kube-saver 1.3.0\n", "v1.3.0") == "1.3.0"


@pytest.mark.parametrize("dimension", ["wheel", "sdist", "embedded"])
def test_mismatching_artifact_rejected(tmp_path, dimension):
    source, dist = artifacts(tmp_path, **{dimension: "1.8.0"})
    with pytest.raises(ValueError, match="artifact version mismatch"):
        verify_release(source, dist, "kube-saver 1.3.0")


def test_historical_mismatch_rejected(tmp_path):
    source, dist = artifacts(tmp_path)
    with pytest.raises(ValueError, match="does not match source"):
        verify_release(source, dist, "kube-saver 1.3.0", "v1.8.0")


def test_installed_cli_mismatch_rejected(tmp_path):
    source, dist = artifacts(tmp_path)
    with pytest.raises(ValueError, match="CLI version mismatch"):
        verify_release(source, dist, "kube-saver 1.2.0")


def test_extra_artifact_rejected(tmp_path):
    source, dist = artifacts(tmp_path)
    (dist / "stale.whl").write_bytes(b"")
    with pytest.raises(ValueError, match="exactly one"):
        verify_release(source, dist, "kube-saver 1.3.0")


@pytest.mark.parametrize("kind", ["whl", "tar.gz"])
def test_renamed_artifact_rejected(tmp_path, kind):
    source, dist = artifacts(tmp_path)
    artifact = next(dist.glob(f"*.{kind}"))
    artifact.rename(dist / artifact.name.replace("1.3.0", "1.8.0"))
    with pytest.raises(ValueError, match="filename"):
        verify_release(source, dist, "kube-saver 1.3.0")


def checksum_manifest(dist):
    import hashlib
    (dist / "SHA256SUMS.txt").write_text("".join(
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  dist/{p.name}\n"
        for p in sorted(dist.iterdir()) if p.name != "SHA256SUMS.txt"
    ))


def test_tampered_artifact_rejected(tmp_path):
    source, dist = artifacts(tmp_path)
    checksum_manifest(dist)
    assert verify_release(source, dist, "kube-saver 1.3.0", require_checksums=True)
    with next(dist.glob("*.whl")).open("ab") as stream:
        stream.write(b"tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_release(source, dist, "kube-saver 1.3.0", require_checksums=True)


@pytest.mark.parametrize("manifest", [None, "../outside.whl", "duplicates", "extra"])
def test_missing_or_unsafe_checksum_manifest_rejected(tmp_path, manifest):
    source, dist = artifacts(tmp_path)
    if manifest is not None:
        checksum_manifest(dist)
        p = dist / "SHA256SUMS.txt"
        content = p.read_text()
        if manifest == "duplicates":
            content += content
        elif manifest == "extra":
            content += "0" * 64 + "  dist/extra.txt\n"
        else:
            content = content.replace("dist/kube_saver-1.3.0-py3-none-any.whl", manifest)
        p.write_text(content)
    with pytest.raises(ValueError):
        verify_release(source, dist, "kube-saver 1.3.0", require_checksums=True)


@pytest.mark.parametrize("version", ["1.03.0", "1.3.0+local", "1.3.0!", "1.3.0-evil", "1.3.0$(false)"])
def test_noncanonical_or_docker_unsafe_version_rejected(version):
    from scripts.verify_release import source_version
    with pytest.raises(ValueError, match="canonical"):
        source_version(f'VERSION = "{version}"')


def test_remote_tag_guard_rejects_moved_tags_and_accepts_both_tag_types(tmp_path):
    import subprocess
    from pathlib import Path
    remote = tmp_path / "remote.git"
    checkout = tmp_path / "checkout"
    def git(*args):
        return subprocess.check_output(["git", *args], text=True).strip()
    git("init", "--bare", str(remote))
    git("clone", str(remote), str(checkout))
    git("-C", str(checkout), "config", "user.name", "Release guard test")
    git("-C", str(checkout), "config", "user.email", "test@localhost")
    git("-C", str(checkout), "commit", "--allow-empty", "-m", "tested")
    tested = git("-C", str(checkout), "rev-parse", "HEAD")
    git("-C", str(checkout), "tag", "v1.3.0")
    git("-C", str(checkout), "tag", "-a", "v1.3.1", "-m", "annotated")
    git("-C", str(checkout), "push", "origin", "HEAD", "--tags")
    script = Path(__file__).resolve().parents[1] / "scripts/verify_release_tag.sh"
    def guard(tag):
        return subprocess.run(["bash", str(script), tag, tested], cwd=checkout, capture_output=True).returncode
    assert guard("v1.3.0") == 0
    assert guard("v1.3.1") == 0
    assert guard("v9.9.9") != 0
    assert guard("bad;touch unexpected") != 0
    git("-C", str(checkout), "commit", "--allow-empty", "-m", "different")
    git("-C", str(checkout), "tag", "-f", "v1.3.0")
    git("-C", str(checkout), "push", "--force", "origin", "refs/tags/v1.3.0")
    # Local stale tag knowledge must not make a moved remote tag pass.
    assert guard("v1.3.0") != 0


def test_workflow_keeps_checks_and_publication_on_one_commit():
    from pathlib import Path

    import yaml
    workflow = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text())
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"]["cancel-in-progress"] is False
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["ref"] == "${{ github.sha }}"
                assert step["with"]["persist-credentials"] is False
    for name in ("release", "docker"):
        job = workflow["jobs"][name]
        assert "workflow_dispatch" in job["if"] and "inputs.publish_release" in job["if"]
        assert "refs/heads/main" in job["if"]
        assert "release-check" in job["needs"]
        assert "smoke-docker" in job["needs"] and "smoke-wheel" in job["needs"]
    docker_steps = workflow["jobs"]["docker"]["steps"]
    assert any(step.get("with", {}).get("name") == "smoke-image" for step in docker_steps)
    assert not any(step.get("with", {}).get("push") is True for step in docker_steps)
