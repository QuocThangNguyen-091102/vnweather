/* =====================================================================
   usp_run_dq_checks
   Chạy 8 phép kiểm tra chất lượng dữ liệu, ghi kết quả vào dwh.dq_check_log
   và trả về kết quả của lần chạy này (PASS khi bad_rows = 0, ngược lại FAIL).

   Phiên bản 2: sửa check #3 — so sánh số ngày distinct theo từng địa điểm
   giữa staging.weather_daily_raw và fact_weather_daily thay vì so sánh
   tổng COUNT(*) (vốn sẽ luôn lệch vì staging còn chứa api_forecast_raw).
   ===================================================================== */
USE VNDataPlatform;
GO

CREATE OR ALTER PROCEDURE dwh.usp_run_dq_checks
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @run_at DATETIME2 = SYSDATETIME();

    INSERT INTO dwh.dq_check_log (run_at, check_name, bad_rows, status)
    SELECT @run_at, check_name, bad_rows,
           CASE WHEN bad_rows = 0 THEN N'PASS' ELSE N'FAIL' END
    FROM (
        -- 1. Trùng khóa trong staging (địa điểm, ngày)
        SELECT N'Staging trùng (địa điểm, ngày)' AS check_name,
               (SELECT COUNT(*) FROM (
                    SELECT 1 AS x FROM staging.weather_daily_raw
                    GROUP BY location_name, obs_date HAVING COUNT(*) > 1) AS t) AS bad_rows

        UNION ALL
        -- 2. Staging không khớp bất kỳ phiên bản nào của dimension địa điểm
        SELECT N'Staging không khớp dimension',
               (SELECT COUNT(*) FROM staging.weather_daily_raw AS s
                WHERE NOT EXISTS (SELECT 1 FROM dwh.dim_location AS l
                                  WHERE l.location_name = s.location_name
                                    AND s.obs_date BETWEEN l.valid_from AND l.valid_to))

        UNION ALL
        -- 3. Số ngày distinct per địa điểm trong staging vs fact không khớp
        --    (kiểm tra từng location riêng để tránh hiệu ứng bù trừ giữa các địa điểm)
        SELECT N'Chênh lệch số ngày staging và fact theo địa điểm',
               (SELECT COALESCE(SUM(ABS(s.day_count - f.day_count)), 0)
                FROM (
                    SELECT location_name, COUNT(DISTINCT obs_date) AS day_count
                    FROM staging.weather_daily_raw
                    GROUP BY location_name
                ) AS s
                JOIN (
                    SELECT l.location_name, COUNT(*) AS day_count
                    FROM dwh.fact_weather_daily AS fw
                    JOIN dwh.dim_location AS l ON l.location_key = fw.location_key
                    GROUP BY l.location_name
                ) AS f ON f.location_name = s.location_name)

        UNION ALL
        -- 4. Ngày bị thiếu trong chuỗi thời gian của mỗi địa điểm
        SELECT N'Ngày bị thiếu trong chuỗi thời gian',
               (SELECT COALESCE(SUM(DATEDIFF(DAY, mn, mx) + 1 - cnt), 0)
                FROM (SELECT MIN(obs_date) AS mn, MAX(obs_date) AS mx,
                             COUNT(DISTINCT obs_date) AS cnt
                      FROM staging.weather_daily_raw GROUP BY location_name) AS g)

        UNION ALL
        -- 5. Nhiệt độ ngoài khoảng hợp lý cho Việt Nam
        SELECT N'Nhiệt độ ngoài khoảng -10..50 độ C',
               (SELECT COUNT(*) FROM dwh.fact_weather_daily
                WHERE temp_max_c NOT BETWEEN -10 AND 50 OR temp_min_c NOT BETWEEN -10 AND 50)

        UNION ALL
        -- 6. Logic nhiệt độ: min > max là vô lý
        SELECT N'Nhiệt độ thấp nhất lớn hơn cao nhất',
               (SELECT COUNT(*) FROM dwh.fact_weather_daily WHERE temp_min_c > temp_max_c)

        UNION ALL
        -- 7. Lượng mưa không thể âm
        SELECT N'Lượng mưa âm',
               (SELECT COUNT(*) FROM dwh.fact_weather_daily WHERE precipitation_mm < 0)

        UNION ALL
        -- 8. NULL nhiệt độ (mô hình dự báo phụ thuộc cột này)
        SELECT N'Thiếu giá trị nhiệt độ (NULL)',
               (SELECT COUNT(*) FROM dwh.fact_weather_daily
                WHERE temp_max_c IS NULL OR temp_min_c IS NULL)
    ) AS c;

    SELECT check_name, bad_rows, status
    FROM dwh.dq_check_log
    WHERE run_at = @run_at
    ORDER BY check_id;
END;
GO
