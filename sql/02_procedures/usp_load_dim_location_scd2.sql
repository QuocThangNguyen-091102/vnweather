/* =====================================================================
   usp_load_dim_location_scd2
   Nạp dimension địa điểm theo SCD Type 2 từ staging.location_ref:
   - Địa điểm mới          : thêm phiên bản đầu tiên (hiệu lực từ 1900-01-01)
   - Thuộc tính thay đổi   : đóng phiên bản cũ (valid_to = ngày hiệu lực - 1),
                             thêm phiên bản mới (valid_from = ngày hiệu lực)
   - Không thay đổi        : không làm gì
   @effective_date mặc định là hôm nay. Không nên đặt lùi về quá khứ vì các
   dòng fact đã nạp sẽ không tự chuyển sang phiên bản mới.
   ===================================================================== */
USE VNDataPlatform;
GO

CREATE OR ALTER PROCEDURE dwh.usp_load_dim_location_scd2
    @effective_date DATE = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;
    SET @effective_date = COALESCE(@effective_date, CAST(SYSDATETIME() AS DATE));

    BEGIN TRAN;

    -- 1. Đóng phiên bản hiện hành nếu thuộc tính đã đổi
    --    (EXCEPT so sánh an toàn với NULL, khác với dấu <>)
    UPDATE d
    SET d.valid_to   = DATEADD(DAY, -1, @effective_date),
        d.is_current = 0
    FROM dwh.dim_location AS d
    JOIN staging.location_ref AS r ON r.location_name = d.location_name
    WHERE d.is_current = 1
      AND EXISTS (SELECT r.latitude, r.longitude, r.region_name
                  EXCEPT
                  SELECT d.latitude, d.longitude, d.region_name);

    -- 2. Thêm phiên bản mới cho địa điểm mới hoặc vừa bị đóng
    INSERT INTO dwh.dim_location
        (location_name, latitude, longitude, region_name, valid_from, valid_to, is_current)
    SELECT r.location_name, r.latitude, r.longitude, r.region_name,
           CASE WHEN EXISTS (SELECT 1 FROM dwh.dim_location AS x
                             WHERE x.location_name = r.location_name)
                THEN @effective_date ELSE CAST('1900-01-01' AS DATE) END,
           '9999-12-31',
           1
    FROM staging.location_ref AS r
    WHERE NOT EXISTS (SELECT 1 FROM dwh.dim_location AS c
                      WHERE c.location_name = r.location_name AND c.is_current = 1);

    COMMIT;
END;
GO
