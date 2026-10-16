"""
forecast.py - Dự báo nhiệt độ cao nhất hằng ngày cho từng địa điểm.

So sánh 3 phương pháp bằng backtest cuốn chiếu (dự báo trước 1..7 ngày):
  persistence : lặp lại giá trị của ngày cuối cùng
  clim        : đường khí hậu theo mùa (hồi quy sin/cos + xu hướng)
  clim_ar1    : đường khí hậu + phần lệch hiện tại giảm dần theo hệ số phi
Kết quả ghi vào mart.forecast_eval và mart.forecast_daily.
"""
from datetime import datetime

import numpy as np
import pandas as pd
import pyodbc

from config import CONN_STR

EPOCH = pd.Timestamp("2020-01-01")
HORIZON = 7           # backtest: dự báo trước tối đa 7 ngày
FORECAST_DAYS = 14    # dự báo thật: 14 ngày sau ngày dữ liệu cuối
BACKTEST_DAYS = 730   # backtest trên 2 năm gần nhất
ORIGIN_STEP = 7       # cứ 7 ngày lấy một mốc để dự báo
N_HARMONICS = 3       # số cặp sin/cos mô tả mùa
MODEL_NAME = "clim_ar1"


def load_series(conn):
    """Đọc nhiệt độ cao nhất từ kho, trả về {tên địa điểm: chuỗi theo ngày}."""
    sql = """
        SELECT l.location_name, d.full_date, f.temp_max_c
        FROM dwh.fact_weather_daily AS f
        JOIN dwh.dim_date     AS d ON d.date_key     = f.date_key
        JOIN dwh.dim_location AS l ON l.location_key = f.location_key
        WHERE f.temp_max_c IS NOT NULL
    """
    cur = conn.cursor()
    cur.execute(sql)
    df = pd.DataFrame.from_records(
        [tuple(r) for r in cur.fetchall()],
        columns=["location_name", "full_date", "temp_max_c"],
    )
    df["full_date"] = pd.to_datetime(df["full_date"])
    df["temp_max_c"] = df["temp_max_c"].astype(float)

    series = {}
    for name, g in df.groupby("location_name"):
        y = g.set_index("full_date")["temp_max_c"].sort_index().asfreq("D")
        series[name] = y.interpolate(limit=3).dropna()
    return series


def design_matrix(t):
    """Cột: hằng số, xu hướng, rồi các cặp sin/cos theo chu kỳ năm."""
    cols = [np.ones_like(t), t / 3650.0]
    for k in range(1, N_HARMONICS + 1):
        w = 2 * np.pi * k * t / 365.25
        cols += [np.sin(w), np.cos(w)]
    return np.column_stack(cols)


def fit_model(y):
    """Khớp đường khí hậu, ước lượng hệ số phi và phần lệch của ngày cuối."""
    t = (y.index - EPOCH).days.values.astype(float)
    beta, *_ = np.linalg.lstsq(design_matrix(t), y.values, rcond=None)
    resid = y.values - design_matrix(t) @ beta
    phi = float(np.corrcoef(resid[:-1], resid[1:])[0, 1])
    phi = min(max(phi, 0.0), 0.99)
    return beta, phi, resid[-1]


def predict(beta, phi, last_anom, last_date, horizon):
    dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=horizon)
    t = (dates - EPOCH).days.values.astype(float)
    clim = design_matrix(t) @ beta
    h = np.arange(1, horizon + 1)
    return dates, clim, clim + (phi ** h) * last_anom


def backtest(series):
    """Lùi về từng mốc trong quá khứ, chỉ dùng dữ liệu đến mốc đó để dự báo 7 ngày tiếp theo."""
    rows = []
    for name, y in series.items():
        last = y.index.max()
        origins = pd.date_range(
            last - pd.Timedelta(days=BACKTEST_DAYS),
            last - pd.Timedelta(days=HORIZON),
            freq=f"{ORIGIN_STEP}D",
        )
        for origin in origins:
            train = y.loc[:origin]
            actual = y.loc[origin + pd.Timedelta(days=1): origin + pd.Timedelta(days=HORIZON)]
            if len(actual) < HORIZON:
                continue
            beta, phi, last_anom = fit_model(train)
            _, clim, ar1 = predict(beta, phi, last_anom, origin, HORIZON)
            persistence = np.full(HORIZON, train.iloc[-1])
            for h in range(HORIZON):
                for model, pred in (("persistence", persistence),
                                    ("clim", clim),
                                    ("clim_ar1", ar1)):
                    rows.append((name, origin, h + 1, model, pred[h], actual.iloc[h]))
    return pd.DataFrame(rows, columns=["location", "origin", "horizon", "model", "pred", "actual"])


def evaluate(res):
    """Tính MAE và RMSE theo từng phương pháp và số ngày dự báo trước."""
    res = res.dropna(subset=["pred", "actual"]).copy()
    res["err"] = res["pred"] - res["actual"]
    g = res.groupby(["model", "horizon"])["err"]
    return pd.DataFrame({
        "mae": g.apply(lambda e: e.abs().mean()),
        "rmse": g.apply(lambda e: np.sqrt((e ** 2).mean())),
        "n": g.size(),
    }).reset_index()


def make_forecasts(series):
    rows = []
    for name, y in series.items():
        beta, phi, last_anom = fit_model(y)
        base = y.index.max()
        dates, _, ar1 = predict(beta, phi, last_anom, base, FORECAST_DAYS)
        for h, (d, v) in enumerate(zip(dates, ar1), start=1):
            rows.append((name, base.date(), d.date(), h, MODEL_NAME, round(float(v), 1)))
    return rows


def save_eval(conn, ev):
    cur = conn.cursor()
    run_at = datetime.now()
    cur.executemany(
        "INSERT INTO mart.forecast_eval (run_at, model_name, horizon_days, mae_c, rmse_c, n_obs) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [(run_at, r.model, int(r.horizon), float(r.mae), float(r.rmse), int(r.n))
         for r in ev.itertuples(index=False)],
    )
    conn.commit()


def save_forecasts(conn, rows):
    cur = conn.cursor()
    created_at = datetime.now()
    # Chạy lại cùng ngày dữ liệu thì thay thế, không nhân đôi dòng
    for base_date in {r[1] for r in rows}:
        cur.execute("DELETE FROM mart.forecast_daily WHERE base_date = ? AND model_name = ?",
                    base_date, MODEL_NAME)
    cur.executemany(
        "INSERT INTO mart.forecast_daily "
        "(created_at, location_name, base_date, target_date, horizon_days, model_name, predicted_temp_max_c) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(created_at, *r) for r in rows],
    )
    conn.commit()


def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    with pyodbc.connect(CONN_STR) as conn:
        series = load_series(conn)
        print("Địa điểm:", ", ".join(series))

        ev = evaluate(backtest(series))
        print("\nSai số MAE (độ C) theo số ngày dự báo trước:")
        print(ev.pivot(index="horizon", columns="model", values="mae").round(2))

        save_eval(conn, ev)
        rows = make_forecasts(series)
        save_forecasts(conn, rows)
        print(f"\nĐã ghi {len(ev)} dòng đánh giá và {len(rows)} dòng dự báo vào SQL Server.")


if __name__ == "__main__":
    main()