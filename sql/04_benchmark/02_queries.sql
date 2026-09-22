/* =====================================================================
   Bốn truy vấn đo hiệu năng, mô phỏng khối lượng công việc của dự án:
     A  tra cứu theo địa điểm và khoảng ngày (điểm/khoảng)
     B  tổng hợp theo năm và tháng toàn bảng (aggregation)
     C  Top N ngày nóng nhất
     D  đối chiếu dự báo với thực tế (JOIN forecast và actual)
   Bật thống kê rồi đọc tab Messages: logical reads (hoặc lob logical reads khi dùng columnstore),
   CPU time và elapsed time. Chạy mỗi truy vấn ít nhất 3 lần và lấy lần ổn định (trung vị),
   vì lần đầu sau khi tạo index thường chậm hơn.
   ===================================================================== */
USE VNDataPlatform;
GO
SET STATISTICS IO ON;
SET STATISTICS TIME ON;
GO

-- A: tra cứu một trạm trong một năm
SELECT date_key, temp_max_c, precipitation_mm
FROM bench.weather_test
WHERE station_id = 1234
  AND date_key BETWEEN 20250101 AND 20251231;

-- B: tổng hợp toàn bảng theo năm và tháng
SELECT d.year_num, d.month_num,
       CAST(AVG(t.temp_max_c) AS DECIMAL(5,1))        AS nhiet_do_cao_tb,
       CAST(SUM(t.precipitation_mm) AS DECIMAL(12,1)) AS tong_mua_mm
FROM bench.weather_test AS t
JOIN dwh.dim_date AS d ON d.date_key = t.date_key
GROUP BY d.year_num, d.month_num
ORDER BY d.year_num, d.month_num;

-- C: 10 ngày có nhiệt độ cao nhất
SELECT TOP (10) station_id, date_key, temp_max_c
FROM bench.weather_test
ORDER BY temp_max_c DESC, station_id, date_key;

-- D: sai số tuyệt đối trung bình của dự báo theo số ngày dự báo trước, cho 50 trạm đầu
SELECT f.horizon_days,
       COUNT(*) AS n_obs,
       AVG(ABS(CAST(f.predicted AS FLOAT) - CAST(w.temp_max_c AS FLOAT))) AS mae_c
FROM bench.forecast_test AS f
JOIN bench.weather_test  AS w ON w.station_id = f.station_id AND w.date_key = f.target_date_key
WHERE f.station_id BETWEEN 1 AND 50
GROUP BY f.horizon_days
ORDER BY f.horizon_days;
GO

/* Khi index của truy vấn A đang tồn tại, đo mốc "chưa có columnstore" cho B bằng cách ép quét bảng gốc
   với gợi ý INDEX(0), nếu không SQL Server có thể tự dùng index của A (chứa đủ 3 cột B cần):

SELECT d.year_num, d.month_num,
       CAST(AVG(t.temp_max_c) AS DECIMAL(5,1))        AS nhiet_do_cao_tb,
       CAST(SUM(t.precipitation_mm) AS DECIMAL(12,1)) AS tong_mua_mm
FROM bench.weather_test AS t WITH (INDEX(0))
JOIN dwh.dim_date AS d ON d.date_key = t.date_key
GROUP BY d.year_num, d.month_num
ORDER BY d.year_num, d.month_num;
*/
