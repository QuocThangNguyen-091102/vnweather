from datetime import date

import numpy as np
import pandas as pd
import pytest

from weather_platform import config, forecast
from weather_platform.forecast import (
    InsufficientDataError, backtest, build_series, design_matrix, estimate_phi, evaluate, fit_model,
    make_forecasts, predict, save_eval, save_forecasts,
)


def seasonal_series(days=3 * 365 + 30, noise=0.0, seed=0, start="2022-01-01"):
    idx = pd.date_range(start, periods=days, freq="D")
    t = np.asarray((idx - forecast.EPOCH).days, dtype=float)
    rng = np.random.default_rng(seed)
    values = 28 + 4 * np.sin(2 * np.pi * t / 365.25) + noise * rng.standard_normal(days)
    return pd.Series(values, index=idx)


# --------------------------------------------------------------------------- mô hình
def test_design_matrix_shape_and_constant_column():
    x = design_matrix(np.arange(10.0))
    assert x.shape == (10, 2 + 2 * config.N_HARMONICS)
    assert np.all(x[:, 0] == 1.0)


def test_fit_recovers_a_clean_seasonal_signal():
    y = seasonal_series()
    fit = forecast.fit_model(y)
    dates, clim, ar1 = predict(fit, y.index.max(), 7)
    t = np.asarray((dates - forecast.EPOCH).days, dtype=float)
    truth = 28 + 4 * np.sin(2 * np.pi * t / 365.25)
    assert np.max(np.abs(clim - truth)) < 0.05
    assert np.max(np.abs(ar1 - truth)) < 0.05


def test_fit_requires_enough_history():
    with pytest.raises(InsufficientDataError):
        fit_model(seasonal_series(days=100))


def test_fit_ignores_missing_values_but_counts_only_real_ones():
    y = seasonal_series(days=400)
    y.iloc[50:200] = np.nan
    with pytest.raises(InsufficientDataError):
        fit_model(y, min_train=365)


def test_predict_returns_requested_horizon_and_dates():
    y = seasonal_series()
    fit = fit_model(y)
    dates, clim, ar1 = predict(fit, y.index.max(), 14)
    assert len(dates) == len(clim) == len(ar1) == 14
    assert dates[0] == y.index.max() + pd.Timedelta(days=1)


def test_anomaly_correction_fades_toward_the_climate_line():
    fit = forecast.ModelFit(beta=np.array([28.0, 0, 0, 0, 0, 0, 0, 0]), phi=0.7, last_anomaly=3.0, n_train=999)
    _, clim, ar1 = predict(fit, pd.Timestamp("2026-01-01"), 7)
    gap = np.abs(ar1 - clim)
    assert gap[0] == pytest.approx(2.1)
    assert np.all(np.diff(gap) < 0)


# --------------------------------------------------------------------------- estimate_phi
def test_phi_is_zero_for_constant_residuals():
    assert estimate_phi(np.zeros(50)) == 0.0


def test_phi_is_zero_for_nan_or_too_short_input():
    assert estimate_phi(np.array([np.nan] * 10)) == 0.0
    assert estimate_phi(np.array([1.0, 2.0])) == 0.0
    assert estimate_phi(np.array([])) == 0.0


def test_phi_recovers_positive_autocorrelation():
    rng = np.random.default_rng(1)
    e = np.zeros(4000)
    for i in range(1, len(e)):
        e[i] = 0.7 * e[i - 1] + rng.standard_normal()
    assert 0.6 < estimate_phi(e) < 0.8


def test_phi_is_clipped_to_valid_range():
    alternating = np.array([1.0, -1.0] * 50)          # tự tương quan âm
    assert estimate_phi(alternating) == 0.0
    trend = np.arange(1000.0)                         # tự tương quan gần 1
    assert estimate_phi(trend) <= 0.99


