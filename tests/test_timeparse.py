from datetime import UTC, datetime

import polars as pl
import pytest

from arkstream.timeparse import TimestampParseError, parse_one_utc, parse_ts_column


def _p(values):
    return parse_ts_column(pl.DataFrame({"timestamp": values}))["ts"].to_list()


def test_mixed_formats_force_utc_and_pad_fraction():
    got = _p(["2025-10-10 21:18:44.652+00", "2025-10-10 21:18:44.65+00", "2025-10-10 21:18:44.6",
              "2025-10-10 21:18:44", "2025-10-10T21:18:44Z", "2025-10-10 23:18:44.652+02:00"])
    base = datetime(2025, 10, 10, 21, 18, 44, tzinfo=UTC)
    ms = [652, 650, 600, 0, 0, 652]
    assert [g.isoformat() for g in got] == [base.replace(microsecond=m * 1000).isoformat() for m in ms]


def test_unparseable_raises():
    with pytest.raises(TimestampParseError):
        _p(["2025-10-10 21:18:44.652+00", "10/10/2025 21:18"])


def test_parse_one_utc():
    assert parse_one_utc("2026-01-04T23:59:59Z") == datetime(2026, 1, 4, 23, 59, 59, tzinfo=UTC)
    assert parse_one_utc("2025-10-08") == datetime(2025, 10, 8, tzinfo=UTC)


@pytest.mark.data
def test_zero_parse_failures_on_raw(inputs):
    # ingest raises on any failure; here we assert the parsed columns are complete and UTC
    for df in (inputs.traders, inputs.fills):
        assert df["ts"].null_count() == 0
        assert str(df["ts"].dtype) == "Datetime(time_unit='ms', time_zone='UTC')"
