# Từ điển dữ liệu

Nguồn: **OM** = Open-Meteo, **DWH** = sinh ra trong kho dữ liệu, **PL** = do pipeline ghi.

## staging.weather_daily_raw

| Cột | Ý nghĩa | Kiểu | Nguồn |
|---|---|---|---|
| id | Khóa kỹ thuật | INT IDENTITY | DWH |
| location_name | Tên địa điểm | NVARCHAR(100) | `staging.location_ref` |
| latitude, longitude | Tọa độ dùng để gọi API | DECIMAL(9,6) | `staging.location_ref` |
| obs_date | Ngày quan sát | DATE | OM |
| temp_max_c | Nhiệt độ cao nhất trong ngày (°C) | DECIMAL(5,2) | OM `temperature_2m_max` |
| temp_min_c | Nhiệt độ thấp nhất trong ngày (°C) | DECIMAL(5,2) | OM `temperature_2m_min` |
| precipitation_mm | Tổng lượng mưa trong ngày (mm) | DECIMAL(7,2) | OM `precipitation_sum` |
| wind_max_kmh | Tốc độ gió lớn nhất trong ngày (km/h) | DECIMAL(6,2) | OM `wind_speed_10m_max` |
| source | Nguồn dữ liệu | NVARCHAR(50) | PL |
| loaded_at | Thời điểm nạp (ingested_at) | DATETIME2 | DWH |
| pipeline_run_id | Lần chạy pipeline đã nạp dòng này (NULL với dòng nạp trước khi có cột này) | NVARCHAR(30) | PL |

Ràng buộc: `UNIQUE (location_name, obs_date)`.

## staging.api_forecast_raw

| Cột | Ý nghĩa | Kiểu | Nguồn |
|---|---|---|---|
| location_name | Tên địa điểm | NVARCHAR(100) | PL |
| base_date | Ngày đưa ra dự báo (ngày chạy pipeline) | DATE | PL |
| target_date | Ngày được dự báo | DATE | OM |
| horizon_days | Số ngày dự báo trước (`target_date - base_date`) | TINYINT | PL |
| predicted_temp_max_c | Nhiệt độ cao nhất dự báo (°C) | DECIMAL(5,1) | OM |
| fetched_at | Thời điểm lưu | DATETIME2 | DWH |
| pipeline_run_id | Lần chạy pipeline đã lưu | NVARCHAR(30) | PL |

## staging.location_ref

| Cột | Ý nghĩa | Kiểu | Nguồn |
|---|---|---|---|
| location_name | Tên địa điểm (khóa) | NVARCHAR(100) | khai báo tay |
| latitude, longitude | Tọa độ đại diện của địa điểm | DECIMAL(9,6) | khai báo tay |
| region_name | Vùng (Miền Bắc, Miền Trung, Miền Nam) | NVARCHAR(20) | khai báo tay |

## dwh.dim_date

| Cột | Ý nghĩa | Kiểu | Nguồn |
|---|---|---|---|
| date_key | Khóa ngày dạng yyyymmdd | INT | DWH |
| full_date | Ngày đầy đủ | DATE | DWH |
| year_num, quarter_num, month_num | Năm, quý, tháng | SMALLINT / TINYINT | DWH |
| month_name, day_name | Tên tháng, tên thứ (tiếng Việt) | NVARCHAR(20) | DWH |
| day_of_month, day_of_week | Ngày trong tháng; thứ trong tuần (1 = Thứ Hai) | TINYINT | DWH |
| is_weekend | 1 nếu Thứ Bảy hoặc Chủ Nhật | BIT | DWH |

## dwh.dim_location (SCD Type 2)

| Cột | Ý nghĩa | Kiểu | Nguồn |
|---|---|---|---|
| location_key | Surrogate key của một phiên bản địa điểm | INT IDENTITY | DWH |
| location_name | Tên địa điểm (không duy nhất, mỗi phiên bản một dòng) | NVARCHAR(100) | `staging.location_ref` |
| latitude, longitude, region_name | Thuộc tính được theo dõi lịch sử | DECIMAL / NVARCHAR | `staging.location_ref` |
| valid_from, valid_to | Khoảng hiệu lực của phiên bản. Phiên bản đầu bắt đầu 1900-01-01, phiên bản hiện hành kết thúc 9999-12-31 | DATE | DWH |
| is_current | 1 nếu là phiên bản hiện hành (mỗi địa điểm đúng một) | BIT | DWH |

## dwh.fact_weather_daily

