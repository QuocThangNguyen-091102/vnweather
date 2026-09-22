"""
warehouse.py - Nạp kho dữ liệu (dwh) từ staging bằng stored procedure.

Thứ tự bắt buộc: dimension địa điểm (SCD2) TRƯỚC, bảng fact SAU. Nếu đảo ngược, các dòng fact
của địa điểm mới sẽ bị bỏ sót vì chưa có dimension tương ứng.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

log = logging.getLogger(__name__)


def load_dim_location(conn: Any, effective_date: date | None = None) -> None:
    """Cập nhật dim_location theo SCD Type 2 từ staging.location_ref."""
    cur = conn.cursor()
    if effective_date is None:
        cur.execute("EXEC dwh.usp_load_dim_location_scd2")
    else:
        cur.execute("EXEC dwh.usp_load_dim_location_scd2 @effective_date = ?", effective_date)
    conn.commit()
    log.info("Đã chạy SCD2 cho dim_location")


def load_facts(conn: Any) -> dict[str, int]:
    """Nạp fact_weather_daily bằng MERGE. Trả về số dòng INSERT / UPDATE."""
    cur = conn.cursor()
    cur.execute("EXEC dwh.usp_load_weather")
    changes = {str(row[0]): int(row[1]) for row in cur.fetchall()}
    conn.commit()
    log.info("Nạp fact: %s", changes if changes else "không có thay đổi")
    return changes


def load_warehouse(conn: Any) -> dict[str, int]:
    load_dim_location(conn)
    return load_facts(conn)
