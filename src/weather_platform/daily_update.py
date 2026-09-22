"""
Chạy hằng ngày (nạp tăng dần):  python -m weather_platform.daily_update

Chỉ tải các ngày sau ngày cuối cùng đã có trong staging, rồi nạp kho dữ liệu, kiểm tra chất lượng và
chạy lại mô hình dự báo. Nếu staging còn rỗng thì tự nạp toàn bộ lịch sử từ 2020.
"""
from __future__ import annotations

import sys

from .pipeline import run_daily


def main() -> int:
    return run_daily("incremental")


if __name__ == "__main__":
    sys.exit(main())
