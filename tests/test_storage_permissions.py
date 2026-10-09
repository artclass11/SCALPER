import os
import stat

import pytest

from scalper.storage import init_db, save_strategy
from scalper.schemas import StrategySpec


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits do not apply on Windows.")
def test_local_strategy_database_uses_private_permissions(tmp_path, monkeypatch):
    db_path = tmp_path / "private-dir" / "test.sqlite3"
    monkeypatch.setenv("SCALPER_DB_PATH", str(db_path))
    init_db()
    save_strategy("Private local strategy", StrategySpec(name="EMA 9/21", fast_ema=9, slow_ema=21))
    assert stat.S_IMODE(db_path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(db_path.stat().st_mode) == 0o600
