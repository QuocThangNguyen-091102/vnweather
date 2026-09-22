"""
Nạp lịch sử (bootstrap, chạy một lần khi dựng hệ thống):  python -m weather_platform.load_history

Xóa và nạp lại toàn bộ dữ liệu quan trắc từ 01/01/2020 cho mọi địa điểm ở staging, rồi chạy các bước còn lại
của pipeline. Dùng cùng logic nạp với daily_update, chỉ khác chế độ ("history" thay vì "incremental").
"""
from __future__ import annotations

import sys

from .pipeline import run_daily


def main() -> int:
    return run_daily("history")


if __name__ == "__main__":
    sys.exit(main())
