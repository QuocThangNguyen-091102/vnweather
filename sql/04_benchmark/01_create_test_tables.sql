/* =====================================================================
   Bảng thử nghiệm hiệu năng (DỮ LIỆU GIẢ LẬP, ngẫu nhiên, không phải thời tiết thật)
     bench.weather_test  : 2.000 trạm x số ngày trong dim_date đến 2026-09-13, khoảng 4,9 triệu dòng
     bench.forecast_test : 200 trạm x cùng các ngày x 7 mức dự báo trước, khoảng 3,4 triệu dòng
   Bảng nằm ở schema riêng "bench" và ban đầu chưa có index (heap).
   Thủ tục bench.usp_reset_indexes xóa mọi index của schema bench để đưa về heap giữa các lần đo.
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

IF OBJECT_ID(N'bench.forecast_test', N'U') IS NULL
BEGIN
    CREATE TABLE bench.forecast_test (
        station_id      INT          NOT NULL,
        target_date_key INT          NOT NULL,
        horizon_days    TINYINT      NOT NULL,
        predicted       DECIMAL(5,2) NOT NULL
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

IF NOT EXISTS (SELECT 1 FROM bench.forecast_test)
BEGIN
    ;WITH n AS (
        SELECT TOP (200) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS station_id
        FROM sys.all_objects AS a CROSS JOIN sys.all_objects AS b
    )
    INSERT INTO bench.forecast_test WITH (TABLOCK)
        (station_id, target_date_key, horizon_days, predicted)
    SELECT n.station_id,
           d.date_key,
           h.horizon_days,
           CAST(20 + (ABS(CHECKSUM(NEWID())) % 200) / 10.0 AS DECIMAL(5,2))
    FROM n
    CROSS JOIN dwh.dim_date AS d
    CROSS JOIN (VALUES (1), (2), (3), (4), (5), (6), (7)) AS h (horizon_days)
    WHERE d.full_date <= '2026-09-13';
END
GO

CREATE OR ALTER PROCEDURE bench.usp_reset_indexes
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @sql NVARCHAR(MAX) = N'';
    SELECT @sql += N'DROP INDEX ' + QUOTENAME(i.name) + N' ON '
                 + QUOTENAME(s.name) + N'.' + QUOTENAME(t.name) + N';' + CHAR(10)
    FROM sys.indexes AS i
    JOIN sys.tables  AS t ON t.object_id = i.object_id
    JOIN sys.schemas AS s ON s.schema_id = t.schema_id
    WHERE s.name = N'bench' AND i.type > 0 AND i.is_primary_key = 0 AND i.is_unique_constraint = 0;
    IF LEN(@sql) > 0 EXEC sys.sp_executesql @sql;
END;
GO

SELECT (SELECT COUNT(*) FROM bench.weather_test)  AS weather_test_rows,    -- kỳ vọng: 4.894.000
       (SELECT COUNT(*) FROM bench.forecast_test) AS forecast_test_rows;   -- kỳ vọng: 3.429.000
GO
