"""
db.py - Kết nối SQL Server và các hàm đọc dữ liệu dùng chung.

`pyodbc` chỉ được nạp khi thật sự kết nối, nên các phần còn lại của dự án (và bộ kiểm thử)
không cần cài driver ODBC.
"""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from typing import Any, Iterator, Sequence

import pandas as pd

from .config import DbSettings, get_db_settings


def build_connection_string(settings: DbSettings | None = None) -> str:
    """Ghép chuỗi kết nối ODBC từ cấu hình."""
    s = settings or get_db_settings()
    parts = [
        f"DRIVER={{{s.driver}}}",
        f"SERVER={s.server}",
        f"DATABASE={s.database}",
    ]
    if s.trusted_connection:
        parts.append("Trusted_Connection=yes")
    else:
        if not s.user:
            raise ValueError("DB_TRUSTED_CONNECTION=no nhưng chưa khai báo DB_USER / DB_PASSWORD")
        parts.append(f"UID={s.user}")
        parts.append(f"PWD={s.password}")
    parts.append("TrustServerCertificate=" + ("yes" if s.trust_server_certificate else "no"))
    return ";".join(parts) + ";"


def connect(settings: DbSettings | None = None):
    """Mở kết nối mới tới SQL Server (autocommit tắt, gọi commit() sau khi ghi)."""
    import pyodbc  # nạp muộn để kiểm thử không cần driver

    return pyodbc.connect(build_connection_string(settings))


@contextmanager
def connection(settings: DbSettings | None = None) -> Iterator[Any]:
    conn = connect(settings)
    try:
        yield conn
    finally:
        conn.close()


def rows_to_frame(columns: Sequence[str], rows: Sequence[Sequence[Any]]) -> pd.DataFrame:
    """Chuyển danh sách dòng thành DataFrame, đổi kiểu DECIMAL của SQL Server sang float."""
    df = pd.DataFrame.from_records([tuple(r) for r in rows], columns=list(columns))
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = df[col].map(lambda v: float(v) if isinstance(v, Decimal) else v).astype(float)
    return df


def fetch_frame(conn: Any, sql: str, params: Sequence[Any] = ()) -> pd.DataFrame:
    """Chạy truy vấn SELECT và trả về DataFrame."""
    cur = conn.cursor()
    cur.execute(sql, *params)
    columns = [c[0] for c in cur.description]
    return rows_to_frame(columns, cur.fetchall())
