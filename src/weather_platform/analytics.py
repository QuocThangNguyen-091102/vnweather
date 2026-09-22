"""
analytics.py - Các phép tính thuần pandas dùng cho dashboard (không phụ thuộc Streamlit hay SQL).

Tách riêng để kiểm thử được. Điểm quan trọng về phương pháp: ngưỡng "nóng bất thường" (P95) được tính từ
một GIAI ĐOẠN THAM CHIẾU CỐ ĐỊNH, không phụ thuộc khoảng năm mà người dùng chọn để xem.
"""
from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd


def p95_thresholds(
    daily: pd.DataFrame, ref_start_year: int, ref_end_year: int, quantile: float = 0.95
) -> pd.DataFrame:
    """Phân vị của nhiệt độ cao nhất theo (địa điểm, tháng), tính trong giai đoạn tham chiếu cố định."""
    ref = daily[daily["year_num"].between(ref_start_year, ref_end_year)]
    return (
        ref.groupby(["location_name", "month_num"])["temp_max_c"]
        .quantile(quantile).rename("p95").reset_index()
    )


def flag_extremes(sel: pd.DataFrame, thresholds: pd.DataFrame, heavy_rain_mm: float) -> pd.DataFrame:
    """Đánh dấu ngày nóng bất thường (vượt P95 tham chiếu) và ngày có lượng mưa >= ngưỡng."""
    out = sel.merge(thresholds, on=["location_name", "month_num"], how="left")
    out["hot_day"] = out["temp_max_c"] > out["p95"]
    out["heavy_rain"] = out["precipitation_mm"] >= heavy_rain_mm
    return out


def extremes_by_year(flagged: pd.DataFrame) -> pd.DataFrame:
    return (
        flagged.groupby(["location_name", "year_num"])
        .agg(hot_days=("hot_day", "sum"), heavy_rain_days=("heavy_rain", "sum"), days=("full_date", "count"))
        .reset_index()
    )


def monthly_temperature(sel: pd.DataFrame) -> pd.DataFrame:
    return sel.groupby(["location_name", "month_num"])["temp_max_c"].mean().reset_index()


def monthly_rainfall(sel: pd.DataFrame, min_days: int = 28) -> pd.DataFrame:
    """Lượng mưa tháng trung bình qua các năm; bỏ các tháng chưa đủ dữ liệu."""
    monthly = (
        sel.groupby(["location_name", "year_num", "month_num"])
        .agg(total=("precipitation_mm", "sum"), days=("full_date", "count"))
        .reset_index()
    )
    monthly = monthly[monthly["days"] >= min_days]
    return monthly.groupby(["location_name", "month_num"])["total"].mean().reset_index()


def yearly_temperature(sel: pd.DataFrame, min_days: int = 360) -> pd.DataFrame:
    """Nhiệt độ cao nhất trung bình theo năm; chỉ giữ năm đủ dữ liệu để không làm lệch trung bình."""
    yearly = (
        sel.groupby(["location_name", "year_num"])
        .agg(temp=("temp_max_c", "mean"), days=("full_date", "count"))
        .reset_index()
    )
    return yearly[yearly["days"] >= min_days]


def summarize_location(d: pd.DataFrame, today: date) -> dict[str, Any]:
    """Các chỉ số chính của một địa điểm: ngày dữ liệu gần nhất, độ trễ, nhiệt độ, mưa 30 ngày."""
    d = d.dropna(subset=["temp_max_c"]).sort_values("full_date")
    if d.empty:
        return {}
    last = d.iloc[-1]
    last30 = d.tail(30)
    last_date = pd.Timestamp(last["full_date"]).date()
    return {
        "last_date": last_date,
        "lag_days": (today - last_date).days,
        "temp_last": float(last["temp_max_c"]),
        "temp_avg_30": float(last30["temp_max_c"].mean()),
        "rain_30": float(last30["precipitation_mm"].sum()),
    }
