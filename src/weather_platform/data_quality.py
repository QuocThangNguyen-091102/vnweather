"""
data_quality.py - Kiểm tra chất lượng dữ liệu ở hai lớp.

Lớp 1 (Python, trước khi nạp): `validate_observations` soi từng lô dữ liệu vừa tải từ API.
Lớp 2 (SQL, sau khi nạp): stored procedure `dwh.usp_run_dq_checks` đối soát staging với fact,
kiểm tra SCD2 và độ tươi của dữ liệu. Kết quả ghi vào `dwh.dq_check_log`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable

import pandas as pd

from .config import MAX_LAG_DAYS, TEMP_VALID_MAX_C, TEMP_VALID_MIN_C

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------------- lớp 1: Python
@dataclass(frozen=True)
class Issue:
    check: str
    count: int


def find_missing_dates(dates: Iterable[Any]) -> list[date]:
    """Các ngày còn thiếu giữa ngày đầu và ngày cuối của chuỗi."""
    s = pd.to_datetime(pd.Series(list(dates))).dt.normalize().drop_duplicates().sort_values()
    if s.empty:
        return []
    full = pd.date_range(s.iloc[0], s.iloc[-1], freq="D")
    return [d.date() for d in full.difference(pd.DatetimeIndex(s))]


def validate_observations(
    df: pd.DataFrame,
    temp_min: float = TEMP_VALID_MIN_C,
    temp_max: float = TEMP_VALID_MAX_C,
) -> list[Issue]:
    """
    Kiểm tra một lô quan trắc của MỘT địa điểm. Chỉ trả về các vấn đề có số lượng > 0.
    Cột cần có: obs_date, temp_max_c, temp_min_c, precipitation_mm.
    """
    if df.empty:
        return []
    tmax, tmin, rain = df["temp_max_c"], df["temp_min_c"], df["precipitation_mm"]
    found = {
        "duplicate_dates": int(df["obs_date"].duplicated().sum()),
        "missing_dates": len(find_missing_dates(df["obs_date"])),
        "temp_min_gt_max": int((tmin > tmax).sum()),
        "negative_rain": int((rain < 0).sum()),
        "temp_out_of_range": int(
            ((tmax < temp_min) | (tmax > temp_max) | (tmin < temp_min) | (tmin > temp_max)).sum()
        ),
        "null_temperature": int((tmax.isna() | tmin.isna()).sum()),
    }
    return [Issue(name, n) for name, n in found.items() if n > 0]


def drop_duplicate_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Giữ dòng cuối cùng khi trùng ngày, để không vi phạm ràng buộc UNIQUE ở staging."""
    return df.drop_duplicates(subset="obs_date", keep="last").reset_index(drop=True)


# ----------------------------------------------------------------------------- lớp 2: SQL
@dataclass(frozen=True)
class CheckResult:
    check_name: str
    bad_rows: int
    status: str

    @property
    def passed(self) -> bool:
        return self.status == "PASS"


def run_sql_checks(conn: Any, run_id: str | None) -> list[CheckResult]:
    """Chạy `dwh.usp_run_dq_checks` và trả về kết quả của lần chạy này."""
    cur = conn.cursor()
    cur.execute(
        "EXEC dwh.usp_run_dq_checks @run_id = ?, @temp_min_c = ?, @temp_max_c = ?, @max_lag_days = ?",
        run_id, TEMP_VALID_MIN_C, TEMP_VALID_MAX_C, MAX_LAG_DAYS,
    )
    rows = cur.fetchall()
    conn.commit()
    return [CheckResult(str(r.check_name), int(r.bad_rows), str(r.status)) for r in rows]


def fetch_quality_metrics(conn: Any) -> dict[str, Any]:
    """Đọc một dòng chỉ số chất lượng từ view `mart.v_data_quality_metrics`."""
    cur = conn.cursor()
    cur.execute("SELECT * FROM mart.v_data_quality_metrics")
    row = cur.fetchone()
    if row is None:
        return {}
    return {col[0]: value for col, value in zip(cur.description, row)}
