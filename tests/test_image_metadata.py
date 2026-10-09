"""Reject incomplete or misleading public image metadata."""

import pytest
from scripts.verify_image_metadata import verify_labels

REVISION = "a" * 40


def valid_labels():
    return {
        "io.artifacthub.package.readme-url":
            f"https://raw.githubusercontent.com/pooyanazad/kube-saver/{REVISION}/README.md",
        "org.opencontainers.image.description":
            "Kubernetes cost estimates and resource right-sizing with local reports and review plans.",
        "org.opencontainers.image.documentation": "https://pooyanazad.github.io/kube-saver/",
        "org.opencontainers.image.source": "https://github.com/pooyanazad/kube-saver",
        "org.opencontainers.image.revision": REVISION,
        "org.opencontainers.image.version": "2.0.0",
        "org.opencontainers.image.licenses": "MIT",
        "org.opencontainers.image.created": "2026-10-09T12:00:00Z",
    }


def test_valid_labels():
    verify_labels(valid_labels(), "2.0.0", REVISION)


@pytest.mark.parametrize("value", [None, {}, "labels"])
def test_absent_labels_rejected(value):
    with pytest.raises(ValueError):
        verify_labels(value, "2.0.0", REVISION)


@pytest.mark.parametrize("key", list(valid_labels()))
def test_missing_or_incorrect_label_rejected(key):
    labels = valid_labels()
    labels[key] = "wrong"
    with pytest.raises(ValueError):
        verify_labels(labels, "2.0.0", REVISION)


@pytest.mark.parametrize("created", ["2026-02-30T12:00:00Z", "9999-01-01T00:00:00Z", "", 7])
def test_invalid_or_future_creation_date_rejected(created):
    labels = valid_labels()
    labels["org.opencontainers.image.created"] = created
    with pytest.raises(ValueError):
        verify_labels(labels, "2.0.0", REVISION)
