# Phương pháp dự báo và đánh giá

> Đây là **các mô hình thống kê đơn giản dùng làm mốc so sánh**, được **ước lượng** bằng bình phương tối thiểu
> (`numpy.linalg.lstsq`). Không phải mô hình học máy và không thay thế dự báo vật lý của các trung tâm khí tượng.

## Bài toán

Dự báo **nhiệt độ cao nhất hằng ngày** của từng địa điểm cho 1 đến 7 ngày tới (đánh giá) và 14 ngày tới (dự báo lưu vào `mart.forecast_daily`).

## Ba phương pháp

| Tên trong DB | Tên hiển thị | Cách tính | Vai trò |
|---|---|---|---|
| `persistence` | Lặp lại ngày cuối | Mọi ngày sau bằng giá trị của ngày cuối cùng đã biết | Mốc đơn giản nhất: "ngày mai giống hôm nay" |
| `clim` | Đường khí hậu | Hồi quy tuyến tính trên hằng số, xu hướng và 3 cặp sin/cos theo chu kỳ 365,25 ngày | Nhiệt độ điển hình theo mùa, không dùng thông tin của những ngày gần nhất |
| `clim_ar1` | Khí hậu + hiệu chỉnh AR(1) | `clim` cộng phần sai lệch của ngày cuối nhân `phi^h` (h = số ngày dự báo trước) | Giữ lại thông tin "hôm nay nóng hơn bình thường bao nhiêu" và để nó giảm dần |

**Ước lượng `phi`**: là hệ số tự tương quan bậc 1 của phần dư (`resid_t` so với `resid_{t-1}`), cắt về khoảng [0; 0,99].
Nếu không tính được (phần dư là hằng số, chuỗi quá ngắn, kết quả NaN) thì `phi = 0`, nghĩa là không hiệu chỉnh và
`clim_ar1` trùng `clim`. Điều kiện này được kiểm thử trong `tests/test_forecast.py`.

## Đánh giá bằng rolling-origin, bước 7 ngày

Cứ cách 7 ngày lấy một **mốc dự báo** (origin) trong 730 ngày gần nhất. Tại mỗi mốc:

```
Thời gian ─────────────────────────────────────────────────────────────►

Mốc 1:  [==== dữ liệu huấn luyện đến mốc 1 ====]|─ dự báo 1..7 ngày ─┐
                                                 └─ so với số đo thực tế

Mốc 2:  [======== dữ liệu huấn luyện đến mốc 2 (dài hơn 7 ngày) ========]|─ dự báo 1..7 ngày ─┐
                                                                         └─ so với số đo thực tế

Mốc 3:  [=============== ... ===============]|─ ...
```

1. Ước lượng mô hình **chỉ từ dữ liệu đến hết mốc**.
2. Dự báo 1 đến 7 ngày sau mốc.
3. So với số đo thực tế của các ngày đó (bỏ qua ngày không có số đo).
4. Lùi tới mốc kế tiếp (sau 7 ngày) và lặp lại; dữ liệu huấn luyện dài dần ("mở rộng").

Bước 7 ngày được chọn để giảm thời gian chạy; các mốc liền nhau vì vậy không chồng lấn phần dự báo.
Mốc bị bỏ qua nếu ngày mốc không có quan trắc hoặc chuỗi huấn luyện ngắn hơn 365 ngày.

## Kiểm soát rò rỉ dữ liệu (leakage)

- Hàm `backtest` cắt chuỗi bằng `y.loc[:origin]` trước khi ước lượng, nên dữ liệu sau mốc không đi vào mô hình.
- Có một kiểm thử tự động (`test_backtest_uses_no_data_after_the_origin`): sửa toàn bộ dữ liệu SAU (mốc + 7 ngày)
  rồi chạy lại, dự báo tại mốc đầu tiên phải **giống hệt**. Kiểm thử này đã được thử làm hỏng có chủ đích
  (ước lượng trên toàn chuỗi thay vì đến mốc) và bị FAIL đúng như mong đợi.
- Giới hạn còn lại: các chuỗi tái phân tích đã được nội suy tối đa 3 ngày liền để lấp khoảng trống nhỏ trước khi đánh giá.

## Chỉ số

- **MAE**: trung bình của |dự báo - thực tế| (°C).
- **RMSE**: căn bậc hai của trung bình bình phương sai số (°C). Nhạy hơn với sai số lớn.
- **n_obs**: số cặp (dự báo, thực tế) dùng để tính. Số quan sát càng ít, kết quả càng kém ổn định.
- Kết quả lưu theo **từng địa điểm** và một dòng **gộp** (`location_name = 'ALL'`).
  Dòng gộp tính trên toàn bộ quan sát, **không phải trung bình của các MAE** từng địa điểm.

## Giới hạn

- Đánh giá trên 5 địa điểm, 2 năm gần nhất, dữ liệu tái phân tích (không phải số đo của một trạm).
- Chưa có so sánh với mô hình học máy hay dự báo vật lý. Việc đối chiếu với dự báo Open-Meteo đang tích lũy dần
  qua `mart.v_forecast_vs_actual` (cần khoảng một tuần chạy hằng ngày mới có số đo tương ứng).
- Không tối ưu siêu tham số (số cặp sin/cos, độ dài cửa sổ). Đây là chủ ý: mục tiêu là có mốc so sánh rõ ràng,
  không phải tìm mô hình tốt nhất.
