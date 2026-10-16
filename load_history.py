from datetime import date, timedelta
import time

import pandas as pd
import pyodbc
import requests

from config import CONN_STR

# (tên, vĩ độ, kinh độ) - tọa độ gần đúng của trung tâm mỗi thành phố
LOCATIONS = [
    ("Hà Nội", 21.03, 105.85),
    ("Đà Nẵng", 16.05, 108.20),
    ("TP.HCM", 10.82, 106.63),
    ("Cần Thơ", 10.03, 105.78),
    ("Vũng Tàu", 10.35, 107.08),
]

URL = "https://archive-api.open-meteo.com/v1/archive"
START_DATE = "2020-01-01"
# Dữ liệu những ngày gần nhất chưa có ngay nên lùi 7 ngày cho chắc
END_DATE = (date.today() - timedelta(days=7)).isoformat()
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max"


def to_float(value):
    """Đổi giá trị thiếu (NaN) thành None để SQL Server lưu là NULL."""
    return None if pd.isna(value) else float(value)


def fetch_daily(lat, lon):
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "daily": DAILY,
        "timezone": "Asia/Bangkok",
    }
    resp = requests.get(URL, params=params, timeout=60)
    resp.raise_for_status()
    return pd.DataFrame(resp.json()["daily"])


def main():
    conn = pyodbc.connect(CONN_STR)
    cur = conn.cursor()
    cur.fast_executemany = True

    for name, lat, lon in LOCATIONS:
        print(f"Đang lấy dữ liệu: {name} ...")
        df = fetch_daily(lat, lon)

        rows = [
            (
                name,
                lat,
                lon,
                date.fromisoformat(r["time"]),
                to_float(r["temperature_2m_max"]),
                to_float(r["temperature_2m_min"]),
                to_float(r["precipitation_sum"]),
                to_float(r["wind_speed_10m_max"]),
            )
            for _, r in df.iterrows()
        ]

        # Xóa dữ liệu cũ của địa điểm này rồi nạp lại -> chạy lại nhiều lần không bị trùng
        cur.execute(
            "DELETE FROM staging.weather_daily_raw WHERE location_name = ?", name
        )
        cur.executemany(
            """
            INSERT INTO staging.weather_daily_raw
                (location_name, latitude, longitude, obs_date,
                 temp_max_c, temp_min_c, precipitation_mm, wind_max_kmh)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        print(f"  -> đã nạp {len(rows)} dòng")
        time.sleep(1)  # nghỉ 1 giây giữa các lần gọi để lịch sự với API

    conn.close()
    print("Xong!")


if __name__ == "__main__":
    main()