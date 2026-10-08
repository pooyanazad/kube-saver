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
    with zipfile.ZipFile(dist / "kube_saver.whl", "w") as z:
        z.writestr("kube_saver.dist-info/METADATA", f"Name: kube-saver\nVersion: {wheel}\n")
        z.writestr("kube_saver/version.py", f'VERSION = "{embedded}"\n')
    with tarfile.open(dist / "kube_saver.tar.gz", "w:gz") as t:
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