# --------------------------------------------------------------------------- chuỗi thời gian
def test_build_series_interpolates_short_gaps_only():
    idx = pd.date_range("2026-01-01", periods=20, freq="D")
    y = pd.Series(np.arange(20, dtype=float), index=idx)
    y = y.drop(idx[[3, 4]]).drop(idx[10:15])          # khoảng trống 2 ngày và 5 ngày
    df = pd.DataFrame({"location_name": "A", "full_date": y.index, "temp_max_c": y.values})
    out = build_series(df)["A"]
    assert idx[3] in out.index and idx[4] in out.index          # 2 ngày: được nội suy
    assert not any(d in out.index for d in idx[13:15])          # 5 ngày: chỉ nội suy tối đa 3 ngày đầu, phần còn lại bỏ


# --------------------------------------------------------------------------- kiểm thử ngược
def test_backtest_returns_expected_columns_and_models():
    res = backtest({"A": seasonal_series(days=3 * 365)}, backtest_days=100, origin_step=7)
    assert set(res.columns) == {"location", "origin", "horizon", "model", "pred", "actual"}
    assert set(res["model"]) == set(forecast.MODELS)
    assert set(res["horizon"]) == set(range(1, 8))


def test_backtest_uses_no_data_after_the_origin():
    """Kiểm tra rò rỉ: đổi toàn bộ dữ liệu SAU (mốc + 7 ngày) thì dự báo tại mốc đầu tiên không được đổi."""
    y = seasonal_series(days=3 * 365, noise=0.5)
    base = backtest({"A": y}, backtest_days=60, origin_step=7)
    first_origin = base["origin"].min()
    tampered = y.copy()
    tampered[tampered.index > first_origin + pd.Timedelta(days=7)] += 100.0
    again = backtest({"A": tampered}, backtest_days=60, origin_step=7)
    a = base[base["origin"] == first_origin].reset_index(drop=True)
    b = again[again["origin"] == first_origin].reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_backtest_skips_series_that_are_too_short():
    assert backtest({"A": seasonal_series(days=200)}).empty


def test_backtest_only_scores_days_with_real_observations():
    y = seasonal_series(days=3 * 365)
    y = y.drop(y.index[-40:-30])                       # cắt 10 ngày trống gần cuối
    res = backtest({"A": y}, backtest_days=60)
    assert res["actual"].notna().all()


def test_step_between_origins_is_seven_days():
    res = backtest({"A": seasonal_series(days=3 * 365)}, backtest_days=70, origin_step=7)
    origins = sorted(res["origin"].unique())
    assert {(b - a).days for a, b in zip(origins, origins[1:])} == {7}


# --------------------------------------------------------------------------- đánh giá
def test_evaluate_computes_mae_rmse_and_n_per_location_and_pooled():
    res = pd.DataFrame([
        ("A", pd.Timestamp("2026-01-01"), 1, "clim", 11.0, 10.0),
        ("A", pd.Timestamp("2026-01-08"), 1, "clim", 11.0, 10.0),
        ("A", pd.Timestamp("2026-01-15"), 1, "clim", 11.0, 10.0),
        ("B", pd.Timestamp("2026-01-01"), 1, "clim", 15.0, 10.0),
    ], columns=["location", "origin", "horizon", "model", "pred", "actual"])
    ev = evaluate(res).set_index(["location_name", "model", "horizon"])
    assert ev.loc[("A", "clim", 1), "mae"] == pytest.approx(1.0)
    assert ev.loc[("A", "clim", 1), "n"] == 3
    assert ev.loc[("B", "clim", 1), "rmse"] == pytest.approx(5.0)
    pooled = ev.loc[("ALL", "clim", 1)]
    assert pooled["mae"] == pytest.approx(2.0)                 # (1+1+1+5)/4, không phải trung bình của các MAE
    assert pooled["rmse"] == pytest.approx(np.sqrt(7.0))       # sqrt((1+1+1+25)/4)
    assert pooled["n"] == 4


def test_evaluate_empty_input_returns_empty_frame_with_columns():
    out = evaluate(pd.DataFrame(columns=["location", "origin", "horizon", "model", "pred", "actual"]))
    assert out.empty and list(out.columns) == ["location_name", "model", "horizon", "mae", "rmse", "n"]


