"""Tests for the `profiles` sub-command (profile listing / scan).

`_scan_profiles` is pure filesystem logic (no browser), so these run fast
without launching a browser. `cmd_profiles` just pretty-prints the results.
"""
import time
from pathlib import Path

from stealth_browser.browser import _scan_profiles, ProfileInfo


def _mk_profile(root: Path, name: str, age: int = 0):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    # Set a recent mtime for the "last used" ordering test.
    ts = time.time() - age
    (d / "state.json").write_text(f'{{"age_test": {age}}}')
    import os
    os.utime(d / "state.json", (ts, ts))
    return d


def test_scan_empty(tmp_path):
    """Fresh profiles dir with nothing yet -> empty list."""
    infos = _scan_profiles(tmp_path)
    assert infos == []


def test_scan_single_profile(tmp_path):
    d = _mk_profile(tmp_path, "bob")
    infos = _scan_profiles(tmp_path)
    assert len(infos) == 1
    i = infos[0]
    assert isinstance(i, ProfileInfo)
    assert i.name == "bob"
    assert i.dir == d
    assert i.state_size is not None  # state.json exists
    assert i.n_profiles == 1


def test_scan_ignores_files_not_dirs(tmp_path):
    (tmp_path / "not_a_profile.txt").write_text("x")
    infos = _scan_profiles(tmp_path)
    # A stray file in the profiles dir is not a profile.
    assert infos == []


def test_scan_sorts_most_recent_first(tmp_path):
    """Newest mtime should sort first; task scans then `profiles` shows MRU."""
    old = _mk_profile(tmp_path, "old", age=5000)  # ~1.4h ago
    _mk_profile(tmp_path, "new", age=10)          # 10s ago
    infos = _scan_profiles(tmp_path)
    names = [i.name for i in infos]
    assert names == ["new", "old"]  # MRU first


def test_scan_reports_no_state_yet(tmp_path):
    """A profile dir without state.json still shows up, 'no state yet'."""
    (tmp_path / "fresh").mkdir()
    infos = _scan_profiles(tmp_path)
    assert len(infos) == 1
    assert infos[0].name == "fresh"
    assert infos[0].state_size is None
