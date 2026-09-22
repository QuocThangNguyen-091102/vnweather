# Kết quả đo hiệu năng index

Môi trường: SQL Server 2022 Developer, máy cá nhân.
Dữ liệu: bảng `bench.weather_test` khoảng 4,9 triệu dòng **giả lập** (giá trị ngẫu nhiên), không phải dữ liệu
thời tiết thật. Số đo có dao động giữa các lần chạy. Bốn truy vấn A đến D nằm trong `02_queries.sql`,
bốn cấu trúc lưu trữ được dựng bằng các file `03` đến `06`.

## Đã đo

Truy vấn A và B trên ba cấu trúc heap, nonclustered và columnstore (số đo ban đầu của dự án):

| Truy vấn | Cấu trúc | Số lần đọc | CPU | Thời gian thực |
|---|---|---|---|---|
| A (tra cứu 1 trạm, 1 năm) | Heap | 19.352 | 671 ms | 105 ms |
| A | Nonclustered index (station_id, date_key) | 5 | 0 ms | 0 ms |
| B (tổng hợp toàn bảng) | Heap | 19.352 | 1.328 đến 2.060 ms | 178 đến 293 ms |
| B | Nonclustered columnstore | khoảng 4.000 (lob) | 203 đến 235 ms | 191 đến 221 ms |

## Chưa đo

Các ô còn trống dưới đây cần chạy theo quy trình ở cuối file rồi điền số thật vào.
Không điền số ước lượng.

| Truy vấn | Heap | Clustered | Nonclustered | Columnstore |
|---|---|---|---|---|
| A | đã đo | chưa đo | đã đo | chưa đo |
| B | đã đo | chưa đo | chưa đo | đã đo |
| C (Top 10 ngày nóng nhất) | chưa đo | chưa đo | chưa đo | chưa đo |
| D (đối chiếu dự báo và thực tế) | chưa đo | chưa đo | chưa đo | chưa đo |

## Cách trình bày kết luận

- Logical reads giảm mạnh từ 19.352 xuống 5 ở truy vấn A trên khối lượng công việc thử nghiệm.
  Thời gian thực (elapsed) của truy vấn A đã về dưới 1 ms, nhưng thời gian thực cần được đánh giá trên khối lượng
  công việc thật và qua nhiều lần chạy, không nên quy ra "nhanh gấp X lần".
- Với truy vấn B, columnstore giảm số lần đọc khoảng 4,8 lần và CPU khoảng 6 đến 9 lần, nhưng thời gian thực gần như
  không đổi vì bản không index đã chạy song song nhiều luồng.
- Dữ liệu giả lập ngẫu nhiên nén kém, nên lợi ích của columnstore trên dữ liệu thật có thể khác.

## Quy trình đo lại

1. Chạy `01_create_test_tables.sql` (một lần).
2. Với mỗi giai đoạn `03` đến `06`: chạy file dựng cấu trúc, chạy `02_queries.sql` ít nhất 3 lần,
   ghi lại logical reads, CPU và elapsed của lần ổn định (trung vị), rồi điền vào bảng.
