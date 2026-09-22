from decimal import Decimal

import pandas as pd

from weather_platform.data_quality import fetch_quality_metrics
from weather_platform.db import fetch_frame, rows_to_frame


def test_rows_to_frame_converts_decimal_columns_to_float():
    df = rows_to_frame(["a", "b"], [(Decimal("1.50"), "x"), (Decimal("2.25"), "y")])
    assert df["a"].dtype == float
    assert df["a"].tolist() == [1.5, 2.25]
    assert df["b"].tolist() == ["x", "y"]


def test_rows_to_frame_keeps_null_as_missing_value():
    df = rows_to_frame(["a"], [(Decimal("1.5"),), (None,)])
    assert pd.isna(df.loc[1, "a"])


def test_rows_to_frame_of_no_rows_keeps_columns():
    df = rows_to_frame(["a", "b"], [])
    assert df.empty and list(df.columns) == ["a", "b"]


def test_fetch_frame_reads_columns_from_cursor_description(fake_conn):
    fake_conn.frames["FROM some_table"] = (["x", "y"], [(1, Decimal("2.5"))])
    df = fetch_frame(fake_conn, "SELECT x, y FROM some_table WHERE id = ?", (7,))
    assert df.loc[0, "y"] == 2.5
    assert fake_conn.executed[0][1] == (7,)


def test_fetch_quality_metrics_returns_named_values(fake_conn):
    fake_conn.frames["v_data_quality_metrics"] = (["freshness_days", "completeness_pct"], [(7, Decimal("100.000"))])
    assert fetch_quality_metrics(fake_conn) == {"freshness_days": 7, "completeness_pct": Decimal("100.000")}
