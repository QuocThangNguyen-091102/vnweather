from datetime import date

import pandas as pd

from weather_platform.data_quality import (
    CheckResult, drop_duplicate_dates, find_missing_dates, run_sql_checks, validate_observations,
)


def obs(rows):
    """rows: [(ngày, tmax, tmin, mưa)]"""
    return pd.DataFrame(rows, columns=["obs_date", "temp_max_c", "temp_min_c", "precipitation_mm"])


def names(issues):
    return {i.check: i.count for i in issues}


def test_clean_batch_has_no_issues():
    df = obs([(date(2026, 1, d), 30.0, 22.0, 0.0) for d in range(1, 6)])
    assert validate_observations(df) == []


def test_empty_batch_has_no_issues():
    assert validate_observations(obs([])) == []


def test_detects_min_temperature_above_max():
    df = obs([(date(2026, 1, 1), 25.0, 26.0, 0.0), (date(2026, 1, 2), 30.0, 22.0, 0.0)])
    assert names(validate_observations(df)) == {"temp_min_gt_max": 1}


def test_detects_negative_rain():
    df = obs([(date(2026, 1, 1), 30.0, 22.0, -0.5), (date(2026, 1, 2), 30.0, 22.0, 1.0)])
    assert names(validate_observations(df)) == {"negative_rain": 1}


def test_detects_temperature_out_of_range():
    df = obs([(date(2026, 1, 1), 55.0, 22.0, 0.0), (date(2026, 1, 2), 30.0, -15.0, 0.0)])
    assert names(validate_observations(df))["temp_out_of_range"] == 2


def test_detects_null_temperature():
    df = obs([(date(2026, 1, 1), None, 22.0, 0.0), (date(2026, 1, 2), 30.0, None, 0.0)])
    assert names(validate_observations(df))["null_temperature"] == 2


def test_detects_duplicate_dates():
    df = obs([(date(2026, 1, 1), 30.0, 22.0, 0.0), (date(2026, 1, 1), 31.0, 22.0, 0.0)])
    assert names(validate_observations(df)) == {"duplicate_dates": 1}


def test_detects_missing_dates():
    df = obs([(date(2026, 1, 1), 30.0, 22.0, 0.0), (date(2026, 1, 5), 30.0, 22.0, 0.0)])
    assert names(validate_observations(df)) == {"missing_dates": 3}


def test_find_missing_dates_lists_the_gap():
    assert find_missing_dates([date(2026, 1, 1), date(2026, 1, 4)]) == [date(2026, 1, 2), date(2026, 1, 3)]
    assert find_missing_dates([]) == []


def test_drop_duplicate_dates_keeps_last_value():
    df = obs([(date(2026, 1, 1), 30.0, 22.0, 0.0), (date(2026, 1, 1), 31.0, 22.0, 0.0),
              (date(2026, 1, 2), 29.0, 21.0, 0.0)])
    out = drop_duplicate_dates(df)
    assert len(out) == 2
    assert out.loc[0, "temp_max_c"] == 31.0


def test_run_sql_checks_maps_procedure_rows(fake_conn):
    from collections import namedtuple
    Row = namedtuple("Row", "check_name bad_rows status")
    fake_conn.responders = [("usp_run_dq_checks", lambda p: [Row("A", 0, "PASS"), Row("B", 2, "FAIL")])]
    results = run_sql_checks(fake_conn, "20260921_070000")
    assert results == [CheckResult("A", 0, "PASS"), CheckResult("B", 2, "FAIL")]
    assert results[0].passed and not results[1].passed
    sql, params = fake_conn.executed[0]
    assert "@run_id = ?" in sql and params[0] == "20260921_070000"
    assert fake_conn.commits == 1