def test_evaluate_ignores_rows_with_missing_actual():
    res = pd.DataFrame([("A", pd.Timestamp("2026-01-01"), 1, "clim", 11.0, np.nan)],
                       columns=["location", "origin", "horizon", "model", "pred", "actual"])
    assert evaluate(res).empty


# --------------------------------------------------------------------------- dự báo thật
def test_make_forecasts_isolates_failures_per_location():
    rows, failed = make_forecasts({"Tốt": seasonal_series(), "Ngắn": seasonal_series(days=50)}, horizon=14)
    assert {r[0] for r in rows} == {"Tốt"} and len(rows) == 14
    assert set(failed) == {"Ngắn"}
    assert rows[0][3] == 1 and rows[-1][3] == 14 and rows[0][4] == config.FORECAST_MODEL_NAME


def test_make_forecasts_rounds_to_one_decimal():
    rows, _ = make_forecasts({"A": seasonal_series()})
    assert all(round(r[5], 1) == r[5] for r in rows)


# --------------------------------------------------------------------------- ghi kết quả
def test_save_eval_writes_location_and_run_id(fake_conn):
    ev = pd.DataFrame([("A", "clim", 1, 1.234567, 2.0, 30)],
                      columns=["location_name", "model", "horizon", "mae", "rmse", "n"])
    assert save_eval(fake_conn, ev, "RUN1") == 1
    sql, rows = fake_conn.many[0]
    assert "location_name" in sql and "run_id" in sql
    assert rows[0][0] == "RUN1" and rows[0][2] == "A" and rows[0][5] == 1.235


def test_save_forecasts_replaces_only_same_location_and_base_date(fake_conn):
    rows = [("A", date(2026, 9, 13), date(2026, 9, 14), 1, "clim_ar1", 30.1),
            ("A", date(2026, 9, 13), date(2026, 9, 15), 2, "clim_ar1", 30.2),
            ("B", date(2026, 9, 13), date(2026, 9, 14), 1, "clim_ar1", 29.0)]
    assert save_forecasts(fake_conn, rows, "RUN1") == 3
    deletes = fake_conn.sql_containing("DELETE FROM mart.forecast_daily")
    assert len(deletes) == 2 and {p[0] for _, p in deletes} == {"A", "B"}


def test_save_forecasts_with_no_rows_does_nothing(fake_conn):
    assert save_forecasts(fake_conn, [], "RUN1") == 0 and not fake_conn.executed


# --------------------------------------------------------------------------- chạy cả quy trình với DB giả
def test_run_reads_series_evaluates_and_saves_everything(fake_conn):
    from decimal import Decimal

    rows = []
    for name, offset in (("A", 0.0), ("B", 1.5)):
        y = seasonal_series(days=3 * 365 + 30)
        for d, v in y.items():
            rows.append((name, d.date(), Decimal(str(round(v + offset, 2)))))
    fake_conn.frames["FROM dwh.fact_weather_daily AS f"] = (["location_name", "full_date", "temp_max_c"], rows)

    summary = forecast.run(fake_conn, "20260921_070000")

    assert summary.locations_ok == 2 and not summary.failed
    assert summary.forecast_rows == 2 * config.FORECAST_DAYS
    assert summary.mae_table is not None and list(summary.mae_table.index) == list(range(1, 8))
    eval_rows = [r for sql, batch in fake_conn.many if "mart.forecast_eval" in sql for r in batch]
    assert {r[2] for r in eval_rows} == {"A", "B", "ALL"}          # từng địa điểm và dòng gộp
    assert {r[0] for r in eval_rows} == {"20260921_070000"}         # mọi dòng mang run_id
    assert all(r[7] > 0 for r in eval_rows)                         # số quan sát dương


def test_run_fails_clearly_when_warehouse_has_no_temperature(fake_conn):
    fake_conn.frames["FROM dwh.fact_weather_daily AS f"] = (["location_name", "full_date", "temp_max_c"], [])
    with pytest.raises(RuntimeError, match="chưa có nhiệt độ"):
        forecast.run(fake_conn, "R")
