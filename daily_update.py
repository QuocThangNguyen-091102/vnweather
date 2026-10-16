"""
daily_update.py - Cập nhật dữ liệu mỗi ngày:
  1. Lấy dữ liệu quan trắc mới (chưa có trong staging) từ Open-Meteo archive
  2. Lưu dự báo 7 ngày tới của Open-Meteo để đối chiếu với thực tế sau này
  3. Chạy SCD2 địa điểm, nạp fact (MERGE) và kiểm tra chất lượng dữ liệu
  4. Chạy lại mô hình dự báo (forecast.py)
Thoát với mã 1 nếu có bước lỗi hoặc có phép kiểm tra FAIL,
để Task Scheduler ghi nhận lần chạy thất bại.
"""
import logging
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyodbc
import requests

import forecast
from config import CONN_STR

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORY_START = date(2020, 1, 1)
LAG_DAYS = 7  # dữ liệu lịch sử về chậm vài ngày nên lùi 7 ngày cho chắc
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"

LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "daily_update.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("daily_update")


def to_float(value):
    return None if pd.isna(value) else float(value)


def get_json(url, params, retries=3):
    """Gọi API, tự thử lại khi gặp lỗi mạng, bị giới hạn (429) hoặc lỗi máy chủ (5xx)."""
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=60)
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            log.warning("Gọi API lỗi (lần %d/%d): %s", attempt, retries, exc)
            if attempt == retries:
                raise
            time.sleep(5 * attempt)


def get_locations(conn):
    """Danh sách địa điểm lấy từ bảng khai báo, thêm địa điểm mới chỉ cần thêm dòng vào đó."""
    cur = conn.cursor()
    cur.execute(
        "SELECT location_name, latitude, longitude FROM staging.location_ref ORDER BY location_name"
    )
    return [(r[0], float(r[1]), float(r[2])) for r in cur.fetchall()]


