/* =====================================================================
   002 - Các bảng ở tầng staging
   weather_daily_raw : dữ liệu thời tiết thô nạp bằng Python (load_history.py)
   location_ref      : khai báo thuộc tính từng địa điểm, là nguồn cho SCD2
   ===================================================================== */
USE VNDataPlatform;
GO

IF OBJECT_ID(N'staging.weather_daily_raw', N'U') IS NULL
BEGIN
    CREATE TABLE staging.weather_daily_raw (
        id               INT IDENTITY PRIMARY KEY,
        location_name    NVARCHAR(100) NOT NULL,
        latitude         DECIMAL(9,6)  NOT NULL,
        longitude        DECIMAL(9,6)  NOT NULL,
        obs_date         DATE          NOT NULL,
        temp_max_c       DECIMAL(5,2)  NULL,
        temp_min_c       DECIMAL(5,2)  NULL,
        precipitation_mm DECIMAL(7,2)  NULL,
        wind_max_kmh     DECIMAL(6,2)  NULL,
        source           NVARCHAR(50)  NOT NULL DEFAULT 'open-meteo-archive',
        loaded_at        DATETIME2     NOT NULL DEFAULT SYSDATETIME()
    );
END
GO

IF OBJECT_ID(N'staging.location_ref', N'U') IS NULL
BEGIN
    CREATE TABLE staging.location_ref (
        location_name NVARCHAR(100) NOT NULL PRIMARY KEY,
        latitude      DECIMAL(9,6)  NOT NULL,
        longitude     DECIMAL(9,6)  NOT NULL,
        region_name   NVARCHAR(20)  NOT NULL
    );
END
GO

-- Dữ liệu ban đầu của 5 địa điểm (chỉ thêm địa điểm chưa có)
INSERT INTO staging.location_ref (location_name, latitude, longitude, region_name)
SELECT v.location_name, v.latitude, v.longitude, v.region_name
FROM (VALUES
        (N'Hà Nội',   21.03, 105.85, N'Miền Bắc'),
        (N'Đà Nẵng',  16.05, 108.20, N'Miền Trung'),
        (N'TP.HCM',   10.82, 106.63, N'Miền Nam'),
        (N'Cần Thơ',  10.03, 105.78, N'Miền Nam'),
        (N'Vũng Tàu', 10.35, 107.08, N'Miền Nam')
     ) AS v (location_name, latitude, longitude, region_name)
WHERE NOT EXISTS (SELECT 1 FROM staging.location_ref AS r
                  WHERE r.location_name = v.location_name);
GO
