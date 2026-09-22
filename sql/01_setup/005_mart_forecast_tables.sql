/* =====================================================================
   005 - Các bảng kết quả dự báo ở tầng mart (do Python ghi)
   forecast_eval  : sai số (MAE, RMSE, số quan sát) theo từng địa điểm, phương pháp và số ngày dự báo trước.
                    location_name = 'ALL' là kết quả gộp mọi quan sát của mọi địa điểm.
   forecast_daily : dự báo của mô hình cho các ngày sau ngày dữ liệu cuối.

   Dùng được cho cả database mới lẫn database đang có. Các dòng đánh giá cũ (trước khi có cột location_name)
   đều là kết quả gộp nên được gán 'ALL'.
   ===================================================================== */
USE VNDataPlatform;
GO

IF OBJECT_ID(N'mart.forecast_eval', N'U') IS NULL
BEGIN
    CREATE TABLE mart.forecast_eval (
        eval_id       INT IDENTITY PRIMARY KEY,
        run_id        NVARCHAR(30)  NULL,
        run_at        DATETIME2     NOT NULL,
        location_name NVARCHAR(100) NOT NULL CONSTRAINT DF_forecast_eval_location DEFAULT N'ALL',
        model_name    NVARCHAR(50)  NOT NULL,
        horizon_days  TINYINT       NOT NULL,
        mae_c         DECIMAL(6,3)  NOT NULL,
        rmse_c        DECIMAL(6,3)  NOT NULL,
        n_obs         INT           NOT NULL
    );
END
GO

-- NÂNG CẤP database đang có
IF COL_LENGTH(N'mart.forecast_eval', N'run_id') IS NULL
    ALTER TABLE mart.forecast_eval ADD run_id NVARCHAR(30) NULL;
GO
IF COL_LENGTH(N'mart.forecast_eval', N'location_name') IS NULL
    ALTER TABLE mart.forecast_eval
        ADD location_name NVARCHAR(100) NOT NULL CONSTRAINT DF_forecast_eval_location DEFAULT N'ALL';
GO

IF OBJECT_ID(N'mart.forecast_daily', N'U') IS NULL
BEGIN
    CREATE TABLE mart.forecast_daily (
        forecast_id          INT IDENTITY PRIMARY KEY,
        run_id               NVARCHAR(30)  NULL,
        created_at           DATETIME2     NOT NULL,
        location_name        NVARCHAR(100) NOT NULL,
        base_date            DATE          NOT NULL,   -- ngày dữ liệu cuối dùng để dự báo
        target_date          DATE          NOT NULL,
        horizon_days         TINYINT       NOT NULL,
        model_name           NVARCHAR(50)  NOT NULL,
        predicted_temp_max_c DECIMAL(5,1)  NOT NULL
    );
END
GO

-- NÂNG CẤP database đang có
IF COL_LENGTH(N'mart.forecast_daily', N'run_id') IS NULL
    ALTER TABLE mart.forecast_daily ADD run_id NVARCHAR(30) NULL;
GO
