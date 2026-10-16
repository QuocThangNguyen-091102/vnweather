/* =====================================================================
   001 - Tạo database và các schema (tầng dữ liệu)
   staging : dữ liệu thô đúng như nguồn trả về
   dwh     : kho dữ liệu (star schema)
   mart    : dữ liệu tổng hợp phục vụ báo cáo
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
