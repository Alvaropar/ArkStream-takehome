"""Mixed-format timestamp parsing, forced to UTC with millisecond precision.

Observed formats: 'YYYY-MM-DD HH:MM:SS', with 0-3 fractional digits, with or without '+00'.
Fractions are right-padded ('.9' is 900 ms). Any other offset is applied, then converted to UTC.
A row that does not match the grammar is a parse failure and raises.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import polars as pl

TS_RE = r"^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(?:\.(\d{1,3}))?(Z|[+-]\d{2}(?::?\d{2})?)?$"
_TS = re.compile(TS_RE)


class TimestampParseError(ValueError):
    pass


def parse_ts_expr(col: str) -> pl.Expr:
    """Polars expression: string column -> Datetime('ms', 'UTC'). Nulls mark failures."""
    c = pl.col(col)
    base = (c.str.extract(TS_RE, 1) + " " + c.str.extract(TS_RE, 2)).str.to_datetime(
        "%Y-%m-%d %H:%M:%S", time_unit="ms", strict=False
    )
    frac_ms = c.str.extract(TS_RE, 3).fill_null("000").str.pad_end(3, "0").cast(pl.Int64, strict=False)
    off = c.str.extract(TS_RE, 4).fill_null("Z")
    sign = pl.when(off.str.starts_with("-")).then(-1).otherwise(1)
    off_digits = off.str.replace_all(r"[^0-9]", "")
    # Both when/otherwise branches are evaluated, so casts are non-strict; a bad value still ends as null.
    off_h = pl.when(off == "Z").then(0).otherwise(off_digits.str.slice(0, 2).cast(pl.Int64, strict=False))
    off_m = pl.when(off_digits.str.len_chars() >= 4).then(
        off_digits.str.slice(2, 2).cast(pl.Int64, strict=False)).otherwise(0)
    off_ms = sign * (off_h * 3_600_000 + off_m * 60_000)
    return (base + pl.duration(milliseconds=frac_ms - off_ms)).dt.replace_time_zone("UTC")


def parse_ts_column(df: pl.DataFrame, col: str = "timestamp", out: str = "ts") -> pl.DataFrame:
    """Parse and assert zero failures (rule A03)."""
    res = df.with_columns(parse_ts_expr(col).alias(out))
    bad = res.filter(pl.col(out).is_null())
    if bad.height:
        raise TimestampParseError(f"{bad.height} unparseable timestamps, e.g. {bad[col].head(5).to_list()}")
    return res


def parse_one_utc(s: str) -> datetime:
    """Parse a single timestamp (config / CLI). Accepts the data grammar plus ISO 'T' and 'Z'."""
    s = s.strip()
    if _TS.match(s) or re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        val = pl.DataFrame({"t": [s if " " in s or "T" in s else s + " 00:00:00"]})
        return parse_ts_column(val, "t", "ts")["ts"][0]
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).astimezone(UTC)
