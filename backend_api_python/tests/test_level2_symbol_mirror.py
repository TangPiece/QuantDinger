"""按日宽表收成每只股票一个文件；D1 模式下默认跳过。"""
from io import BytesIO

import pandas as pd


def test_rebuild_skips_without_uploader(tmp_path):
    from app.services.level2_factors.symbol_mirror import rebuild_symbol_mirrors

    pd.DataFrame({
        "trade_date": ["20251103"],
        "symbol": ["600519.SH"],
        "l2_obi": [0.2],
    }).to_parquet(tmp_path / "20251103.parquet", index=False)
    assert rebuild_symbol_mirrors(tmp_path) == (0, 0)


def test_rebuild_uploads_each_symbol_once_when_uploader_injected(tmp_path, monkeypatch):
    from app.services.level2_factors.names import stored_columns
    from app.services.level2_factors.symbol_mirror import rebuild_symbol_mirrors

    monkeypatch.setenv("R2_FACTOR_PREFIX", "l2_factors")
    columns = ["trade_date", "symbol", "l2_obi", "l2_obi_mean_5"]
    pd.DataFrame({
        "trade_date": ["20251103", "20251103"],
        "symbol": ["600519.SH", "000001.SZ"],
        "l2_obi": [0.2, 0.4],
        "l2_obi_mean_5": [0.1, 0.1],
    })[columns].to_parquet(tmp_path / "20251103.parquet", index=False)
    pd.DataFrame({
        "trade_date": ["20251104"],
        "symbol": ["600519.SH"],
        "l2_obi": [0.5],
    }).to_parquet(tmp_path / "20251104.parquet", index=False)
    seen: dict[str, bytes] = {}

    def uploader(key: str, payload: bytes) -> None:
        seen[key] = payload

    done, total = rebuild_symbol_mirrors(tmp_path, uploader=uploader)
    assert (done, total) == (2, 2)
    assert set(seen) == {
        "l2_factors/symbol/600519.SH.parquet",
        "l2_factors/symbol/000001.SZ.parquet",
    }
    maotai = pd.read_parquet(BytesIO(seen["l2_factors/symbol/600519.SH.parquet"]))
    assert list(maotai["trade_date"]) == ["20251103", "20251104"]
    assert "l2_obi_mean_5" not in maotai.columns
    assert set(maotai.columns).issubset(set(stored_columns()))
