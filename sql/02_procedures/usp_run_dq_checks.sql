/* =====================================================================
   usp_run_dq_checks
   Chạy 14 phép kiểm tra chất lượng dữ liệu, ghi kết quả vào dwh.dq_check_log (kèm run_id)
   và trả về kết quả của lần chạy này (PASS khi bad_rows = 0, ngược lại FAIL).

   Nhóm kiểm tra:
     1-2   Staging: trùng khóa, dòng không khớp dimension
     3-5   ĐỐI SOÁT staging và fact theo khóa nghiệp vụ (địa điểm, ngày), gồm cả so sánh giá trị.
           Không chỉ so số dòng: hai bên có thể cùng số dòng nhưng chứa dữ liệu khác nhau.
     6-10  Tính hợp lý của dữ liệu: ngày thiếu, nhiệt độ ngoài khoảng, Tmin > Tmax, mưa âm, NULL
     11-13 Kiểm tra SCD2 của dim_location
     14    Độ tươi (freshness): địa điểm có dữ liệu cũ hơn @max_lag_days

   Tham số (đều có giá trị mặc định, pipeline Python truyền giá trị từ config.py):
     @run_id, @temp_min_c, @temp_max_c, @max_lag_days
   PASS chỉ có nghĩa là không phát hiện lỗi thuộc các loại đã định nghĩa, không đảm bảo dữ liệu đúng 100%.
   ===================================================================== */
USE VNDataPlatform;
GO

