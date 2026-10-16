/* =====================================================================
   Bảng thử nghiệm hiệu năng: 2.000 trạm x số ngày trong dim_date đến
   2026-09-13, khoảng 4,9 triệu dòng DỮ LIỆU GIẢ LẬP (ngẫu nhiên).
   Chỉ dùng để đo index, không phải dữ liệu thời tiết thật.
   Bảng nằm ở schema riêng "bench" và chưa có index nào (heap).
   ===================================================================== */
USE VNDataPlatform;
GO

IF SCHEMA_ID(N'bench') IS NULL EXEC (N'CREATE SCHEMA bench');
GO

IF OBJECT_ID(N'bench.weather_test', N'U') IS NULL
BEGIN
    CREATE TABLE bench.weather_test (
        station_id       INT          NOT NULL,
        date_key         INT          NOT NULL,
        temp_max_c       DECIMAL(5,2) NOT NULL,
        temp_min_c       DECIMAL(5,2) NOT NULL,
        precipitation_mm DECIMAL(7,2) NOT NULL
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM bench.weather_test)
BEGIN
    ;WITH n AS (
        SELECT TOP (2000) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS station_id
        FROM sys.all_objects AS a CROSS JOIN sys.all_objects AS b
    )
    INSERT INTO bench.weather_test WITH (TABLOCK)
        (station_id, date_key, temp_max_c, temp_min_c, precipitation_mm)
    SELECT n.station_id,
           d.date_key,
           CAST(20 + (ABS(CHECKSUM(NEWID())) % 200) / 10.0 AS DECIMAL(5,2)),
           CAST(12 + (ABS(CHECKSUM(NEWID())) % 80)  / 10.0 AS DECIMAL(5,2)),
           CAST((ABS(CHECKSUM(NEWID())) % 3000) / 10.0     AS DECIMAL(7,2))
    FROM n
    CROSS JOIN dwh.dim_date AS d
    WHERE d.full_date <= '2026-09-13';
END
GO

SELECT COUNT(*) AS so_dong FROM bench.weather_test;   -- kỳ vọng: 4.894.000
GO
