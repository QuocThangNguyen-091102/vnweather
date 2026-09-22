"""
ingestion.py - Thu thập dữ liệu từ Open-Meteo và nạp vào tầng staging.

Dữ liệu API được chuyển thành bảng có cấu trúc (landing/staging), chưa làm sạch hay biến đổi
nghiệp vụ. Payload JSON gốc không được lưu lại.

Hai chế độ dùng chung một hàm nạp (không lặp code):
  - "history"     : nạp lại toàn bộ lịch sử từ HISTORY_START (bootstrap)
  - "incremental" : chỉ nạp các ngày sau ngày cuối cùng đã có (chạy hằng ngày)
Mỗi địa điểm được nạp trong một transaction riêng; một địa điểm lỗi không làm hỏng các địa điểm khác.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Callable, Sequence

import pandas as pd
import requests

from . import config
from .data_quality import drop_duplicate_dates, validate_observations

log = logging.getLogger(__name__)

Location = tuple  # (tên, vĩ độ, kinh độ)


class TransientAPIError(Exception):
    """Lỗi tạm thời của API (429 hoặc 5xx), đáng để thử lại."""


# ----------------------------------------------------------------------------- gọi API
def get_json(
    url: str,
    params: dict[str, Any],
    *,
    retries: int = config.API_MAX_RETRIES,
    timeout: int = config.API_TIMEOUT_SECONDS,
    backoff: float = config.API_BACKOFF_SECONDS,
    http_get: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """
    Gọi API và trả về JSON. Thử lại khi lỗi mạng, hết thời gian chờ, HTTP 429 hoặc 5xx.
    Lỗi 4xx khác (tham số sai) không được thử lại vì thử lại cũng không thay đổi kết quả.
    """
    http_get = http_get or requests.get
    transient = (requests.ConnectionError, requests.Timeout, TransientAPIError)
    for attempt in range(1, retries + 1):
        try:
            resp = http_get(url, params=params, timeout=timeout)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise TransientAPIError(f"HTTP {resp.status_code}")
            resp.raise_for_status()
            return resp.json()
        except transient as exc:
            log.warning("Gọi API lỗi (lần %d/%d): %s", attempt, retries, exc)
            if attempt == retries:
                raise
            sleep(backoff * attempt)
    raise RuntimeError("Không đạt tới đây")  # pragma: no cover


def _none_if_nan(value: Any) -> float | None:
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) else v


def _column(daily: dict[str, Any], key: str, n: int) -> list[Any]:
    values = daily.get(key)
    if values is None:
        return [None] * n
    if len(values) != n:
        raise ValueError(f"Cột '{key}' có {len(values)} giá trị, khác số ngày {n}")
    return list(values)


def parse_archive_daily(payload: Any) -> pd.DataFrame:
    """
    Chuyển phản hồi của archive API thành bảng (obs_date, temp_max_c, temp_min_c,
    precipitation_mm, wind_max_kmh). Các ngày cuối chưa có số liệu (null nhiệt độ cao nhất) bị
    cắt bỏ để lần sau lấy lại, thay vì ghi NULL cố định vào staging.
    """
    daily = payload.get("daily") if isinstance(payload, dict) else None
    if not daily or "time" not in daily:
        raise ValueError("Phản hồi API không có khối 'daily'")
    n = len(daily["time"])
    df = pd.DataFrame({
        "obs_date": [date.fromisoformat(t) for t in daily["time"]],
        "temp_max_c": pd.to_numeric(_column(daily, "temperature_2m_max", n), errors="coerce"),
        "temp_min_c": pd.to_numeric(_column(daily, "temperature_2m_min", n), errors="coerce"),
        "precipitation_mm": pd.to_numeric(_column(daily, "precipitation_sum", n), errors="coerce"),
        "wind_max_kmh": pd.to_numeric(_column(daily, "wind_speed_10m_max", n), errors="coerce"),
    })
    last_valid = df["temp_max_c"].last_valid_index()
    if last_valid is None:
        return df.iloc[0:0]
    return df.loc[:last_valid].reset_index(drop=True)


def parse_forecast_daily(payload: Any, today: date) -> list[tuple[date, int, float]]:
    """Trả về các bộ (ngày dự báo, số ngày dự báo trước, nhiệt độ cao nhất) cho 1..7 ngày tới."""
    daily = payload.get("daily") if isinstance(payload, dict) else None
    if not daily or "time" not in daily or "temperature_2m_max" not in daily:
        raise ValueError("Phản hồi dự báo không có 'daily.temperature_2m_max'")
    out = []
    for t, v in zip(daily["time"], daily["temperature_2m_max"]):
        target = date.fromisoformat(t)
        horizon = (target - today).days
        value = _none_if_nan(v)
        if 1 <= horizon <= config.API_FORECAST_MAX_HORIZON and value is not None:
            out.append((target, horizon, round(value, 1)))
    return out


def fetch_archive(lat: float, lon: float, start: date, end: date, get: Callable[..., Any] = get_json) -> pd.DataFrame:
    payload = get(config.ARCHIVE_URL, {
        "latitude": lat, "longitude": lon,
        "start_date": start.isoformat(), "end_date": end.isoformat(),
        "daily": ",".join(config.ARCHIVE_DAILY_VARIABLES), "timezone": config.API_TIMEZONE,
    })
    return parse_archive_daily(payload)


# ----------------------------------------------------------------------------- lập cửa sổ thời gian
def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    return value


def compute_window(last_obs_date: Any, today: date, mode: str) -> tuple[date, date] | None:
    """
    Khoảng ngày cần tải. Trả về None nếu không có gì mới.
    Ngày cuối = hôm nay trừ độ trễ của nguồn dữ liệu lịch sử.
    """
    if mode not in ("history", "incremental"):
        raise ValueError(f"mode không hợp lệ: {mode}")
    end = today - timedelta(days=config.ARCHIVE_LAG_DAYS)
    last = _as_date(last_obs_date)
    start = config.HISTORY_START if (mode == "history" or last is None) else last + timedelta(days=1)
    if start > end:
        return None
    return start, end


# ----------------------------------------------------------------------------- kết quả
@dataclass
class IngestResult:
    total: int = 0
    loaded: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)   # không có dữ liệu mới, không phải lỗi
    failed: dict[str, str] = field(default_factory=dict)
    rows: int = 0

    @property
    def ok_count(self) -> int:
        return len(self.loaded) + len(self.skipped)

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        text = f"{self.ok_count}/{self.total} địa điểm thành công, {self.rows} dòng mới"
        if self.failed:
            text += "; lỗi: " + ", ".join(self.failed)
        return text


# ----------------------------------------------------------------------------- staging
def get_locations(conn: Any) -> list[Location]:
    """Danh sách địa điểm lấy từ staging.location_ref (nguồn duy nhất, không hard-code)."""
    cur = conn.cursor()
    cur.execute("SELECT location_name, latitude, longitude FROM staging.location_ref ORDER BY location_name")
    locations = [(r[0], float(r[1]), float(r[2])) for r in cur.fetchall()]
    if not locations:
        raise RuntimeError("staging.location_ref đang rỗng, hãy chạy sql/01_setup/002_staging_tables.sql")
    return locations


_INSERT_OBS = (
    "INSERT INTO staging.weather_daily_raw "
    "(location_name, latitude, longitude, obs_date, temp_max_c, temp_min_c, precipitation_mm, "
    " wind_max_kmh, source, pipeline_run_id) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
)


def ingest_observations(
    conn: Any,
    locations: Sequence[Location],
    run_id: str,
    mode: str = "incremental",
    today: date | None = None,
    fetch: Callable[[float, float, date, date], pd.DataFrame] = fetch_archive,
    sleep: Callable[[float], None] = time.sleep,
) -> IngestResult:
    """Nạp quan trắc mới vào staging.weather_daily_raw, từng địa điểm một transaction."""
    today = today or date.today()
    result = IngestResult(total=len(locations))
    cur = conn.cursor()
    cur.fast_executemany = True
    for name, lat, lon in locations:
        try:
            cur.execute("SELECT MAX(obs_date) FROM staging.weather_daily_raw WHERE location_name = ?", name)
            last = cur.fetchone()[0]
            window = compute_window(last, today, mode)
            if window is None:
                result.skipped.append(name)
                log.info("%s: không có dữ liệu mới (đã có đến %s)", name, last)
                continue
            start, end = window
            df = fetch(lat, lon, start, end)
            sleep(1)  # nghỉ giữa các lần gọi để lịch sự với API miễn phí
            if df.empty:
                result.skipped.append(name)
                log.info("%s: API chưa có số liệu cho %s đến %s", name, start, end)
                continue
            for issue in validate_observations(df):
                log.warning("%s: kiểm tra trước khi nạp: %s = %d", name, issue.check, issue.count)
            df = drop_duplicate_dates(df)
            rows = [
                (name, lat, lon, r.obs_date, _none_if_nan(r.temp_max_c), _none_if_nan(r.temp_min_c),
                 _none_if_nan(r.precipitation_mm), _none_if_nan(r.wind_max_kmh),
                 config.SOURCE_ARCHIVE, run_id)
                for r in df.itertuples(index=False)
            ]
            # Xóa rồi nạp lại trong cùng một transaction: chạy lại nhiều lần không bị trùng
            if mode == "history":
                cur.execute("DELETE FROM staging.weather_daily_raw WHERE location_name = ?", name)
            else:
                cur.execute(
                    "DELETE FROM staging.weather_daily_raw WHERE location_name = ? AND obs_date >= ?",
                    name, start,
                )
            cur.executemany(_INSERT_OBS, rows)
            conn.commit()
            result.loaded.append(name)
            result.rows += len(rows)
            log.info("%s: nạp thêm %d ngày (%s đến %s)", name, len(rows), rows[0][3], rows[-1][3])
        except Exception as exc:  # noqa: BLE001 - lỗi một địa điểm không được làm hỏng các địa điểm khác
            conn.rollback()
            result.failed[name] = f"{type(exc).__name__}: {exc}"
            log.exception("%s: nạp quan trắc thất bại", name)
    log.info("Quan trắc: %s", result.summary())
    return result


def store_api_forecast(
    conn: Any,
    locations: Sequence[Location],
    run_id: str,
    today: date | None = None,
    get: Callable[..., Any] = get_json,
    sleep: Callable[[float], None] = time.sleep,
) -> IngestResult:
    """Lưu dự báo 1..7 ngày tới của Open-Meteo để sau này đối chiếu với số đo thực tế."""
    today = today or date.today()
    result = IngestResult(total=len(locations))
    cur = conn.cursor()
    for name, lat, lon in locations:
        try:
            payload = get(config.FORECAST_URL, {
                "latitude": lat, "longitude": lon, "daily": "temperature_2m_max",
                "timezone": config.API_TIMEZONE, "forecast_days": config.API_FORECAST_DAYS,
            })
            sleep(1)
            rows = [(name, today, target, horizon, temp, run_id)
                    for target, horizon, temp in parse_forecast_daily(payload, today)]
            cur.execute("DELETE FROM staging.api_forecast_raw WHERE location_name = ? AND base_date = ?", name, today)
            if rows:
                cur.executemany(
                    "INSERT INTO staging.api_forecast_raw "
                    "(location_name, base_date, target_date, horizon_days, predicted_temp_max_c, pipeline_run_id) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    rows,
                )
            conn.commit()
            result.loaded.append(name)
            result.rows += len(rows)
        except Exception as exc:  # noqa: BLE001
            conn.rollback()
            result.failed[name] = f"{type(exc).__name__}: {exc}"
            log.exception("%s: lưu dự báo Open-Meteo thất bại", name)
    log.info("Dự báo Open-Meteo: %s", result.summary())
    return result
