from datetime import date, datetime

import pandas as pd
import pytest
import requests

from weather_platform import config
from weather_platform.ingestion import (
    IngestResult, compute_window, get_json, ingest_observations, parse_archive_daily,
    parse_forecast_daily, store_api_forecast,
)


def payload(times, tmax, tmin=None, rain=None, wind=None):
    n = len(times)
    return {"daily": {
        "time": times,
        "temperature_2m_max": tmax,
        "temperature_2m_min": tmin if tmin is not None else [22.0] * n,
        "precipitation_sum": rain if rain is not None else [0.0] * n,
        "wind_speed_10m_max": wind if wind is not None else [10.0] * n,
    }}


# --------------------------------------------------------------------------- parse
def test_parse_archive_daily_builds_typed_frame():
    df = parse_archive_daily(payload(["2026-01-01", "2026-01-02"], [30.5, 31.0]))
    assert list(df.columns) == ["obs_date", "temp_max_c", "temp_min_c", "precipitation_mm", "wind_max_kmh"]
    assert df.loc[0, "obs_date"] == date(2026, 1, 1)
    assert df.loc[1, "temp_max_c"] == 31.0


def test_parse_archive_daily_trims_trailing_days_without_data():
    df = parse_archive_daily(payload(["2026-01-01", "2026-01-02", "2026-01-03"], [30.0, 31.0, None]))
    assert len(df) == 2
    assert df["obs_date"].iloc[-1] == date(2026, 1, 2)


def test_parse_archive_daily_keeps_null_in_the_middle():
    df = parse_archive_daily(payload(["2026-01-01", "2026-01-02", "2026-01-03"], [30.0, None, 31.0]))
    assert len(df) == 3
    assert pd.isna(df.loc[1, "temp_max_c"])


def test_parse_archive_daily_all_null_returns_empty():
    assert parse_archive_daily(payload(["2026-01-01"], [None])).empty


def test_parse_archive_daily_rejects_response_without_daily_block():
    with pytest.raises(ValueError):
        parse_archive_daily({"error": True, "reason": "x"})


def test_parse_archive_daily_rejects_mismatched_column_length():
    bad = payload(["2026-01-01", "2026-01-02"], [30.0, 31.0])
    bad["daily"]["precipitation_sum"] = [0.0]
    with pytest.raises(ValueError):
        parse_archive_daily(bad)


def test_parse_archive_daily_missing_optional_column_becomes_null():
    p = payload(["2026-01-01"], [30.0])
    del p["daily"]["wind_speed_10m_max"]
    df = parse_archive_daily(p)
    assert pd.isna(df.loc[0, "wind_max_kmh"])


def test_parse_forecast_daily_keeps_only_horizons_1_to_7_with_values():
    today = date(2026, 9, 21)
    times = ["2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-26",
             "2026-09-27", "2026-09-28", "2026-09-29"]
    temps = [30.0, 31.04, None, 29.0, 28.0, 27.0, 26.0, 25.0, 24.0]
    out = parse_forecast_daily({"daily": {"time": times, "temperature_2m_max": temps}}, today)
    assert [h for _, h, _ in out] == [1, 3, 4, 5, 6, 7]     # bỏ ngày hôm nay, ngày null và ngày thứ 8
    assert out[0] == (date(2026, 9, 22), 1, 31.0)


# --------------------------------------------------------------------------- cửa sổ thời gian
def test_window_incremental_starts_after_last_observation():
    start, end = compute_window(date(2026, 9, 10), date(2026, 9, 21), "incremental")
    assert start == date(2026, 9, 11)
    assert end == date(2026, 9, 14)             # hôm nay trừ 7 ngày độ trễ


def test_window_returns_none_when_up_to_date():
    assert compute_window(date(2026, 9, 14), date(2026, 9, 21), "incremental") is None


def test_window_history_ignores_existing_data():
    start, _ = compute_window(date(2026, 9, 10), date(2026, 9, 21), "history")
    assert start == config.HISTORY_START


def test_window_without_data_starts_at_history_start():
    start, _ = compute_window(None, date(2026, 9, 21), "incremental")
    assert start == config.HISTORY_START


def test_window_accepts_datetime_from_database():
    start, _ = compute_window(datetime(2026, 9, 10, 0, 0), date(2026, 9, 21), "incremental")
    assert start == date(2026, 9, 11)


def test_window_rejects_unknown_mode():
    with pytest.raises(ValueError):
        compute_window(None, date(2026, 9, 21), "bat-ky-gi")


# --------------------------------------------------------------------------- get_json (retry)
class Resp:
    def __init__(self, status, body=None):
        self.status_code, self._body = status, body or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self._body


