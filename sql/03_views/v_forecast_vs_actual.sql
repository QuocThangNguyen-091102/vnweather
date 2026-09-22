/* =====================================================================
   View đối chiếu dự báo với số đo thực tế
   Gộp dự báo của Open-Meteo (staging.api_forecast_raw) và của mô hình
   (mart.forecast_daily), nối với nhiệt độ thực tế trong fact.
   Chỉ có dòng khi ngày được dự báo đã có số đo thực tế (dữ liệu quan trắc
   về chậm khoảng 7 ngày).
   Cần chạy sau khi đã tạo các bảng ở 005 và 006.
   ===================================================================== */
USE VNDataPlatform;
GO

CREATE OR ALTER VIEW mart.v_forecast_vs_actual
AS
WITH actual AS (
    SELECT l.location_name, d.full_date, f.temp_max_c
    FROM dwh.fact_weather_daily AS f
    JOIN dwh.dim_date     AS d ON d.date_key     = f.date_key
    JOIN dwh.dim_location AS l ON l.location_key = f.location_key
),
preds AS (
    SELECT N'open-meteo' AS model_name, location_name, base_date, target_date,
           horizon_days, predicted_temp_max_c
    FROM staging.api_forecast_raw
    UNION ALL
    SELECT model_name, location_name, base_date, target_date,
           horizon_days, predicted_temp_max_c
    FROM mart.forecast_daily
)
SELECT p.model_name, p.location_name, p.base_date, p.target_date, p.horizon_days,
       p.predicted_temp_max_c,
       a.temp_max_c AS actual_temp_max_c,
       CAST(p.predicted_temp_max_c - a.temp_max_c AS DECIMAL(6,1)) AS error_c
FROM preds AS p
JOIN actual AS a
  ON a.location_name = p.location_name AND a.full_date = p.target_date;
GO
