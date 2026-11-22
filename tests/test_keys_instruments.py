import polars as pl
import pytest
from conftest import make_fills

from arkstream.instruments import FILL_KEY, key_report


def test_classes_and_dust_kept():
    f = make_fills([
        dict(ts="2025-10-01 00:00:00", trader="0xa", symbol="BTC", side="buy", size=1.0, start_position=0.0),
        dict(ts="2025-10-01 00:00:00", trader="0xa", symbol="@107", side="buy", size=1.0, start_position=0.0,
             dir="Buy"),
        dict(ts="2025-10-01 00:00:00", trader="0xa", symbol="PURR/USDC", side="buy", size=1.0, start_position=0.0,
             dir="Buy"),
        dict(ts="2025-10-01 00:00:00", trader="0xa", symbol="xyz:TSLA", side="buy", size=1.0, start_position=0.0),
        dict(ts="2025-10-01 00:00:00", trader="0xa", symbol="@230", side="sell", size=0.01, start_position=0.01,
             dir="Spot Dust Conversion", tid=0),
    ])
    assert f["instrument_class"].to_list() == ["core_perp", "spot", "spot", "hip3", "spot"]
    assert f["eligible"].to_list() == [True, False, False, False, False]
    assert f.height == 5 and f["event_kind"].to_list()[-1] == "non_trade"


@pytest.mark.data
def test_composite_key_unique_and_dust_is_the_only_repeat(inputs):
    rep = key_report(inputs.fills)
    assert rep["composite_key_duplicates"] == 0
    assert rep["repeated_rows_not_dust"] == 0
    assert inputs.fills.select(FILL_KEY).is_duplicated().sum() == 0
    dust = inputs.fills.filter(pl.col("dir") == "Spot Dust Conversion")
    assert dust.height == 785 and dust["event_kind"].unique().to_list() == ["non_trade"]
