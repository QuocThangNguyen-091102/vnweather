from datetime import date

import numpy as np
import pandas as pd
import pytest

from weather_platform import analytics


def make_daily(years=range(2020, 2027), location="A", seed=0, last=date(2026, 9, 13)):
    rng = np.random.default_rng(seed)
    days = pd.date_range(f"{min(years)}-01-01", min(pd.Timestamp(f"{max(years)}-12-31"), pd.Timestamp(last)))
    return pd.DataFrame({
        "location_name": location, "full_date": days, "year_num": days.year, "month_num": days.month,
        "temp_max_c": 28 + 4 * np.sin(2 * np.pi * days.dayofyear / 365.25) + rng.standard_normal(len(days)),
        "precipitation_mm": np.abs(rng.standard_normal(len(days))) * 5,
    })


def test_threshold_depends_only_on_the_reference_period():
    daily = make_daily()
    base = analytics.p95_thresholds(daily, 2020, 2025)
    tampered = daily.copy()
    tampered.loc[tampered["year_num"] == 2026, "temp_max_c"] += 50      # đổi dữ liệu ngoài giai đoạn tham chiếu
    again = analytics.p95_thresholds(tampered, 2020, 2025)
    pd.testing.assert_frame_equal(base, again)


def test_threshold_is_not_affected_by_the_selected_view_range():
    daily = make_daily()
    thr = analytics.p95_thresholds(daily, 2020, 2025)
    early = analytics.flag_extremes(daily[daily["year_num"].between(2020, 2023)], thr, 50)
    late = analytics.flag_extremes(daily[daily["year_num"].between(2020, 2026)], thr, 50)
    same_rows = late[late["year_num"].between(2020, 2023)].reset_index(drop=True)
    pd.testing.assert_series_equal(early["hot_day"].reset_index(drop=True), same_rows["hot_day"], check_names=False)


def test_roughly_five_percent_of_reference_days_are_flagged():
    daily = make_daily(years=range(2020, 2026))
    thr = analytics.p95_thresholds(daily, 2020, 2025)
    flagged = analytics.flag_extremes(daily, thr, 50)
    assert 0.03 < flagged["hot_day"].mean() < 0.07


def test_heavy_rain_threshold_is_inclusive():
    df = pd.DataFrame({"location_name": "A", "full_date": pd.date_range("2026-01-01", periods=3),
                       "year_num": 2026, "month_num": 1, "temp_max_c": 30.0,
                       "precipitation_mm": [49.9, 50.0, 80.0]})
    thr = pd.DataFrame({"location_name": ["A"], "month_num": [1], "p95": [99.0]})
    flagged = analytics.flag_extremes(df, thr, 50)
    assert flagged["heavy_rain"].tolist() == [False, True, True]


def test_extremes_by_year_counts_flags():
    df = pd.DataFrame({"location_name": "A", "full_date": pd.date_range("2025-12-30", periods=4),
                       "year_num": [2025, 2025, 2026, 2026], "month_num": [12, 12, 1, 1],
                       "temp_max_c": 30.0, "precipitation_mm": [60.0, 0.0, 70.0, 80.0]})
    thr = pd.DataFrame({"location_name": ["A", "A"], "month_num": [12, 1], "p95": [40.0, 40.0]})
    out = analytics.extremes_by_year(analytics.flag_extremes(df, thr, 50)).set_index("year_num")
    assert out.loc[2025, "heavy_rain_days"] == 1 and out.loc[2026, "heavy_rain_days"] == 2


def test_monthly_rainfall_skips_incomplete_months():
    daily = make_daily(years=range(2025, 2027))          # 2026 chỉ đến 13/09
    rain = analytics.monthly_rainfall(daily)
    assert set(rain["month_num"]) == set(range(1, 13))
    september = daily[daily["month_num"] == 9]
    complete_sept = september[september["year_num"] == 2025]["precipitation_mm"].sum()
    assert rain[rain["month_num"] == 9]["total"].iloc[0] == pytest.approx(complete_sept)


def test_yearly_temperature_drops_the_incomplete_year():
    out = analytics.yearly_temperature(make_daily(years=range(2024, 2027)))
    assert set(out["year_num"]) == {2024, 2025}


def test_summarize_location_reports_data_lag():
    daily = make_daily(years=range(2026, 2027))
    kpi = analytics.summarize_location(daily, today=date(2026, 9, 20))
    assert kpi["last_date"] == date(2026, 9, 13)
    assert kpi["lag_days"] == 7
    assert kpi["temp_avg_30"] == pytest.approx(daily.tail(30)["temp_max_c"].mean())


def test_summarize_location_of_empty_frame_is_empty():
    assert analytics.summarize_location(make_daily().iloc[0:0], date(2026, 9, 20)) == {}
