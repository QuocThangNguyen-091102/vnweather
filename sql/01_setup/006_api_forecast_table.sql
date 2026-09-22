/* =====================================================================
   006 - Bảng lưu dự báo thô của Open-Meteo (mỗi ngày lưu một lần)
   Dùng để sau này đối chiếu với số đo thực tế và so với mô hình của dự án.
   Được ghi bởi pipeline Python.
   ===================================================================== */
USE VNDataPlatform;
GO

IF OBJECT_ID(N'staging.api_forecast_raw', N'U') IS NULL
BEGIN
    CREATE TABLE staging.api_forecast_raw (
        api_forecast_id      INT IDENTITY PRIMARY KEY,
        fetched_at           DATETIME2     NOT NULL DEFAULT SYSDATETIME(),
        location_name        NVARCHAR(100) NOT NULL,
        base_date            DATE          NOT NULL,   -- ngày đưa ra dự báo
        target_date          DATE          NOT NULL,   -- ngày được dự báo
        horizon_days         TINYINT       NOT NULL,
        predicted_temp_max_c DECIMAL(5,1)  NULL,
        pipeline_run_id      NVARCHAR(30)  NULL,       -- lần chạy pipeline đã lưu dòng này
        CONSTRAINT UQ_api_forecast UNIQUE (location_name, base_date, target_date)
    );
END
GO

-- NÂNG CẤP database đang có
IF COL_LENGTH(N'staging.api_forecast_raw', N'pipeline_run_id') IS NULL
    ALTER TABLE staging.api_forecast_raw ADD pipeline_run_id NVARCHAR(30) NULL;
GO