def scripted(*outcomes):
    calls = []

    def http_get(url, params, timeout):
        calls.append(url)
        outcome = outcomes[min(len(calls) - 1, len(outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    http_get.calls = calls
    return http_get


def test_get_json_retries_server_errors_then_succeeds():
    sleeps = []
    http_get = scripted(Resp(500), Resp(503), Resp(200, {"ok": 1}))
    assert get_json("u", {}, http_get=http_get, sleep=sleeps.append, backoff=5) == {"ok": 1}
    assert len(http_get.calls) == 3
    assert sleeps == [5, 10]                    # chờ tăng dần


def test_get_json_retries_rate_limit_and_raises_after_last_attempt():
    http_get = scripted(Resp(429))
    with pytest.raises(Exception):
        get_json("u", {}, retries=3, http_get=http_get, sleep=lambda s: None)
    assert len(http_get.calls) == 3


def test_get_json_retries_connection_errors():
    http_get = scripted(requests.ConnectionError("mất mạng"), Resp(200, {"ok": 1}))
    assert get_json("u", {}, http_get=http_get, sleep=lambda s: None) == {"ok": 1}


def test_get_json_does_not_retry_client_errors():
    http_get = scripted(Resp(400))
    with pytest.raises(requests.HTTPError):
        get_json("u", {}, http_get=http_get, sleep=lambda s: None)
    assert len(http_get.calls) == 1


# --------------------------------------------------------------------------- nạp staging
LOCS = [("Hà Nội", 21.03, 105.85), ("Đà Nẵng", 16.05, 108.2), ("TP.HCM", 10.82, 106.63)]


def frame(*days):
    return pd.DataFrame({
        "obs_date": [date(2026, 9, d) for d in days],
        "temp_max_c": [30.0] * len(days), "temp_min_c": [22.0] * len(days),
        "precipitation_mm": [0.0] * len(days), "wind_max_kmh": [10.0] * len(days),
    })


def test_ingest_loads_each_location_in_its_own_transaction(fake_conn):
    fake_conn.responders = [("MAX(obs_date)", lambda p: [(date(2026, 9, 10),)])]
    fetch = lambda lat, lon, s, e: frame(11, 12, 13)
    result = ingest_observations(fake_conn, LOCS, "RUN1", "incremental", date(2026, 9, 21), fetch, lambda s: None)
    assert result.ok and result.total == 3 and result.rows == 9
    assert fake_conn.commits == 3
    delete_sql, params = fake_conn.sql_containing("DELETE FROM staging.weather_daily_raw")[0]
    assert "obs_date >= ?" in delete_sql and params[1] == date(2026, 9, 11)
    sql, rows = fake_conn.many[0]
    assert rows[0][-1] == "RUN1" and rows[0][-2] == config.SOURCE_ARCHIVE


def test_ingest_history_mode_replaces_the_whole_location(fake_conn):
    fake_conn.responders = [("MAX(obs_date)", lambda p: [(date(2026, 9, 10),)])]
    fetch = lambda lat, lon, s, e: frame(1)
    ingest_observations(fake_conn, LOCS[:1], "RUN1", "history", date(2026, 9, 21), fetch, lambda s: None)
    delete_sql, params = fake_conn.sql_containing("DELETE FROM staging.weather_daily_raw")[0]
    assert "obs_date" not in delete_sql and params == ("Hà Nội",)


def test_ingest_partial_failure_keeps_other_locations(fake_conn):
    fake_conn.responders = [("MAX(obs_date)", lambda p: [(date(2026, 9, 10),)])]

    def fetch(lat, lon, s, e):
        if lat == 16.05:
            raise RuntimeError("API hỏng")
        return frame(11)

    result = ingest_observations(fake_conn, LOCS, "RUN1", "incremental", date(2026, 9, 21), fetch, lambda s: None)
    assert not result.ok
    assert set(result.failed) == {"Đà Nẵng"}
    assert result.loaded == ["Hà Nội", "TP.HCM"]
    assert result.ok_count == 2 and "2/3" in result.summary() and "Đà Nẵng" in result.summary()
    assert fake_conn.rollbacks == 1 and fake_conn.commits == 2


def test_ingest_skips_location_that_is_already_up_to_date(fake_conn):
    fake_conn.responders = [("MAX(obs_date)", lambda p: [(date(2026, 9, 14),)])]
    called = []
    result = ingest_observations(fake_conn, LOCS[:1], "RUN1", "incremental", date(2026, 9, 21),
                                 lambda *a: called.append(a), lambda s: None)
    assert result.skipped == ["Hà Nội"] and result.rows == 0 and not called


def test_ingest_drops_duplicate_dates_before_insert(fake_conn):
    fake_conn.responders = [("MAX(obs_date)", lambda p: [(None,)])]
    fetch = lambda lat, lon, s, e: frame(11, 11, 12)
    ingest_observations(fake_conn, LOCS[:1], "RUN1", "incremental", date(2026, 9, 21), fetch, lambda s: None)
    assert len(fake_conn.many[0][1]) == 2


def test_ingest_stores_missing_values_as_none(fake_conn):
    fake_conn.responders = [("MAX(obs_date)", lambda p: [(None,)])]
    df = frame(11, 12)
    df.loc[1, "precipitation_mm"] = float("nan")
    ingest_observations(fake_conn, LOCS[:1], "RUN1", "incremental", date(2026, 9, 21),
                        lambda *a: df, lambda s: None)
    assert fake_conn.many[0][1][1][6] is None


def test_store_api_forecast_saves_seven_horizons_per_location(fake_conn):
    today = date(2026, 9, 21)
    body = {"daily": {"time": [date(2026, 9, 21 + i).isoformat() for i in range(0, 8)],
                      "temperature_2m_max": [30.0 - i for i in range(0, 8)]}}
    result = store_api_forecast(fake_conn, LOCS[:2], "RUN1", today, lambda url, params: body, lambda s: None)
    assert result.ok and result.rows == 14
    assert fake_conn.many[0][1][0][-1] == "RUN1"


def test_store_api_forecast_continues_after_one_failure(fake_conn):
    body = {"daily": {"time": ["2026-09-22"], "temperature_2m_max": [30.0]}}

    def get(url, params):
        if params["latitude"] == 16.05:
            raise RuntimeError("lỗi")
        return body

    result = store_api_forecast(fake_conn, LOCS, "RUN1", date(2026, 9, 21), get, lambda s: None)
    assert set(result.failed) == {"Đà Nẵng"} and result.rows == 2


def test_ingest_result_summary_without_failures():
    r = IngestResult(total=5, loaded=["a"] * 5, rows=12)
    assert r.summary() == "5/5 địa điểm thành công, 12 dòng mới"
