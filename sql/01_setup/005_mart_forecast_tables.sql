/* =====================================================================
   005 - Các bảng kết quả dự báo ở tầng mart
   forecast_eval  : sai số (MAE, RMSE) của từng phương pháp theo số ngày dự báo trước
   forecast_daily : dự báo của mô hình cho các ngày sau ngày dữ liệu cuối
   Được ghi bởi forecast.py.
   ===================================================================== */
USE VNDataPlatform;
GO

IF OBJECT_ID(N'mart.forecast_eval', N'U') IS NULL
BEGIN
    CREATE TABLE mart.forecast_eval (
        eval_id      INT IDENTITY PRIMARY KEY,
        run_at       DATETIME2     NOT NULL,
        model_name   NVARCHAR(50)  NOT NULL,
        horizon_days TINYINT       NOT NULL,
        mae_c        DECIMAL(6,3)  NOT NULL,
        rmse_c       DECIMAL(6,3)  NOT NULL,
        n_obs        INT           NOT NULL
    );
END
GO

IF OBJECT_ID(N'mart.forecast_daily', N'U') IS NULL
BEGIN
    CREATE TABLE mart.forecast_daily (
        forecast_id          INT IDENTITY PRIMARY KEY,
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
