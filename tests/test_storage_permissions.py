import os
import stat

import pytest

from scalper.schemas import StrategySpec
from scalper.storage import init_db, save_strategy


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits do not apply on Windows.")
def test_new_custom_database_directory_and_file_are_private(tmp_path, monkeypatch):
    db_path = tmp_path / "new-private-dir" / "test.sqlite3"
    monkeypatch.setenv("SCALPER_DB_PATH", str(db_path))
    init_db()
    save_strategy("Private local strategy", StrategySpec(name="EMA 9/21", fast_ema=9, slow_ema=21))
    assert stat.S_IMODE(db_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits do not apply on Windows.")
def test_existing_custom_parent_permissions_are_not_changed(tmp_path, monkeypatch):
    parent = tmp_path / "shared-existing-folder"
    parent.mkdir()
    parent.chmod(0o755)
    db_path = parent / "scalper.sqlite3"
    monkeypatch.setenv("SCALPER_DB_PATH", str(db_path))
    init_db()
    assert stat.S_IMODE(parent.stat().st_mode) == 0o755
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600