CREATE OR ALTER PROCEDURE dwh.usp_run_dq_checks
    @run_id       NVARCHAR(30) = NULL,
    @temp_min_c   DECIMAL(5,1) = -10,
    @temp_max_c   DECIMAL(5,1) = 50,
    @max_lag_days INT          = 10
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @run_at DATETIME2 = SYSDATETIME();
    DECLARE @today  DATE      = CAST(SYSDATETIME() AS DATE);

    INSERT INTO dwh.dq_check_log (run_id, run_at, check_name, bad_rows, status)
    SELECT @run_id, @run_at, c.check_name, c.bad_rows,
           CASE WHEN c.bad_rows = 0 THEN N'PASS' ELSE N'FAIL' END
    FROM (
        -- 1
        SELECT 1 AS seq, N'Staging trùng khóa (địa điểm, ngày)' AS check_name,
               (SELECT COUNT(*) FROM (
                    SELECT 1 AS x FROM staging.weather_daily_raw
                    GROUP BY location_name, obs_date HAVING COUNT(*) > 1) AS t) AS bad_rows
        UNION ALL
        -- 2
        SELECT 2, N'Staging không khớp dimension',
               (SELECT COUNT(*) FROM staging.weather_daily_raw AS s
                WHERE NOT EXISTS (SELECT 1 FROM dwh.dim_location AS l
                                  WHERE l.location_name = s.location_name
                                    AND s.obs_date BETWEEN l.valid_from AND l.valid_to)
                   OR NOT EXISTS (SELECT 1 FROM dwh.dim_date AS d WHERE d.full_date = s.obs_date))
        UNION ALL
        -- 3: đối soát, có ở staging nhưng thiếu ở fact
        SELECT 3, N'Đối soát: có ở staging nhưng thiếu ở fact',
               (SELECT COUNT(*) FROM staging.weather_daily_raw AS s
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM dwh.fact_weather_daily AS f
                    JOIN dwh.dim_date     AS d ON d.date_key     = f.date_key
                    JOIN dwh.dim_location AS l ON l.location_key = f.location_key
                    WHERE l.location_name = s.location_name AND d.full_date = s.obs_date))
        UNION ALL
        -- 4: đối soát, có ở fact nhưng không còn ở staging
        SELECT 4, N'Đối soát: có ở fact nhưng không có ở staging',
               (SELECT COUNT(*)
                FROM dwh.fact_weather_daily AS f
                JOIN dwh.dim_date     AS d ON d.date_key     = f.date_key
                JOIN dwh.dim_location AS l ON l.location_key = f.location_key
                WHERE NOT EXISTS (SELECT 1 FROM staging.weather_daily_raw AS s
                                  WHERE s.location_name = l.location_name AND s.obs_date = d.full_date))
        UNION ALL
        -- 5: đối soát giá trị (so sánh an toàn với NULL bằng EXCEPT)
        SELECT 5, N'Đối soát: giá trị staging và fact khác nhau',
               (SELECT COUNT(*)
                FROM staging.weather_daily_raw AS s
                JOIN dwh.dim_date     AS d ON d.full_date     = s.obs_date
                JOIN dwh.dim_location AS l ON l.location_name = s.location_name
                                          AND s.obs_date BETWEEN l.valid_from AND l.valid_to
                JOIN dwh.fact_weather_daily AS f ON f.date_key = d.date_key AND f.location_key = l.location_key
                WHERE EXISTS (SELECT s.temp_max_c, s.temp_min_c, s.precipitation_mm, s.wind_max_kmh
                              EXCEPT
                              SELECT f.temp_max_c, f.temp_min_c, f.precipitation_mm, f.wind_max_kmh))
        UNION ALL
        -- 6
        SELECT 6, N'Ngày bị thiếu trong chuỗi thời gian',
               (SELECT COALESCE(SUM(DATEDIFF(DAY, g.mn, g.mx) + 1 - g.cnt), 0)
                FROM (SELECT MIN(obs_date) AS mn, MAX(obs_date) AS mx, COUNT(DISTINCT obs_date) AS cnt
                      FROM staging.weather_daily_raw GROUP BY location_name) AS g)
        UNION ALL
        -- 7
        SELECT 7, N'Nhiệt độ ngoài khoảng hợp lệ (tham số)',
               (SELECT COUNT(*) FROM dwh.fact_weather_daily
                WHERE temp_max_c NOT BETWEEN @temp_min_c AND @temp_max_c
                   OR temp_min_c NOT BETWEEN @temp_min_c AND @temp_max_c)
        UNION ALL
        -- 8
        SELECT 8, N'Nhiệt độ thấp nhất lớn hơn cao nhất',
               (SELECT COUNT(*) FROM dwh.fact_weather_daily WHERE temp_min_c > temp_max_c)
        UNION ALL
        -- 9
        SELECT 9, N'Lượng mưa âm',
               (SELECT COUNT(*) FROM dwh.fact_weather_daily WHERE precipitation_mm < 0)
        UNION ALL
        -- 10
        SELECT 10, N'Thiếu giá trị nhiệt độ (NULL)',
               (SELECT COUNT(*) FROM dwh.fact_weather_daily
                WHERE temp_max_c IS NULL OR temp_min_c IS NULL)
        UNION ALL
        -- 11: SCD2, mỗi địa điểm phải có đúng 1 bản ghi hiện hành
        SELECT 11, N'SCD2: địa điểm không có đúng 1 bản ghi hiện hành',
               (SELECT COUNT(*) FROM (
                    SELECT location_name FROM dwh.dim_location
                    GROUP BY location_name
                    HAVING SUM(CASE WHEN is_current = 1 THEN 1 ELSE 0 END) <> 1) AS t)
        UNION ALL
        -- 12: SCD2, các khoảng hiệu lực của cùng một địa điểm không được chồng lấn
        SELECT 12, N'SCD2: khoảng hiệu lực chồng lấn',
               (SELECT COUNT(*) FROM dwh.dim_location AS a
                JOIN dwh.dim_location AS b
                  ON a.location_name = b.location_name AND a.location_key < b.location_key
                 AND a.valid_from <= b.valid_to AND b.valid_from <= a.valid_to)
        UNION ALL
        -- 13
        SELECT 13, N'SCD2: valid_from lớn hơn valid_to',
               (SELECT COUNT(*) FROM dwh.dim_location WHERE valid_from > valid_to)
        UNION ALL
        -- 14: độ tươi, số địa điểm có dữ liệu cũ hơn ngưỡng (nguồn tái phân tích luôn trễ khoảng 7 ngày)
        SELECT 14, N'Độ tươi: địa điểm có dữ liệu quá cũ',
               (SELECT COUNT(*) FROM (
                    SELECT MAX(obs_date) AS last_date FROM staging.weather_daily_raw GROUP BY location_name) AS g
                WHERE DATEDIFF(DAY, g.last_date, @today) > @max_lag_days)
    ) AS c
    ORDER BY c.seq;   -- ORDER BY khi INSERT ... SELECT đảm bảo check_id tăng theo thứ tự kiểm tra

    SELECT check_name, bad_rows, status
    FROM dwh.dq_check_log
    WHERE run_at = @run_at
    ORDER BY check_id;
END;
GO
