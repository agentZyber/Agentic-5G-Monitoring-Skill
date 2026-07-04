"""Unit tests for the dataset registry."""

import pytest

from corelab.datasets import (
    Dataset,
    datasets_for_role,
    get_dataset,
    list_datasets,
)


def test_verified_datasets_present():
    names = {d.name for d in list_datasets(verified_only=True)}
    assert {"TeleQnA", "Tele-Data", "5G3E"}.issubset(names)


def test_get_dataset_is_normalization_tolerant():
    assert get_dataset("TeleQnA").source == "hf:netop/TeleQnA"
    assert get_dataset("tele_data").name == "Tele-Data"  # underscore -> hyphen
    with pytest.raises(KeyError):
        get_dataset("nonexistent")


def test_roles_filter():
    eval_sets = {d.name for d in datasets_for_role("eval")}
    assert "TeleQnA" in eval_sets
    replay_sets = {d.name for d in datasets_for_role("replay")}
    assert "5G3E" in replay_sets
    with pytest.raises(ValueError):
        datasets_for_role("not-a-role")


def test_5g3e_license_caveat_is_recorded():
    # Research flagged 5G3E has no explicit LICENSE file; the registry must surface that.
    ds = get_dataset("5g3e")
    assert ds.license == "verify"
    assert "licens" in ds.note.lower()


def test_invalid_role_rejected_at_construction():
    with pytest.raises(ValueError):
        Dataset(
            name="bad",
            source="x",
            description="d",
            size="0",
            license="x",
            roles=("not-a-role",),
        )
