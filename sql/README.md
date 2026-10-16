# Thư mục SQL

Mã SQL của dự án nền tảng dữ liệu thời tiết (SQL Server 2022).
Mỗi file một nhiệm vụ, các file trong `01_setup` và `04_benchmark` đánh số theo thứ tự chạy.
Các file setup và procedure chạy lại nhiều lần vẫn an toàn.

## Thứ tự dựng từ đầu

1. `01_setup/001` đến `006`: tạo database, schema, bảng, nạp bảng ngày.
2. `02_procedures/`: tạo 3 stored procedure (thứ tự bất kỳ).
3. `03_queries/v_forecast_vs_actual.sql`: tạo view đối chiếu dự báo với thực tế.
4. Chạy `python daily_update.py` ở thư mục gốc. Lần đầu nó tự nạp toàn bộ lịch sử từ 2020,
   rồi chạy quy trình kho dữ liệu, kiểm tra chất lượng và mô hình dự báo.

Quy trình nạp kho dữ liệu (do `daily_update.py` gọi) có thể chạy tay, đúng thứ tự:

```sql
EXEC dwh.usp_load_dim_location_scd2;   -- 1. dimension địa điểm (SCD2)
EXEC dwh.usp_load_weather;             -- 2. bảng fact
EXEC dwh.usp_run_dq_checks;            -- 3. kiểm tra chất lượng, kỳ vọng 8 dòng PASS
```

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `01_setup/` | Database, schema, bảng staging, dwh, mart, nạp `dim_date` |
| `02_procedures/` | `usp_load_dim_location_scd2`, `usp_load_weather`, `usp_run_dq_checks` |
| `03_queries/` | Truy vấn báo cáo mẫu và view `mart.v_forecast_vs_actual` |
| `04_benchmark/` | Đo hiệu năng index trên 4,9 triệu dòng giả lập, kèm kết quả trong `notes.md` |
| `05_demo/` | Demo SCD2 và thử làm hỏng dữ liệu. Chỉ chạy khi muốn thử, có sửa dữ liệu |

## Lưu ý

- Bảng `bench.weather_test` là dữ liệu giả lập chỉ dùng cho đo hiệu năng.
- `05_demo/scd2_demo.sql` sửa tọa độ trong `staging.location_ref` và tạo thêm một phiên bản
  địa điểm trong `dwh.dim_location`.
