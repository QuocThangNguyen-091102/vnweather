"""
config.py - Cấu hình tập trung cho toàn bộ dự án.

Thông tin kết nối SQL Server đọc từ biến môi trường hoặc từ file `.env` ở thư mục gốc
(xem `.env.example`). Biến môi trường thật luôn được ưu tiên hơn file `.env`.
Các hằng số nghiệp vụ (nguồn API, tham số mô hình, ngưỡng kiểm tra) đặt ở đây để không
bị lặp lại ở nhiều file.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOG_DIR = PROJECT_ROOT / "logs"

# --------------------------------------------------------------------------- nguồn dữ liệu
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
HISTORY_START = date(2020, 1, 1)
ARCHIVE_LAG_DAYS = 7          # dữ liệu lịch sử (tái phân tích) về chậm khoảng 7 ngày
ARCHIVE_DAILY_VARIABLES = (
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "wind_speed_10m_max",
)
API_TIMEZONE = "Asia/Bangkok"
API_TIMEOUT_SECONDS = 60
API_MAX_RETRIES = 3
API_BACKOFF_SECONDS = 5
API_FORECAST_DAYS = 8         # lấy 8 ngày để có đủ 7 ngày sau ngày hôm nay
API_FORECAST_MAX_HORIZON = 7
SOURCE_ARCHIVE = "open-meteo-archive"
SOURCE_FORECAST = "open-meteo-forecast"

# --------------------------------------------------------------------------- kiểm tra chất lượng
TEMP_VALID_MIN_C = -10.0      # ngoài khoảng này với Việt Nam là bất thường
TEMP_VALID_MAX_C = 50.0
MAX_LAG_DAYS = 10             # độ trễ tối đa chấp nhận được: 7 ngày của nguồn cộng 3 ngày dự phòng

# --------------------------------------------------------------------------- mô hình dự báo
ALL_LOCATIONS = "ALL"         # nhãn lưu trong DB cho kết quả gộp mọi địa điểm
FORECAST_MODEL_NAME = "clim_ar1"
BACKTEST_HORIZON = 7          # kiểm thử ngược: dự báo trước 1..7 ngày
FORECAST_DAYS = 14            # dự báo thật: 14 ngày sau ngày dữ liệu cuối
BACKTEST_DAYS = 730           # kiểm thử ngược trên 2 năm gần nhất
ORIGIN_STEP_DAYS = 7          # cứ 7 ngày lấy một mốc dự báo (rolling-origin, bước 7 ngày)
N_HARMONICS = 3               # số cặp sin/cos mô tả tính mùa
MIN_TRAIN_DAYS = 365          # cần ít nhất 1 năm dữ liệu để ước lượng tính mùa
EPOCH = date(2020, 1, 1)      # gốc thời gian cho biến xu hướng

# --------------------------------------------------------------------------- phân tích (dashboard)
BASELINE_START_YEAR = 2020    # giai đoạn tham chiếu cố định cho ngưỡng P95
BASELINE_END_YEAR = 2025
DEFAULT_HEAVY_RAIN_MM = 50    # ngưỡng phân tích của đề tài, không phải phân loại khí tượng chính thức

# --------------------------------------------------------------------------- cơ sở dữ liệu
_TRUE = {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class DbSettings:
    server: str = "localhost"
    database: str = "VNDataPlatform"
    driver: str = "ODBC Driver 18 for SQL Server"
    trusted_connection: bool = True
    trust_server_certificate: bool = True
    user: str = ""
    password: str = ""


def parse_dotenv(text: str) -> dict[str, str]:
    """Đọc nội dung file .env dạng KEY=VALUE, bỏ qua dòng trống và dòng chú thích."""
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """
    Đọc file .env (nếu có): thư mục gốc dự án trước, thư mục hiện tại sau.
    Không ghi đè biến môi trường đã tồn tại.
    """
    candidates = [path] if path else [PROJECT_ROOT / ".env", Path.cwd() / ".env"]
    for candidate in candidates:
        if candidate.is_file():
            values = parse_dotenv(candidate.read_text(encoding="utf-8"))
            for key, value in values.items():
                os.environ.setdefault(key, value)
            return values
    return {}


def _flag(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in _TRUE


def get_db_settings(env: Mapping[str, str] | None = None) -> DbSettings:
    """Tạo cấu hình DB từ biến môi trường (hoặc từ `env` được truyền vào, dùng cho kiểm thử)."""
    if env is None:
        load_env_file()
        env = os.environ
    return DbSettings(
        server=env.get("DB_SERVER", "localhost"),
        database=env.get("DB_NAME", "VNDataPlatform"),
        driver=env.get("DB_DRIVER", "ODBC Driver 18 for SQL Server"),
        trusted_connection=_flag(env.get("DB_TRUSTED_CONNECTION"), True),
        trust_server_certificate=_flag(env.get("DB_TRUST_SERVER_CERTIFICATE"), True),
        user=env.get("DB_USER", ""),
        password=env.get("DB_PASSWORD", ""),
    )
