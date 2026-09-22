"""
forecast.py - Ước lượng mô hình dự báo nhiệt độ cao nhất hằng ngày và đánh giá bằng kiểm thử ngược.

Ba phương pháp được so sánh:
  persistence : giá trị các ngày sau bằng giá trị ngày cuối cùng đã biết
  clim        : đường khí hậu theo mùa (hồi quy tuyến tính với xu hướng và các cặp sin/cos theo năm)
  clim_ar1    : đường khí hậu + phần sai lệch (anomaly) của ngày cuối, giảm dần theo hệ số phi^h

Đây là các mô hình thống kê đơn giản dùng làm mốc so sánh, ước lượng bằng bình phương tối thiểu
(numpy.linalg.lstsq). Không phải mô hình học máy và không thay thế dự báo vật lý.

Đánh giá: rolling-origin evaluation với bước 7 ngày. Tại mỗi mốc, mô hình chỉ được ước lượng từ dữ liệu
đến hết mốc đó rồi dự báo 1..7 ngày tiếp theo (xem docs/forecast_methodology.md).
Kết quả lưu theo từng địa điểm và một dòng gộp (location_name = 'ALL').
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Mapping

import numpy as np
import pandas as pd

from . import config
from .db import fetch_frame

log = logging.getLogger(__name__)

EPOCH = pd.Timestamp(config.EPOCH)
MODELS = ("persistence", "clim", "clim_ar1")


class InsufficientDataError(ValueError):
    """Chuỗi quá ngắn hoặc suy biến, không ước lượng được mô hình."""


@dataclass(frozen=True)
class ModelFit:
    beta: np.ndarray
    phi: float
    last_anomaly: float
    n_train: int


# ----------------------------------------------------------------------------- dữ liệu
def load_series(conn: Any) -> dict[str, pd.Series]:
    """Đọc nhiệt độ cao nhất từ kho, trả về {tên địa điểm: chuỗi theo ngày liên tục}."""
    df = fetch_frame(conn, """
        SELECT l.location_name, d.full_date, f.temp_max_c
        FROM dwh.fact_weather_daily AS f
        JOIN dwh.dim_date     AS d ON d.date_key     = f.date_key
        JOIN dwh.dim_location AS l ON l.location_key = f.location_key
        WHERE f.temp_max_c IS NOT NULL
    """)
    df["full_date"] = pd.to_datetime(df["full_date"])
    df["temp_max_c"] = df["temp_max_c"].astype(float)
    return build_series(df)


def build_series(df: pd.DataFrame) -> dict[str, pd.Series]:
    """Từ bảng (location_name, full_date, temp_max_c) tạo chuỗi ngày liên tục cho từng địa điểm."""
    series: dict[str, pd.Series] = {}
    for name, g in df.groupby("location_name"):
        y = g.set_index("full_date")["temp_max_c"].sort_index()
        y = y[~y.index.duplicated(keep="last")].asfreq("D")
        series[str(name)] = y.interpolate(limit=3).dropna()   # chỉ nội suy khoảng trống tối đa 3 ngày
    return series


# ----------------------------------------------------------------------------- mô hình
def design_matrix(t: np.ndarray) -> np.ndarray:
    """Cột: hằng số, xu hướng, rồi các cặp sin/cos theo chu kỳ năm."""
    t = np.asarray(t, dtype=float)
    cols = [np.ones_like(t), t / 3650.0]
    for k in range(1, config.N_HARMONICS + 1):
        w = 2 * np.pi * k * t / 365.25
        cols += [np.sin(w), np.cos(w)]
    return np.column_stack(cols)


def _days_since_epoch(index: pd.DatetimeIndex) -> np.ndarray:
    return np.asarray((index - EPOCH).days, dtype=float)


def estimate_phi(resid: np.ndarray) -> float:
    """
    Hệ số tự tương quan bậc 1 của phần dư, cắt về [0, 0.99].
    Trả về 0.0 (không hiệu chỉnh) khi không ước lượng được: chuỗi quá ngắn, phần dư hằng số hoặc NaN.
    """
    resid = np.asarray(resid, dtype=float)
    if resid.size < 3:
        return 0.0
    a, b = resid[:-1], resid[1:]
    if np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return 0.0
    phi = float(np.corrcoef(a, b)[0, 1])
    if not math.isfinite(phi):
        return 0.0
    return min(max(phi, 0.0), 0.99)


def fit_model(y: pd.Series, min_train: int = config.MIN_TRAIN_DAYS) -> ModelFit:
    """Ước lượng đường khí hậu và hệ số phi từ chuỗi y (chỉ dùng dữ liệu có trong y)."""
    y = y.dropna()
    if len(y) < min_train:
        raise InsufficientDataError(f"Cần ít nhất {min_train} ngày dữ liệu, hiện có {len(y)}")
    t = _days_since_epoch(y.index)
    x = design_matrix(t)
    values = y.to_numpy(dtype=float)
    beta, *_ = np.linalg.lstsq(x, values, rcond=None)
    if not np.all(np.isfinite(beta)):
        raise InsufficientDataError("Hệ số hồi quy không hữu hạn")
    resid = values - x @ beta
    return ModelFit(beta=beta, phi=estimate_phi(resid), last_anomaly=float(resid[-1]), n_train=len(y))


def predict(fit: ModelFit, last_date: pd.Timestamp, horizon: int) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    """Trả về (ngày dự báo, đường khí hậu, đường khí hậu + AR(1)) cho `horizon` ngày sau last_date."""
    dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon)
    clim = design_matrix(_days_since_epoch(dates)) @ fit.beta
    h = np.arange(1, horizon + 1)
    return dates, clim, clim + (fit.phi ** h) * fit.last_anomaly


# ----------------------------------------------------------------------------- kiểm thử ngược
def backtest(
    series: Mapping[str, pd.Series],
    horizon: int = config.BACKTEST_HORIZON,
    backtest_days: int = config.BACKTEST_DAYS,
    origin_step: int = config.ORIGIN_STEP_DAYS,
    min_train: int = config.MIN_TRAIN_DAYS,
) -> pd.DataFrame:
    """
    Rolling-origin evaluation. Với mỗi mốc (origin) cách nhau `origin_step` ngày:
    ước lượng mô hình CHỈ từ dữ liệu đến hết mốc, dự báo 1..horizon ngày sau, so với số đo thực tế.
    Chỉ tính các ngày có số đo thực tế. Mốc không có quan trắc hoặc chuỗi huấn luyện quá ngắn bị bỏ qua.
    """
    rows: list[tuple] = []
    for name, y in series.items():
        if y.empty:
            continue
        last = y.index.max()
        start = last - pd.Timedelta(days=backtest_days)
        end = last - pd.Timedelta(days=horizon)
        if end < start:
            continue
        for origin in pd.date_range(start, end, freq=f"{origin_step}D"):
            train = y.loc[:origin]
            if len(train) < min_train or train.index.max() != origin:
                continue
            future = pd.date_range(origin + pd.Timedelta(days=1), periods=horizon)
            actual = y.reindex(future)
            if actual.isna().all():
                continue
            try:
                fit = fit_model(train, min_train)
            except InsufficientDataError:
                continue
            _, clim, ar1 = predict(fit, origin, horizon)
            persistence = np.full(horizon, float(train.iloc[-1]))
            for h in range(horizon):
                obs = actual.iloc[h]
                if pd.isna(obs):
                    continue
                for model, pred in (("persistence", persistence), ("clim", clim), ("clim_ar1", ar1)):
                    rows.append((name, origin, h + 1, model, float(pred[h]), float(obs)))
    return pd.DataFrame(rows, columns=["location", "origin", "horizon", "model", "pred", "actual"])


def _aggregate(df: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    out = df.groupby(keys, as_index=False).agg(
        mae=("abs_err", "mean"), mse=("sq_err", "mean"), n=("err", "size")
    )
    out["rmse"] = np.sqrt(out.pop("mse"))
    return out


def evaluate(res: pd.DataFrame) -> pd.DataFrame:
    """
    MAE, RMSE và số quan sát theo (địa điểm, phương pháp, số ngày dự báo trước), cộng thêm các dòng
    gộp mọi địa điểm (location_name = 'ALL'). Dòng gộp tính trên toàn bộ quan sát, không phải trung bình các MAE.
    """
    cols = ["location_name", "model", "horizon", "mae", "rmse", "n"]
    if res.empty:
        return pd.DataFrame(columns=cols)
    df = res.dropna(subset=["pred", "actual"]).copy()
    if df.empty:
        return pd.DataFrame(columns=cols)
    df["err"] = df["pred"] - df["actual"]
    df["abs_err"] = df["err"].abs()
    df["sq_err"] = df["err"] ** 2
    per_location = _aggregate(df, ["location", "model", "horizon"]).rename(columns={"location": "location_name"})
    overall = _aggregate(df, ["model", "horizon"])
    overall.insert(0, "location_name", config.ALL_LOCATIONS)
    return pd.concat([per_location, overall], ignore_index=True)[cols]


# ----------------------------------------------------------------------------- dự báo thật
def make_forecasts(
    series: Mapping[str, pd.Series],
    horizon: int = config.FORECAST_DAYS,
    min_train: int = config.MIN_TRAIN_DAYS,
) -> tuple[list[tuple], dict[str, str]]:
    """Dự báo `horizon` ngày sau ngày dữ liệu cuối của từng địa điểm. Lỗi một địa điểm không dừng các nơi khác."""
    rows: list[tuple] = []
    failed: dict[str, str] = {}
    for name, y in series.items():
        try:
            fit = fit_model(y, min_train)
            base = y.index.max()
            dates, _, ar1 = predict(fit, base, horizon)
            for h, (d, v) in enumerate(zip(dates, ar1), start=1):
                rows.append((name, base.date(), d.date(), h, config.FORECAST_MODEL_NAME, round(float(v), 1)))
        except Exception as exc:  # noqa: BLE001
            failed[name] = f"{type(exc).__name__}: {exc}"
            log.warning("%s: không dự báo được: %s", name, exc)
    return rows, failed


# ----------------------------------------------------------------------------- ghi kết quả
def save_eval(conn: Any, ev: pd.DataFrame, run_id: str, run_at: datetime | None = None) -> int:
    run_at = run_at or datetime.now()
    rows = [
        (run_id, run_at, r.location_name, r.model, int(r.horizon),
         round(float(r.mae), 3), round(float(r.rmse), 3), int(r.n))
        for r in ev.itertuples(index=False)
    ]
    if rows:
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO mart.forecast_eval "
            "(run_id, run_at, location_name, model_name, horizon_days, mae_c, rmse_c, n_obs) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    return len(rows)


def save_forecasts(conn: Any, rows: list[tuple], run_id: str, created_at: datetime | None = None) -> int:
    created_at = created_at or datetime.now()
    if not rows:
        return 0
    cur = conn.cursor()
    # Chạy lại cùng ngày dữ liệu thì thay thế dự báo cũ của đúng địa điểm đó, không nhân đôi dòng
    for location, base_date in sorted({(r[0], r[1]) for r in rows}):
        cur.execute(
            "DELETE FROM mart.forecast_daily WHERE location_name = ? AND base_date = ? AND model_name = ?",
            location, base_date, config.FORECAST_MODEL_NAME,
        )
    cur.executemany(
        "INSERT INTO mart.forecast_daily "
        "(run_id, created_at, location_name, base_date, target_date, horizon_days, model_name, predicted_temp_max_c) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(run_id, created_at, *r) for r in rows],
    )
    conn.commit()
    return len(rows)


@dataclass
class ForecastSummary:
    locations_ok: int = 0
    failed: dict[str, str] = field(default_factory=dict)
    eval_rows: int = 0
    forecast_rows: int = 0
    mae_table: pd.DataFrame | None = None


def run(conn: Any, run_id: str) -> ForecastSummary:
    """Đọc chuỗi từ kho, đánh giá bằng kiểm thử ngược, dự báo và ghi kết quả về SQL Server."""
    series = load_series(conn)
    if not series:
        raise RuntimeError("Kho dữ liệu chưa có nhiệt độ để ước lượng mô hình")
    ev = evaluate(backtest(series))
    rows, failed = make_forecasts(series)
    summary = ForecastSummary(locations_ok=len({r[0] for r in rows}), failed=failed)
    summary.eval_rows = save_eval(conn, ev, run_id)
    summary.forecast_rows = save_forecasts(conn, rows, run_id)
    overall = ev[ev["location_name"] == config.ALL_LOCATIONS]
    if not overall.empty:
        summary.mae_table = overall.pivot(index="horizon", columns="model", values="mae").round(2)
    log.info("Mô hình: %d địa điểm dự báo được, %d dòng đánh giá, %d dòng dự báo",
             summary.locations_ok, summary.eval_rows, summary.forecast_rows)
    return summary
