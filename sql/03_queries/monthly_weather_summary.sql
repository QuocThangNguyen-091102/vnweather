/* =====================================================================
   Nhiệt độ cao nhất trung bình và tổng lượng mưa theo tháng, từng địa điểm
   Đổi @year để xem năm khác. Nhiệt độ hiển thị 1 chữ số thập phân.
   ===================================================================== */
USE VNDataPlatform;
GO

DECLARE @year INT = 2025;

SELECT l.location_name,
       d.month_num,
       CAST(AVG(f.temp_max_c) AS DECIMAL(5,1))       AS nhiet_do_cao_tb,
       CAST(SUM(f.precipitation_mm) AS DECIMAL(9,1)) AS tong_mua_mm
FROM dwh.fact_weather_daily AS f
JOIN dwh.dim_date     AS d ON d.date_key     = f.date_key
JOIN dwh.dim_location AS l ON l.location_key = f.location_key
WHERE d.year_num = @year
GROUP BY l.location_name, d.month_num
ORDER BY l.location_name, d.month_num;
GO
