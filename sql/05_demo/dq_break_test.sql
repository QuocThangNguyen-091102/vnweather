/* =====================================================================
   Thử làm hỏng dữ liệu để thấy bộ kiểm tra chất lượng bắt được lỗi.
   Toàn bộ nằm trong một transaction và được ROLLBACK, không để lại gì.
   Kỳ vọng: dòng "Nhiệt độ ngoài khoảng -10..50 độ C" hiện FAIL, bad_rows = 1.
   ===================================================================== */
USE VNDataPlatform;
GO

BEGIN TRAN;
UPDATE TOP (1) dwh.fact_weather_daily SET temp_max_c = 99;
EXEC dwh.usp_run_dq_checks;
ROLLBACK;
GO

SELECT @@TRANCOUNT AS giao_dich_dang_mo;   -- kỳ vọng: 0
GO
