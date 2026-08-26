"""Tests for the `reset` sub-command (wipe a profile's stored login state).

`_reset_profile` is pure filesystem logic — no browser needed, fast to run.
It deletes a profile's `state.json` while keeping the profile directory.
"""
from pathlib import Path

import pytest

from stealth_browser.browser import _reset_profile


def test_reset_removes_state_file(tmp_path):
    d = tmp_path / "bob"
    d.mkdir(parents=True)
    (d / "state.json").write_text("{}")
    removed = _reset_profile("bob", root=tmp_path)
    assert removed == d / "state.json"
    assert not (d / "state.json").exists()
    assert d.is_dir()  # profile dir preserved


def test_reset_no_state_returns_dir(tmp_path):
    d = tmp_path / "fresh"
    d.mkdir(parents=True)
    removed = _reset_profile("fresh", root=tmp_path)
    # nothing to delete -> returns the profile dir itself
    assert removed == d


def test_reset_missing_profile_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        _reset_profile("nope", root=tmp_path)


@pytest.mark.parametrize("bad", ["", ".", "..", "../etc"])
def test_reset_bad_name_raises(tmp_path, bad):
    # Guard against ever touching a parent / traversing out of the root.
    with pytest.raises(ValueError):
        _reset_profile(bad, root=tmp_path)
