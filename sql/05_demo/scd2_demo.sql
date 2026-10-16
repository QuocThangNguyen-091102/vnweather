/* =====================================================================
   Demo SCD Type 2: đổi tọa độ Vũng Tàu và xem dimension lưu 2 phiên bản.
   CHÚ Ý: đây là demo, có sửa dữ liệu thật trong staging.location_ref.
   Chạy ở database đang có dữ liệu thật thì sẽ tạo thêm một phiên bản mới.
   ===================================================================== */
USE VNDataPlatform;
GO

-- Trước khi đổi: mỗi địa điểm một phiên bản hiện hành
EXEC dwh.usp_load_dim_location_scd2;
SELECT COUNT(*) AS so_dong FROM dwh.dim_location;

-- Mô phỏng tọa độ được cập nhật chính xác hơn
UPDATE staging.location_ref
SET latitude = 10.346, longitude = 107.084
WHERE location_name = N'Vũng Tàu';

EXEC dwh.usp_load_dim_location_scd2;

-- Kỳ vọng 2 dòng: bản cũ is_current = 0 (valid_to = hôm qua),
-- bản mới is_current = 1 (valid_from = hôm nay, valid_to = 9999-12-31)
SELECT location_key, location_name, latitude, longitude,
       valid_from, valid_to, is_current
FROM dwh.dim_location
WHERE location_name = N'Vũng Tàu'
ORDER BY location_key;
GO