def load_new_observations(conn, locations):
    """Chỉ lấy các ngày sau ngày cuối cùng đã có trong staging, tối đa đến (hôm nay - 7 ngày)."""
    end_date = date.today() - timedelta(days=LAG_DAYS)
    cur = conn.cursor()
    total = 0
    for name, lat, lon in locations:
        cur.execute(
            "SELECT MAX(obs_date) FROM staging.weather_daily_raw WHERE location_name = ?", name
        )
        last = cur.fetchone()[0]
        start_date = last + timedelta(days=1) if last else HISTORY_START
        if start_date > end_date:
            log.info("%s: không có dữ liệu mới (đã có đến %s)", name, last)
            continue

        data = get_json(ARCHIVE_URL, {
            "latitude": lat, "longitude": lon,
            "start_date": start_date.isoformat(), "end_date": end_date.isoformat(),
            "daily": DAILY, "timezone": "Asia/Bangkok",
        })
        df = pd.DataFrame(data["daily"])
        # Bỏ các ngày cuối chưa có số liệu để lần sau lấy lại, không ghi NULL cố định
        last_valid = df["temperature_2m_max"].last_valid_index()
        if last_valid is None:
            log.info("%s: API chưa có số liệu cho %s đến %s", name, start_date, end_date)
            continue
        df = df.loc[:last_valid]

        rows = [
            (name, lat, lon, date.fromisoformat(r.time),
             to_float(r.temperature_2m_max), to_float(r.temperature_2m_min),
             to_float(r.precipitation_sum), to_float(r.wind_speed_10m_max))
            for r in df.itertuples(index=False)
        ]
        # Xóa rồi nạp lại phần mới trong cùng một transaction nên chạy lại không bị trùng
        cur.execute(
            "DELETE FROM staging.weather_daily_raw WHERE location_name = ? AND obs_date >= ?",
            name, start_date,
        )
        cur.executemany(
            "INSERT INTO staging.weather_daily_raw "
            "(location_name, latitude, longitude, obs_date, "
            " temp_max_c, temp_min_c, precipitation_mm, wind_max_kmh) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        total += len(rows)
        log.info("%s: nạp thêm %d ngày (%s đến %s)", name, len(rows), rows[0][3], rows[-1][3])
    log.info("Tổng số dòng quan trắc mới: %d", total)


def store_api_forecast(conn, locations):
    """Lưu dự báo 1..7 ngày tới của Open-Meteo, để sau này đối chiếu với thực tế."""
    today = date.today()
    cur = conn.cursor()
    total = 0
    for name, lat, lon in locations:
        data = get_json(FORECAST_URL, {
            "latitude": lat, "longitude": lon,
            "daily": "temperature_2m_max", "timezone": "Asia/Bangkok",
            "forecast_days": 8,
        })
        daily = data["daily"]
        rows = []
        for t, v in zip(daily["time"], daily["temperature_2m_max"]):
            target = date.fromisoformat(t)
            horizon = (target - today).days
            if 1 <= horizon <= 7 and v is not None:
                rows.append((name, today, target, horizon, round(float(v), 1)))
        cur.execute(
            "DELETE FROM staging.api_forecast_raw WHERE location_name = ? AND base_date = ?",
            name, today,
        )
        cur.executemany(
            "INSERT INTO staging.api_forecast_raw "
            "(location_name, base_date, target_date, horizon_days, predicted_temp_max_c) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        total += len(rows)
    log.info("Đã lưu dự báo Open-Meteo: %d dòng", total)


def run_warehouse(conn):
    """SCD2 địa điểm trước, nạp fact sau."""
    cur = conn.cursor()
    cur.execute("EXEC dwh.usp_load_dim_location_scd2")
    conn.commit()
    cur.execute("EXEC dwh.usp_load_weather")
    changes = {row[0]: row[1] for row in cur.fetchall()}
    conn.commit()
    log.info("Nạp fact: %s", changes if changes else "không có thay đổi")


def run_dq(conn):
    """Chạy kiểm tra chất lượng, trả về số phép kiểm tra FAIL."""
    cur = conn.cursor()
    cur.execute("EXEC dwh.usp_run_dq_checks")
    results = cur.fetchall()
    conn.commit()
    failed = [r for r in results if r.status != "PASS"]
    for r in failed:
        log.error("Kiểm tra FAIL: %s (%d dòng lỗi)", r.check_name, r.bad_rows)
    log.info("Kiểm tra chất lượng: %d/%d PASS", len(results) - len(failed), len(results))
    return len(failed)


def run_step(conn, name, func, *args):
    """Chạy một bước, lỗi thì ghi log và hoàn tác phần dang dở, không làm sập các bước sau.

    Rollback chỉ có tác dụng nếu đang có transaction chưa commit; gọi khi không có
    transaction không gây lỗi nhờ khối try/except bên trong.
    """
    try:
        return True, func(conn, *args)
    except Exception:
        log.exception("Bước lỗi: %s", name)
        try:
            conn.rollback()
        except Exception:
            pass  # Không có transaction đang mở — bỏ qua
        return False, None


def main():
    log.info("===== Bắt đầu cập nhật hằng ngày =====")
    ok = True
    conn = pyodbc.connect(CONN_STR)
    try:
        locations = get_locations(conn)
        log.info("Số địa điểm: %d", len(locations))
        for name, func in (
            ("Nạp dữ liệu quan trắc mới", load_new_observations),
            ("Lưu dự báo Open-Meteo", store_api_forecast),
        ):
            step_ok, _ = run_step(conn, name, func, locations)
            ok = ok and step_ok

        step_ok, _ = run_step(conn, "Nạp kho dữ liệu", run_warehouse)
        ok = ok and step_ok

        step_ok, n_fail = run_step(conn, "Kiểm tra chất lượng", run_dq)
        ok = ok and step_ok and not n_fail
    finally:
        conn.close()

    try:
        forecast.main()
    except Exception:
        log.exception("Bước lỗi: mô hình dự báo")
        ok = False

    log.info("===== %s =====", "Hoàn tất" if ok else "Hoàn tất nhưng có lỗi")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())