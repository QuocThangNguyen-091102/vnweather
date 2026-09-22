# Các quyết định thiết kế và đánh đổi

## Staging có cấu trúc, không lưu JSON gốc

Bảng `staging.weather_daily_raw` chứa dữ liệu đã được parse từ JSON, đổi kiểu và trải phẳng thành cột. Đó là
landing/staging có cấu trúc, không phải "raw" theo nghĩa payload nguyên bản. Hậu tố `_raw` chỉ có nghĩa "chưa biến
đổi nghiệp vụ". Payload JSON không được lưu vì Archive API trả lại được dữ liệu lịch sử khi cần, và dự án không có
yêu cầu kiểm toán payload. Tên bảng được giữ nguyên để không phá database đang chạy.

## Ràng buộc UNIQUE ở staging và phép kiểm tra trùng khóa

`staging.weather_daily_raw` có `UNIQUE (location_name, obs_date)`: trùng khóa bị chặn ngay ở database.
Phép kiểm tra "Staging trùng khóa" trong `usp_run_dq_checks` vẫn được giữ như một lớp phòng thủ, để phát hiện
nếu ràng buộc bị gỡ hoặc có đường nạp khác bỏ qua nó. Pipeline Python cũng loại dòng trùng ngày trước khi nạp.

## Hai lớp kiểm tra chất lượng

| Lớp | Ở đâu | Phát hiện gì |
|---|---|---|
| Trước khi nạp | `data_quality.validate_observations` (Python, có kiểm thử) | Lô dữ liệu vừa tải từ API: trùng ngày, thiếu ngày, Tmin > Tmax, mưa âm, ngoài khoảng, NULL. Chỉ ghi cảnh báo, không chặn nạp |
| Sau khi nạp | `dwh.usp_run_dq_checks` (SQL, 14 phép kiểm tra) | Đối soát staging và fact theo khóa nghiệp vụ, tính đúng đắn của SCD2, độ tươi của dữ liệu |

**Đối soát không chỉ so số dòng.** Nếu chỉ so `COUNT(*)`, staging `{A ngày 1,2,3}` và fact `{A ngày 1,2,4}` vẫn cùng
3 dòng và PASS. Các phép kiểm tra 3 đến 5 đối chiếu theo `(địa điểm, ngày)` và so cả giá trị (dùng `EXCEPT` để so sánh
an toàn với NULL): thiếu ở fact, dư ở fact, và giá trị khác nhau.

**PASS không có nghĩa dữ liệu đúng 100%**: chỉ có nghĩa là không phát hiện lỗi thuộc các loại đã định nghĩa.

## MERGE và đánh đổi

Fact được nạp bằng `MERGE ... WITH (HOLDLOCK)` theo khóa nghiệp vụ `(date_key, location_key)`, so sánh giá trị bằng
`EXCEPT` nên xử lý đúng NULL và chỉ UPDATE khi giá trị thật sự đổi.

| | MERGE (đang dùng) | UPDATE + INSERT tách rời |
|---|---|---|
| Ưu | Một câu lệnh, ý đồ upsert rõ ràng, `OUTPUT $action` cho biết số INSERT/UPDATE | Ít lưu ý về hành vi của SQL Server |
| Nhược | SQL Server có một số lưu ý đã biết về MERGE (đồng thời, một số lỗi hiếm gặp) | Hai câu lệnh, phải tự bảo đảm không đua nhau |

Lựa chọn hiện tại phù hợp quy mô dự án (một lần chạy mỗi ngày, một tiến trình ghi). Nếu chuyển sang môi trường có
nhiều tiến trình ghi đồng thời, nên cân nhắc chuyển sang `UPDATE` + `INSERT` trong một transaction.

## SCD2 cho dimension địa điểm

Tọa độ đại diện của một địa điểm có thể được chỉnh lại (ví dụ Vũng Tàu từ `10.35, 107.08` sang `10.346, 107.084`).
Nếu chỉ ghi đè, dữ liệu lịch sử sẽ như thể luôn dùng tọa độ mới. Với SCD2: phiên bản cũ bị đóng (`valid_to` = ngày
hiệu lực trừ 1), phiên bản mới mở (`valid_from` = ngày hiệu lực); các dòng fact cũ vẫn trỏ về đúng phiên bản.
Ba phép kiểm tra (11 đến 13) bảo đảm: mỗi địa điểm có đúng một bản ghi hiện hành, các khoảng hiệu lực không chồng lấn,
và `valid_from <= valid_to`. Demo đầy đủ ở `sql/05_demo/scd2_demo.sql`.

Lưu ý: không nên đặt ngày hiệu lực lùi về quá khứ (`@effective_date`), vì các dòng fact đã nạp không tự chuyển
sang phiên bản mới và có thể bị đếm trùng.

## Bảng ngày đến 2035

`dim_date` được nạp đến 2035-12-31 và có thể mở rộng bằng cách tăng `@end_date` rồi chạy lại
`01_setup/004_load_dim_date.sql` (chỉ thêm ngày còn thiếu). Nếu dữ liệu vượt `dim_date`, phép kiểm tra
"Staging không khớp dimension" báo FAIL thay vì im lặng bỏ sót dòng.

## Cấu hình kết nối tập trung

Mọi kết nối DB đi qua `weather_platform.db.connect()` và đọc cấu hình từ biến môi trường hoặc `.env`
(`.env.example` là bản mẫu). Không còn chuỗi kết nối lặp lại ở nhiều file. Mặc định dùng Windows Authentication
nên không cần mật khẩu; SQL authentication là tùy chọn.

## Xử lý lỗi từng phần

Ưu tiên: **một địa điểm hoặc một bước phụ lỗi không được làm mất kết quả của phần còn lại**, nhưng lỗi phải hiện rõ
(log `4/5 địa điểm thành công`, trạng thái `PARTIAL`, mã thoát 1). Chỉ lỗi nạp kho (hoặc mất kết nối, hoặc không nạp
được địa điểm nào) mới là `FAILED`.

## Vì sao không thêm mô hình học máy

Ba mô hình (lặp lại ngày cuối, đường khí hậu, khí hậu + AR(1)) đủ để chứng minh quy trình: mốc so sánh, mô hình theo mùa,
hiệu chỉnh phần dư, kiểm thử ngược không rò rỉ, đánh giá có số quan sát. Thêm LSTM hay XGBoost mà không có feature
engineering, kiểm soát rò rỉ, tinh chỉnh và giải thích thì làm dự án rối hơn chứ không mạnh hơn.
