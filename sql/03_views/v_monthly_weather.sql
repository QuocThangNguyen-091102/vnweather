/* =====================================================================
   View nhiệt độ cao nhất trung bình và tổng lượng mưa theo (địa điểm, năm, tháng)
   Ví dụ:  SELECT * FROM mart.v_monthly_weather WHERE year_num = 2025 ORDER BY location_name, month_num;
   Cột days cho biết số ngày có dữ liệu trong tháng, tháng chưa đủ ngày (ví dụ tháng hiện tại) có days nhỏ hơn.
   ===================================================================== */
USE VNDataPlatform;
GO

CREATE OR ALTER VIEW mart.v_monthly_weather
AS
SELECT l.location_name,
       d.year_num,
       d.month_num,
       CAST(AVG(f.temp_max_c) AS DECIMAL(5,1))       AS avg_temp_max_c,
       CAST(SUM(f.precipitation_mm) AS DECIMAL(9,1)) AS total_precip_mm,
       COUNT(*)                                      AS days
FROM dwh.fact_weather_daily AS f
JOIN dwh.dim_date     AS d ON d.date_key     = f.date_key
JOIN dwh.dim_location AS l ON l.location_key = f.location_key
GROUP BY l.location_name, d.year_num, d.month_num;
GO
