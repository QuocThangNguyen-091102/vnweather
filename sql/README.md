# Thư mục SQL

Mã SQL của dự án (SQL Server 2022). Mỗi file một nhiệm vụ, đánh số theo thứ tự chạy.
Các file setup, procedure và view dùng `IF ... IS NULL`, `CREATE OR ALTER` nên **chạy lại nhiều lần vẫn an toàn**
và dùng được cho cả database mới lẫn database đang có.

## Dựng database mới

Chạy lần lượt trong SSMS (mỗi file một cửa sổ New Query, bấm Execute):

1. `01_setup/001` đến `006`: database, schema, bảng staging, dwh, mart, bảng nhật ký, nạp bảng ngày.
2. `02_procedures/`: `usp_load_dim_location_scd2`, `usp_load_weather`, `usp_run_dq_checks`.
3. `03_views/`: `v_forecast_vs_actual`, `v_data_quality_metrics`, `v_monthly_weather`.
4. Ở thư mục gốc dự án: `python -m weather_platform.load_history` (nạp lịch sử từ 2020 và chạy toàn bộ pipeline).

## Nâng cấp database đang có (bản trước khi sửa theo góp ý)

Chạy lại **đúng thứ tự** `01_setup/002` đến `006`, rồi `02_procedures/`, rồi `03_views/`. Các khối "NÂNG CẤP" trong
setup sẽ thêm những gì còn thiếu mà không đụng dữ liệu cũ:

| Thay đổi | Ảnh hưởng tới dữ liệu cũ |
|---|---|
| Thêm cột `pipeline_run_id` (staging), `run_id` (dq_check_log, forecast_eval, forecast_daily) | Dòng cũ có giá trị NULL |
| Thêm cột `location_name` vào `mart.forecast_eval` | Dòng cũ là kết quả gộp, được gán `ALL` |
| Thêm ràng buộc `UNIQUE (location_name, obs_date)` cho `staging.weather_daily_raw` | Báo lỗi nếu đang có dòng trùng khóa. Tìm dòng trùng bằng phép kiểm tra "Staging trùng khóa" |
| Tạo bảng `dwh.pipeline_run_log` | Bảng mới |
| `usp_run_dq_checks` từ 8 lên 14 phép kiểm tra | Kết quả cũ trong `dq_check_log` giữ nguyên |
| `dim_date` mở rộng đến 2035-12-31 | Chỉ thêm ngày còn thiếu |

Nên thử trên một database sao lưu trước (đổi tên database ở dòng `USE`).

## Thứ tự nạp kho dữ liệu (do pipeline Python gọi)

```sql
EXEC dwh.usp_load_dim_location_scd2;   -- 1. dimension địa điểm (SCD2), TRƯỚC
EXEC dwh.usp_load_weather;             -- 2. bảng fact (MERGE), SAU
EXEC dwh.usp_run_dq_checks;            -- 3. kiểm tra chất lượng, kỳ vọng 14 dòng PASS
```

## Cấu trúc

| Thư mục | Nội dung |
|---|---|
| `01_setup/` | Database, schema, bảng staging, dwh, mart, nhật ký vận hành, nạp `dim_date` |
| `02_procedures/` | Ba stored procedure nạp và kiểm tra |
| `03_views/` | View đối chiếu dự báo, chỉ số chất lượng, tổng hợp theo tháng |
| `04_benchmark/` | Đo hiệu năng index trên dữ liệu giả lập, kèm `notes.md` ghi rõ ô nào đã đo, ô nào chưa |
| `05_demo/` | Demo SCD2 và thử làm hỏng dữ liệu. Chỉ chạy khi muốn thử, có sửa dữ liệu |

## Lưu ý

- Mã SQL trong thư mục này chưa được kiểm thử tự động (cần SQL Server). Bộ kiểm thử `tests/` chỉ bao phủ phần Python.
  Nên dựng thử trên một database trống trước khi dùng cho dữ liệu chính.
- Bảng `bench.weather_test` và `bench.forecast_test` là dữ liệu giả lập chỉ dùng cho đo hiệu năng.
- `05_demo/scd2_demo.sql` sửa tọa độ trong `staging.location_ref` và tạo thêm một phiên bản địa điểm.
