/* =====================================================================
   Thử làm hỏng dữ liệu để thấy bộ kiểm tra chất lượng bắt được lỗi.
   Toàn bộ nằm trong một transaction và được ROLLBACK, không để lại gì.
   Kỳ vọng FAIL ở các phép kiểm tra: "Nhiệt độ ngoài khoảng hợp lệ" và
   "Đối soát: giá trị staging và fact khác nhau" (fact bị sửa nên lệch staging).
   ===================================================================== */
USE VNDataPlatform;
GO

BEGIN TRAN;
UPDATE TOP (1) dwh.fact_weather_daily SET temp_max_c = 99;
EXEC dwh.usp_run_dq_checks @run_id = N'DEMO_BREAK';
ROLLBACK;
GO

SELECT @@TRANCOUNT AS giao_dich_dang_mo;   -- kỳ vọng: 0
GO
