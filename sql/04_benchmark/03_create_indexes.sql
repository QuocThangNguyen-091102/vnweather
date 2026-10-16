/* =====================================================================
   Tạo hai index dùng trong phần đo hiệu năng.
   Chạy 02_queries_ab.sql trước khi tạo để lấy số đo mốc, rồi sau khi tạo
   để lấy số đo mới.
   ===================================================================== */
USE VNDataPlatform;
GO

-- Cho truy vấn A
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = N'IX_weather_test_station_date'
                 AND object_id = OBJECT_ID(N'bench.weather_test'))
    CREATE NONCLUSTERED INDEX IX_weather_test_station_date
        ON bench.weather_test (station_id, date_key)
        INCLUDE (temp_max_c, precipitation_mm);
GO

-- Cho truy vấn B
IF NOT EXISTS (SELECT 1 FROM sys.indexes
               WHERE name = N'NCCI_weather_test'
                 AND object_id = OBJECT_ID(N'bench.weather_test'))
    CREATE NONCLUSTERED COLUMNSTORE INDEX NCCI_weather_test
        ON bench.weather_test (station_id, date_key, temp_max_c, temp_min_c, precipitation_mm);
GO

/* Muốn đo lại từ mốc ban đầu thì xóa index:
DROP INDEX IX_weather_test_station_date ON bench.weather_test;
DROP INDEX NCCI_weather_test            ON bench.weather_test;
*/
