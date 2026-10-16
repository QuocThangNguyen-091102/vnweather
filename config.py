"""
config.py - Cấu hình tập trung cho toàn bộ dự án.
Đọc biến môi trường từ file .env (nếu có) hoặc từ environment thực.
Tạo file .env từ .env.example và điền giá trị trước khi chạy.
"""
import os
from pathlib import Path

# Tự động nạp .env nếu có thư viện python-dotenv
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass  # Không có dotenv thì đọc từ environment trực tiếp

_SERVER   = os.getenv("DB_SERVER", "localhost")
_DB       = os.getenv("DB_NAME",   "VNDataPlatform")
_DRIVER   = os.getenv("DB_DRIVER", "ODBC Driver 18 for SQL Server")
_USER     = os.getenv("DB_USER",   "")
_PASSWORD = os.getenv("DB_PASSWORD", "")

if _USER and _PASSWORD:
    # SQL Server Authentication
    CONN_STR = (
        f"DRIVER={{{_DRIVER}}};"
        f"SERVER={_SERVER};DATABASE={_DB};"
        f"UID={_USER};PWD={_PASSWORD};"
        "TrustServerCertificate=yes;"
    )
else:
    # Windows Authentication (mặc định)
    CONN_STR = (
        f"DRIVER={{{_DRIVER}}};"
        f"SERVER={_SERVER};DATABASE={_DB};"
        "Trusted_Connection=yes;TrustServerCertificate=yes;"
    )
