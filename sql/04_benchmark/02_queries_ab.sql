/* =====================================================================
   Hai truy vấn dùng để đo hiệu năng.
   Bật thống kê rồi đọc tab Messages: logical reads (hoặc lob logical reads
   khi dùng columnstore), CPU time và elapsed time.
   Nên chạy mỗi truy vấn nhiều lần và lấy lần ổn định (lần đầu sau khi tạo
   index thường chậm hơn).
   ===================================================================== */
USE VNDataPlatform;
GO
SET STATISTICS IO ON;
SET STATISTICS TIME ON;
GO

-- Truy vấn A: tra cứu một trạm trong một năm (hợp với nonclustered index)
SELECT date_key, temp_max_c, precipitation_mm
FROM bench.weather_test
WHERE station_id = 1234
  AND date_key BETWEEN 20250101 AND 20251231;

-- Truy vấn B: tổng hợp toàn bảng theo năm và tháng (hợp với columnstore index)
SELECT d.year_num, d.month_num,
       CAST(AVG(t.temp_max_c) AS DECIMAL(5,1))        AS nhiet_do_cao_tb,
       CAST(SUM(t.precipitation_mm) AS DECIMAL(12,1)) AS tong_mua_mm
FROM bench.weather_test AS t
JOIN dwh.dim_date AS d ON d.date_key = t.date_key
GROUP BY d.year_num, d.month_num
ORDER BY d.year_num, d.month_num;

/* Đo mốc "chưa có columnstore" cho truy vấn B khi index của A đang tồn tại:
   ép quét bảng gốc bằng gợi ý INDEX(0), nếu không SQL Server có thể tự dùng
   index của A (chứa đủ 3 cột B cần).

SELECT d.year_num, d.month_num,
       CAST(AVG(t.temp_max_c) AS DECIMAL(5,1))        AS nhiet_do_cao_tb,
       CAST(SUM(t.precipitation_mm) AS DECIMAL(12,1)) AS tong_mua_mm
FROM bench.weather_test AS t WITH (INDEX(0))
JOIN dwh.dim_date AS d ON d.date_key = t.date_key
GROUP BY d.year_num, d.month_num
ORDER BY d.year_num, d.month_num;
*/
GO
