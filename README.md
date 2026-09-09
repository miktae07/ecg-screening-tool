# Công cụ đọc & sàng lọc nhanh điện tâm đồ (ECG) từ file PDF/XML

Bản demo kỹ thuật cho BV Bạch Mai - Viện Tim mạch. Đọc file điện tâm đồ do máy
Philips PageWriter xuất ra (.xml hoặc .pdf), tự động nhận dạng 12 chuyển đạo,
phát hiện các phức bộ QRS, tính một số thông số cơ bản (tần số tim, độ đều
nhịp, bề rộng QRS...) và gắn cờ sàng lọc bước đầu - **thiên về báo động dư,
thà nhầm còn hơn bỏ sót**, theo đúng yêu cầu của BV.

> ⚠️ Đây là công cụ DEMO / SÀNG LỌC BƯỚC ĐẦU, KHÔNG phải thiết bị chẩn đoán y
> tế và chưa qua kiểm định lâm sàng. Xem đầy đủ hạn chế & phương pháp trong
> file `TAI_LIEU_KY_THUAT.md`.

## Cách chạy nhanh nhất (Windows, không cần biết Python)

Double-click file **`Chay_Demo.bat`**. Lần chạy đầu tiên, file này sẽ tự
động:

1. Kiểm tra máy đã có Python chưa - nếu chưa, tự tải Python 3.11 từ
   python.org và cài cho tài khoản hiện tại (**không cần quyền quản trị**).
2. Tạo một môi trường riêng (`.venv`) cho công cụ, không ảnh hưởng tới phần
   mềm khác trên máy.
3. Cài các thư viện cần thiết (`requirements.txt`).
4. Mở giao diện demo trên trình duyệt tại `http://localhost:8501`.

Từ lần chạy thứ 2 trở đi, các bước 1-3 sẽ được bỏ qua (đã cài sẵn) nên chỉ
mất vài giây là mở được giao diện. Đóng cửa sổ dòng lệnh (màu đen) để tắt
công cụ.

> Lưu ý: bước 1 và 3 (chỉ chạy lần đầu) cần **kết nối internet** để tải
> Python và thư viện. Nếu mạng bệnh viện chặn tải file, hãy nhờ IT cài sẵn
> Python 3.10+ (tick chọn "Add python.exe to PATH" lúc cài) rồi chạy lại
> `Chay_Demo.bat`.

## Cài đặt / chạy thủ công (Windows/macOS/Linux, cho người quen dùng Python)

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

Trình duyệt sẽ tự mở tại `http://localhost:8501`. Kéo-thả một hoặc nhiều file
`.xml`/`.pdf` vào ô tải file. Nếu có cả 2 file của cùng một bản ghi, nên ưu
tiên tải file `.xml` (độ chính xác cao hơn nhiều so với đọc lại từ PDF).

## Chạy kiểm thử hàng loạt (đối chiếu với số liệu của máy)

```bash
python3 validate.py /duong/dan/den/thu_muc_chua_cac_file_mau
```

In ra bảng so sánh tần số tim/độ nhạy sàng lọc của công cụ với thông số máy
đã tính sẵn trên toàn bộ thư mục, và ghi chi tiết ra `validation_report.csv`.

## Cấu trúc mã nguồn

```
Chay_Demo.bat    - chạy nhanh trên Windows (tự cài Python + thư viện nếu cần)
ecg_reader/
  common.py       - cấu trúc dữ liệu chung (ECGRecord, LeadSignal)
  xml_reader.py   - đọc & giải mã file XML Philips (giải nén XLI qua thư viện sierraecg)
  pdf_reader.py   - trích văn bản + số hoá lại dạng sóng vector từ file PDF
  qrs.py          - phát hiện QRS theo cơ chế đồng thuận đa thuật toán
  morphology.py   - đo biên độ, ước lượng lệch đoạn ST
  classify.py     - gắn cờ sàng lọc theo ngưỡng (rule-based)
  analysis.py     - ghép nối toàn bộ pipeline (entry point read_ecg_file + analyze_record)
app.py            - giao diện Streamlit
validate.py       - script kiểm thử hàng loạt / đối chiếu độ chính xác
TAI_LIEU_KY_THUAT.md - tài liệu mô tả kỹ thuật & phương pháp chi tiết
```

## Giới hạn quan trọng cần biết trước khi demo

- Chỉ hỗ trợ định dạng XML "Philips PageWriter / Sierra ECG" - đúng định
  dạng của toàn bộ file mẫu BV đã gửi. Định dạng khác sẽ báo lỗi rõ ràng.
- Với PDF: chỉ số hoá được dạng sóng nếu PDF gốc là **PDF vector** (đường ECG
  vẽ bằng nét vẽ, như các file mẫu đã gửi). PDF dạng ảnh scan sẽ không số hoá
  được dạng sóng (vẫn đọc được phần thông tin văn bản).
- Các cờ sàng lọc dùng ngưỡng cố định, thiên về độ nhạy cao (xem
  `TAI_LIEU_KY_THUAT.md` để biết cách chỉnh ngưỡng nếu cần).
