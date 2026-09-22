/* =====================================================================
   001 - Tạo database và các schema (tầng dữ liệu)
   staging : dữ liệu API đã chuyển thành bảng có cấu trúc, chưa làm sạch (landing)
   dwh     : kho dữ liệu (star schema) và các bảng nhật ký vận hành
   mart    : dữ liệu tổng hợp, kết quả mô hình và view phục vụ báo cáo
   Chạy lại nhiều lần vẫn an toàn.
   ===================================================================== */
IF DB_ID(N'VNDataPlatform') IS NULL
    CREATE DATABASE VNDataPlatform;
GO

USE VNDataPlatform;
GO

IF SCHEMA_ID(N'staging') IS NULL EXEC (N'CREATE SCHEMA staging');
IF SCHEMA_ID(N'dwh')     IS NULL EXEC (N'CREATE SCHEMA dwh');
IF SCHEMA_ID(N'mart')    IS NULL EXEC (N'CREATE SCHEMA mart');
GO
