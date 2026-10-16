/* =====================================================================
   003 - Các bảng ở tầng dwh (star schema)
   Grain của fact: một dòng = một địa điểm trong một ngày.
   dim_location áp dụng SCD Type 2 (nhiều phiên bản cho mỗi địa điểm).
   ===================================================================== */
USE VNDataPlatform;
GO

IF OBJECT_ID(N'dwh.dim_date', N'U') IS NULL
BEGIN
    CREATE TABLE dwh.dim_date (
        date_key     INT          NOT NULL PRIMARY KEY,   -- dạng yyyymmdd
        full_date    DATE         NOT NULL UNIQUE,
        year_num     SMALLINT     NOT NULL,
        quarter_num  TINYINT      NOT NULL,
        month_num    TINYINT      NOT NULL,
        month_name   NVARCHAR(20) NOT NULL,
        day_of_month TINYINT      NOT NULL,
        day_of_week  TINYINT      NOT NULL,               -- 1 = Thứ Hai ... 7 = Chủ Nhật
        day_name     NVARCHAR(20) NOT NULL,
        is_weekend   BIT          NOT NULL
    );
END
GO

IF OBJECT_ID(N'dwh.dim_location', N'U') IS NULL
BEGIN
    CREATE TABLE dwh.dim_location (
        location_key  INT IDENTITY(1,1) PRIMARY KEY,      -- surrogate key
        location_name NVARCHAR(100) NOT NULL,
        latitude      DECIMAL(9,6)  NOT NULL,
        longitude     DECIMAL(9,6)  NOT NULL,
        region_name   NVARCHAR(20)  NULL,
        valid_from    DATE NOT NULL CONSTRAINT DF_dim_location_from    DEFAULT '1900-01-01',
        valid_to      DATE NOT NULL CONSTRAINT DF_dim_location_to      DEFAULT '9999-12-31',
        is_current    BIT  NOT NULL CONSTRAINT DF_dim_location_current DEFAULT 1
    );

    -- Mỗi địa điểm chỉ được có đúng một phiên bản hiện hành
    CREATE UNIQUE NONCLUSTERED INDEX UX_dim_location_current
        ON dwh.dim_location (location_name) WHERE is_current = 1;
END
GO

IF OBJECT_ID(N'dwh.fact_weather_daily', N'U') IS NULL
BEGIN
    CREATE TABLE dwh.fact_weather_daily (
        date_key         INT          NOT NULL,
        location_key     INT          NOT NULL,
        temp_max_c       DECIMAL(5,2) NULL,
        temp_min_c       DECIMAL(5,2) NULL,
        precipitation_mm DECIMAL(7,2) NULL,
        wind_max_kmh     DECIMAL(6,2) NULL,
        created_at       DATETIME2    NOT NULL DEFAULT SYSDATETIME(),
        updated_at       DATETIME2    NULL,
        CONSTRAINT PK_fact_weather_daily PRIMARY KEY (date_key, location_key),
        CONSTRAINT FK_fact_weather_date     FOREIGN KEY (date_key)
            REFERENCES dwh.dim_date (date_key),
        CONSTRAINT FK_fact_weather_location FOREIGN KEY (location_key)
            REFERENCES dwh.dim_location (location_key)
    );
END
GO

-- Nhật ký kết quả các phép kiểm tra chất lượng dữ liệu
IF OBJECT_ID(N'dwh.dq_check_log', N'U') IS NULL
BEGIN
    CREATE TABLE dwh.dq_check_log (
        check_id   INT IDENTITY PRIMARY KEY,
        run_at     DATETIME2     NOT NULL,
        check_name NVARCHAR(100) NOT NULL,
        bad_rows   INT           NOT NULL,
        status     NVARCHAR(10)  NOT NULL
    );
END
GO