| Cột | Ý nghĩa | Kiểu | Nguồn |
|---|---|---|---|
| date_key | Khóa ngày, nối `dim_date` | INT | DWH |
| location_key | Khóa phiên bản địa điểm, nối `dim_location` | INT | DWH |
| temp_max_c, temp_min_c | Nhiệt độ cao nhất, thấp nhất trong ngày (°C) | DECIMAL(5,2) | OM |
| precipitation_mm | Tổng lượng mưa trong ngày (mm) | DECIMAL(7,2) | OM |
| wind_max_kmh | Tốc độ gió lớn nhất trong ngày (km/h) | DECIMAL(6,2) | OM |
| created_at, updated_at | Thời điểm tạo và sửa dòng | DATETIME2 | DWH |

Khóa chính: `(date_key, location_key)`.

## dwh.dq_check_log

| Cột | Ý nghĩa | Kiểu | Nguồn |
|---|---|---|---|
| check_id | Thứ tự phép kiểm tra trong bảng | INT IDENTITY | DWH |
| run_id | Lần chạy pipeline (NULL nếu chạy tay) | NVARCHAR(30) | PL |
| run_at | Thời điểm chạy bộ kiểm tra | DATETIME2 | DWH |
| check_name | Tên phép kiểm tra | NVARCHAR(100) | DWH |
| bad_rows | Số dòng (hoặc số đối tượng) vi phạm | INT | DWH |
| status | `PASS` nếu `bad_rows = 0`, ngược lại `FAIL` | NVARCHAR(10) | DWH |

## dwh.pipeline_run_log

| Cột | Ý nghĩa | Kiểu | Nguồn |
|---|---|---|---|
| run_id | Mã lần chạy `yyyymmdd_HHMMSS` (khóa) | NVARCHAR(30) | PL |
| mode | `incremental` hoặc `history` | NVARCHAR(20) | PL |
| started_at, finished_at | Thời điểm bắt đầu và kết thúc | DATETIME2 | DWH / PL |
| status | `RUNNING`, `SUCCESS`, `PARTIAL`, `FAILED` | NVARCHAR(20) | PL |
| locations_ok, locations_total | Số địa điểm nạp quan trắc thành công / tổng số | INT | PL |
| rows_loaded | Số dòng quan trắc mới nạp | INT | PL |
| dq_fail_count | Số phép kiểm tra FAIL | INT | PL |
| message | Tóm tắt ngắn (địa điểm lỗi, bước lỗi) | NVARCHAR(1000) | PL |

## mart.forecast_eval

| Cột | Ý nghĩa | Kiểu | Nguồn |
|---|---|---|---|
| run_id, run_at | Lần chạy và thời điểm ghi | NVARCHAR(30), DATETIME2 | PL |
| location_name | Địa điểm; `ALL` = gộp mọi quan sát của mọi địa điểm | NVARCHAR(100) | PL |
| model_name | `persistence`, `clim`, `clim_ar1` | NVARCHAR(50) | PL |
| horizon_days | Số ngày dự báo trước (1 đến 7) | TINYINT | PL |
| mae_c | Sai số tuyệt đối trung bình (°C) | DECIMAL(6,3) | PL |
| rmse_c | Căn bậc hai sai số bình phương trung bình (°C) | DECIMAL(6,3) | PL |
| n_obs | Số quan sát dùng để tính | INT | PL |

## mart.forecast_daily

| Cột | Ý nghĩa | Kiểu | Nguồn |
|---|---|---|---|
| run_id, created_at | Lần chạy và thời điểm ghi | NVARCHAR(30), DATETIME2 | PL |
| location_name | Địa điểm | NVARCHAR(100) | PL |
| base_date | Ngày dữ liệu cuối dùng để dự báo | DATE | PL |
| target_date | Ngày được dự báo | DATE | PL |
| horizon_days | Số ngày dự báo trước (1 đến 14) | TINYINT | PL |
| model_name | Tên mô hình (hiện là `clim_ar1`) | NVARCHAR(50) | PL |
| predicted_temp_max_c | Nhiệt độ cao nhất dự báo (°C) | DECIMAL(5,1) | PL |

## Các view ở mart

| View | Nội dung |
|---|---|
| `v_forecast_vs_actual` | Dự báo (Open-Meteo và mô hình) nối với số đo thực tế; cột `error_c = dự báo - thực tế`. Chỉ có dòng khi ngày dự báo đã có số đo |
| `v_data_quality_metrics` | Một dòng chỉ số: completeness, tỷ lệ thiếu, tỷ lệ trùng, phủ ngày, độ trễ (freshness), phạm vi dữ liệu |
| `v_monthly_weather` | Nhiệt độ cao nhất trung bình và tổng lượng mưa theo (địa điểm, năm, tháng) |
