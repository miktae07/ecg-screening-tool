# Tài liệu kỹ thuật: Công cụ đọc & sàng lọc nhanh điện tâm đồ (PDF/XML)

**Phiên bản:** 0.1 (demo kỹ thuật) · **Ngày:** 08/09/2026
**Dữ liệu thử nghiệm:** 100 cặp file (.xml + .pdf) điện tâm đồ do BV Bạch Mai
- Viện Tim mạch cung cấp, xuất từ máy Philips PageWriter.

---

## 1. Mục tiêu và phạm vi

Công cụ đọc file điện tâm đồ (ECG) ở định dạng PDF hoặc XML, tự động:

1. Nhận dạng và tách riêng 12 chuyển đạo chuẩn (I, II, III, aVR, aVL, aVF,
   V1-V6).
2. Phát hiện các phức bộ QRS (nhịp tim) trên tín hiệu.
3. Tính một số thông số cơ bản: tần số tim, độ đều nhịp, bề rộng QRS ước
   tính, biên độ, độ lệch đoạn ST thô.
4. Gắn cờ sàng lọc bước đầu (bất thường có thể có) dựa trên các ngưỡng quy
   tắc, **thiên về độ nhạy cao** theo đúng yêu cầu của BV: *"thà nhầm còn hơn
   bỏ sót"*.
5. Hiển thị toàn bộ kết quả trên giao diện web đơn giản (Streamlit) để bác sĩ
   xem nhanh và đối chiếu với dạng sóng gốc.

**Đây KHÔNG phải là:** một thiết bị chẩn đoán y tế, một hệ thống đã được kiểm
định lâm sàng, hay một công cụ thay thế việc bác sĩ đọc điện tim. Đây là một
**bản demo kỹ thuật** nhằm minh hoạ khả năng tự động hoá bước sàng lọc/trích
xuất dữ liệu ban đầu, làm cơ sở để BV đánh giá và quyết định hướng phát triển
tiếp theo (nếu có).

## 2. Kiến trúc tổng quan

```
File .xml hoặc .pdf
        │
        ▼
┌───────────────────┐      ┌───────────────────┐
│   xml_reader.py    │      │   pdf_reader.py    │
│ (giải mã XLI, đọc  │      │ (trích văn bản +    │
│  metadata & thông  │      │  số hoá vector nét  │
│  số máy đã tính)   │      │  vẽ ECG)            │
└─────────┬──────────┘      └─────────┬──────────┘
          │                            │
          └───────────► ECGRecord ◄────┘
                    (cấu trúc dữ liệu chuẩn hoá
                     chung, common.py)
                            │
                            ▼
                    ┌───────────────┐
                    │    qrs.py     │  → phát hiện QRS (đồng thuận đa thuật toán)
                    └───────┬───────┘
                            ▼
                    ┌───────────────┐
                    │ morphology.py │  → biên độ, lệch ST
                    └───────┬───────┘
                            ▼
                    ┌───────────────┐
                    │  classify.py  │  → gắn cờ sàng lọc theo ngưỡng
                    └───────┬───────┘
                            ▼
                    AnalysisReport (analysis.py)
                            │
                ┌───────────┴────────────┐
                ▼                         ▼
           app.py (giao diện)      validate.py (kiểm thử hàng loạt)
```

Toàn bộ logic phân tích chỉ nằm ở **một nơi duy nhất** (`ecg_reader/`), được
cả giao diện và script kiểm thử dùng chung, tránh tình trạng "hai nơi tính
khác nhau".

## 3. Đọc dữ liệu đầu vào

### 3.1. File XML (nguồn chính, độ tin cậy cao)

Toàn bộ 100 file mẫu XML đều thuộc định dạng **Philips PageWriter XML**
(`documenttype = PhilipsECG`, còn gọi là "Sierra ECG XML"). Đặc điểm:

- File được mã hoá **UTF-16**.
- Tín hiệu 12 chuyển đạo (thẻ `<parsedwaveforms>`) được nén bằng thuật toán
  độc quyền của Philips gọi là **XLI**: kết hợp nén **LZW đọc 10-bit một
  lần** rồi **giải mã sai phân bậc hai** (second-order delta decoding), sau
  khi đan xen (interleave) 2 nửa byte cao/thấp của mỗi mẫu 16-bit.
- Thay vì tự viết lại bộ giải nén XLI (rủi ro sai sót cao, khó kiểm chứng
  độc lập), công cụ dùng thư viện mã nguồn mở **`sierraecg`** (PyPI), vốn là
  bản port lại từ dự án **`sierra-ecg-tools`** - dự án do cộng đồng
  reverse-engineer thuật toán XLI từ năm 2011 (tác giả: sixlettervariables,
  xem mục Tài liệu tham khảo) và đã được nhiều nơi dùng để đọc file Sierra
  ECG / MUSE XML trong hơn 10 năm qua.
- Sau khi giải nén ra số nguyên (ADC counts), giá trị được nhân với hệ số
  `<resolution>` (đọc trực tiếp từ chính file XML, thường là 5 µV/đơn vị) để
  ra điện thế thực tế theo mV.
- Đồng thời trích xuất: thông tin hành chính (bệnh viện, khoa, giới tính,
  tuổi, thời gian ghi - **đã được BV ẩn danh trong toàn bộ dữ liệu mẫu**), và
  các **thông số máy đã tự tính sẵn** (nhịp tim, PR, QRS, QT, QTc, trục điện
  tim, mức độ ABNORMAL/BORDERLINE/NORMAL) để đối chiếu.

Nếu gặp file XML không phải định dạng Philips, công cụ báo lỗi rõ ràng thay
vì cố đoán cấu trúc (tránh đọc sai âm thầm).

### 3.2. File PDF (nguồn dự phòng, độ tin cậy thấp hơn)

Dùng khi BV chỉ có file PDF, không có XML đi kèm. Gồm 2 phần:

**a) Trích văn bản (rất tin cậy).** File PDF do Philips PageWriter xuất ra
chứa lớp văn bản thật (không phải ảnh chụp), nên dùng thư viện `PyMuPDF` đọc
trực tiếp: tên bệnh viện/khoa, giới tính, thời gian ghi, và toàn bộ thông số
máy đã in trên tờ báo cáo (HR, PR, QRS, QT, QTc, trục điện tim, kết luận
ABNORMAL/NORMAL...).

**b) Số hoá lại dạng sóng từ nét vẽ vector (thử nghiệm - "best effort").**
Phát hiện quan trọng trong quá trình xây dựng công cụ: các file PDF mẫu của
BV là **PDF vector**, nghĩa là đường cong điện tim được vẽ bằng hàng nghìn
đoạn thẳng nối tiếp nhau (`fitz`/PyMuPDF đọc được toạ độ (x, y) của từng
điểm), **không phải ảnh bitmap**. Nhờ vậy có thể đọc ngược lại toạ độ và quy
đổi ra (thời gian, điện thế) bằng hệ số hiệu chuẩn in ngay trên trang báo cáo
("Speed: 25 mm/sec", "Chest/Limb: 10 mm/mV"):

- `giây/điểm = (25.4/72 mm/điểm) / (tốc độ giấy, mm/giây)`
- `mV/điểm = (25.4/72 mm/điểm) / (độ khuếch đại, mm/mV)`
- Đường nền (0 mV) của mỗi chuyển đạo được ước lượng bằng **trung vị** toạ độ
  y của chính đường vẽ đó (giả định phần lớn thời gian tín hiệu nằm quanh
  đường đẳng điện).
- Việc ghép tên chuyển đạo (I, II, III, ...) vào đúng ô trong lưới in được
  thực hiện bằng cách đối chiếu vị trí (x, y) của chữ nhãn in trên trang với
  vị trí của từng đường vẽ.

**Hạn chế bắt buộc phải lưu ý** (đã hiển thị rõ trong giao diện):

- Layout in ấn chuẩn 3 hàng x 4 cột thể hiện **các cửa sổ thời gian khác
  nhau** cho mỗi hàng (hàng 1: giây 0-2.5, hàng 2: giây 2.5-5, hàng 3: giây
  5-7.5 của bản ghi). 4 chuyển đạo trong cùng một hàng thì đồng bộ với nhau,
  nhưng **không** đồng bộ với chuyển đạo ở hàng khác → các chuyển đạo này chỉ
  dùng để xem hình thái riêng lẻ, không dùng để phân tích đa chuyển đạo đồng
  thời (ví dụ trục điện tim).
- Dải nhịp (rhythm strip) ở cuối trang dài hơn (10 giây trong dữ liệu mẫu)
  và **chỉ có 1 chuyển đạo** (thường là II) - đây là nguồn dữ liệu chính để
  tính tần số tim/độ đều nhịp/QRS khi chỉ có PDF.
- Độ chính xác **biên độ** thấp hơn XML. Kiểm thử trên file mẫu cho thấy
  tương quan dạng sóng giữa bản số hoá PDF và tín hiệu số gốc (XML) đạt hệ số
  tương quan **r ≈ 0.92**, nhưng biên độ đỉnh có thể lệch 20-30% - đủ để phát
  hiện nhịp/thời gian chính xác, nhưng **không đủ tin cậy để dùng cho các cờ
  phụ thuộc biên độ như lệch đoạn ST** (nên công cụ **chủ động tắt** cờ
  `ST_CHANGE` khi dữ liệu đến từ PDF, chỉ bật khi có XML).
- Nếu PDF là ảnh scan (không có nét vẽ vector), công cụ chỉ đọc được phần văn
  bản, không số hoá được dạng sóng, và sẽ báo rõ trong giao diện.

## 4. Phát hiện phức bộ QRS

### 4.1. Vì sao không dùng một thuật toán duy nhất

Thử nghiệm ban đầu dùng cách đơn giản nhất để tối đa hoá độ nhạy - **hợp
(union) mù quáng** kết quả của nhiều thuật toán phát hiện QRS nổi tiếng - cho
kết quả **phản tác dụng nghiêm trọng**: trên chính 100 file mẫu, tần số tim
tính ra bị thổi phồng gấp 1.5-2 lần thực tế ở rất nhiều file (sai số tuyệt
đối trung bình 32.4 bpm, hệ số tương quan chỉ r = 0.14 so với số liệu máy).
Nguyên nhân: hai thuật toán Hamilton (2002) và Elgendi (2010), tuy được công
bố và dùng rộng rãi, lại kém ổn định hơn hẳn trên các bản ghi nhiều nhiễu/bất
thường trong tập dữ liệu tim mạch này, tạo ra nhiều đỉnh giả không khớp nhịp
thật.

### 4.2. Giải pháp: đồng thuận có trọng số (ensemble voting)

1. Chạy đồng thời 4 thuật toán đã công bố: **NeuroKit2 mặc định** (biến thể
   của Nabian et al. 2018), **Pan & Tompkins (1985)**, **Hamilton (2002)**,
   **Elgendi et al. (2010)** - qua thư viện `neurokit2`.
2. Các đỉnh do các thuật toán khác nhau tìm ra nhưng rơi vào cùng cửa sổ
   **±120 ms** được gộp vào một "cụm" (coi là cùng một nhịp thật).
3. Một cụm được **≥ 2/4 thuật toán độc lập đồng ý** → coi là **nhịp đã xác
   nhận** (confirmed) - dùng để tính tần số tim, độ đều nhịp, bề rộng QRS.
4. Một cụm chỉ có **1/4 thuật toán** tìm thấy → coi là **nhịp khả nghi**
   (candidate): **không** đưa vào các con số thống kê định lượng (tránh làm
   sai lệch tần số tim), nhưng **vẫn hiển thị riêng** trên biểu đồ (chấm cam,
   ký hiệu ◇) để bác sĩ tự xem lại.
   → Đây chính là chỗ áp dụng tinh thần "thà nhầm còn hơn bỏ sót" một cách có
   kiểm soát: thay vì im lặng bỏ qua một tín hiệu không chắc chắn, công cụ
   vẫn báo cho người xem biết "có khả năng có một nhịp ở đây, các thuật toán
   chưa thống nhất" - nhưng không để nó làm sai các con số định lượng chính.
5. Ngưỡng sinh lý cứng duy nhất được áp dụng: khoảng cách tối thiểu giữa 2
   nhịp đã xác nhận là **200 ms** (ứng với < 300 nhịp/phút) - không lọc theo
   hình dạng hay biên độ, để tránh loại nhầm ngoại tâm thu hoặc nhịp bất
   thường thật.

Sau khi áp dụng cơ chế đồng thuận, kết quả kiểm thử lại trên chính 100 file
(mục 7) cải thiện rõ rệt: sai số tuyệt đối trung bình còn **3.9 bpm**, hệ số
tương quan **r = 0.91** so với số liệu máy.

### 4.3. Bề rộng QRS

Với mỗi nhịp đã xác nhận, công cụ dùng bước phân định (delineation) của
`neurokit2` (phương pháp `"peak"`, xác định điểm Q và điểm S quanh mỗi đỉnh
R) để ước lượng bề rộng QRS = (thời điểm S - thời điểm Q). Các giá trị nằm
ngoài khoảng sinh lý hợp lý (40-200 ms) bị loại khỏi thống kê (nhưng không
loại nhịp đó khỏi tổng số nhịp đã đếm). Giá trị báo cáo là **trung vị** qua
toàn bộ nhịp phân định được, để giảm ảnh hưởng của nhiễu ở một vài nhịp lẻ.
Đây là một ước lượng **thô** - kém chính xác hơn thuật toán trung bình nhịp
đại diện (representative-beat averaging) mà các máy ECG thương mại dùng,
nên số liệu máy vẫn được hiển thị song song để đối chiếu.

## 5. Các phép đo hình thái khác

- **Biên độ đỉnh-đỉnh** mỗi chuyển đạo: `max - min` trên toàn bộ tín hiệu.
- **Độ lệch đoạn ST**: với mỗi nhịp đã xác nhận, đo chênh lệch biên độ giữa
  một điểm ước lượng nằm trong đoạn ST (140 ms sau đỉnh R - xấp xỉ J+60ms với
  QRS trung bình) và một điểm nền trong đoạn PR (80 ms trước đỉnh R), rồi lấy
  **trung vị** qua các nhịp. Đây là quy ước đơn giản hoá (không cá thể hoá
  theo bề rộng QRS thật của từng nhịp/từng bệnh nhân), chỉ dùng cho mục đích
  sàng lọc thô, độ nhạy cao nhưng độ đặc hiệu thấp - luôn cần bác sĩ xem lại
  dạng sóng gốc.

## 6. Bộ quy tắc gắn cờ sàng lọc

Toàn bộ ngưỡng đều được chọn **lỏng hơn ngưỡng lâm sàng kinh điển** theo đúng
tinh thần "thà nhầm còn hơn bỏ sót". Đây là các quy tắc thô, **không phải chẩn
đoán**, và tất cả có thể chỉnh sửa dễ dàng trong `ecg_reader/classify.py`.

| Cờ | Điều kiện kích hoạt | Ngưỡng kinh điển (tham khảo) | Mức |
|---|---|---|---|
| `HR_LOW` | Tần số tim < 60 ck/ph | 60 | Cảnh báo |
| `HR_HIGH` | Tần số tim > 100 ck/ph | 100 | Cảnh báo |
| `RHYTHM_IRREGULAR` | Hệ số biến thiên RR ≥ 0.12 | thường dùng 0.15-0.20 | Cảnh báo |
| `QRS_WIDE` | Bề rộng QRS ≥ 110 ms | 120 ms | Cảnh báo |
| `QTC_LONG` | QTc ≥ 440 ms (nam) / 450 ms (nữ) | 450/460 ms | **Nguy cơ cao** |
| `AXIS_LEFT` / `AXIS_RIGHT` | Trục QRS < -30° hoặc > 90° | như nhau | Cảnh báo |
| `LOW_VOLTAGE` | Biên độ đỉnh-đỉnh chuyển đạo chi cao nhất < 0.5 mV | như nhau | Cảnh báo |
| `ST_CHANGE` | Lệch ST tại điểm ước tính ≥ 0.10 mV (chỉ áp dụng khi có XML) | STEMI kinh điển dùng 0.1-0.25mV tuỳ chuyển đạo, đặc hiệu hơn nhiều | **Nguy cơ cao** |

QTc và trục điện tim hiện được lấy từ thông số **máy đã tính sẵn** (đọc từ
chính file gốc) chứ công cụ chưa tự tính độc lập - vì việc tự tính chính xác
đòi hỏi thuật toán phân định P/QRS/T phức tạp hơn nhiều so với phạm vi bản
demo này (xem mục 9 - Hướng phát triển).

## 7. Kết quả kiểm thử trên 100 file mẫu

Chạy bằng `validate.py` trên toàn bộ 100 cặp file (.xml + .pdf) do BV cung
cấp, đối chiếu với thông số **máy đã tính sẵn** (không phải "chẩn đoán chuẩn
vàng" độc lập, mà là số liệu tham chiếu có sẵn duy nhất trong tập mẫu):

- **Độ ổn định:** 100/100 file XML và 100/100 file PDF đọc thành công, không
  lỗi. Thời gian xử lý trung bình: **≈ 0.4 giây/file** (XML, máy chủ demo).
- **Độ chính xác tần số tim (so với máy):**
  - Nguồn XML: sai số tuyệt đối trung bình (MAE) **3.9 bpm**, tương quan
    **r = 0.91**.
  - Nguồn PDF (số hoá lại): MAE **3.6 bpm**, tương quan **r = 0.89** - gần
    tương đương XML, cho thấy việc số hoá vector hoạt động tốt cho mục đích
    tính tần số tim/nhịp, dù độ chính xác biên độ kém hơn (mục 3.2).
- **Độ nhạy sàng lọc thô** (so với kết luận severity có sẵn trên máy):
  100% số ca máy kết luận "ABNORMAL ECG" (72/72) và "BORDERLINE ECG" (12/12)
  đều được công cụ gắn ít nhất 1 cờ cảnh báo.
- **Tỷ lệ dương tính giả kỳ vọng:** 100% số ca máy kết luận "NORMAL"/
  "OTHERWISE NORMAL ECG" (16/16) **vẫn** được công cụ gắn ít nhất 1 cờ.
  **Đây là hệ quả trực tiếp và có chủ đích của việc chọn ngưỡng lỏng để tối
  đa hoá độ nhạy** - đúng yêu cầu ban đầu, nhưng có nghĩa là ở cấu hình ngưỡng
  hiện tại, **công cụ gần như luôn báo có ít nhất một điểm cần xem lại**. Nếu
  BV muốn công cụ "im lặng" nhiều hơn với các ca thực sự bình thường, cần
  siết lại một số ngưỡng ở mục 6 (đánh đổi lại một phần độ nhạy) - nên thực
  hiện dựa trên phản hồi thực tế của bác sĩ khi dùng thử, không nên đoán
  trước.

Toàn bộ số liệu chi tiết theo từng file được ghi trong `validation_report.csv`
(sinh ra khi chạy `validate.py`) để BV có thể tự kiểm tra lại độc lập.

## 8. Giao diện người dùng

Xây dựng bằng **Streamlit** (chạy local, không cần deploy server phức tạp,
phù hợp cho demo nhanh) với các phần chính cho mỗi file tải lên:

1. Banner cảnh báo cố định ở đầu trang, nhắc rõ đây là công cụ sàng lọc, cần
   bác sĩ xem lại.
2. Thông tin hành chính (bệnh viện, khoa, giới tính, tuổi, thời gian ghi) +
   nhãn rõ ràng về **độ tin cậy nguồn dữ liệu** (XML/số gốc hay PDF/số hoá
   lại) cùng mọi cảnh báo phát sinh trong quá trình đọc file.
3. Banner tổng hợp mức độ (xanh/vàng/đỏ) kèm đối chiếu với kết luận sẵn có
   của máy (nếu có).
4. Bảng thông số: cột "công cụ tự tính" cạnh cột "máy ghi ECG báo cáo" để dễ
   đối chiếu.
5. Danh sách cờ cảnh báo, mỗi cờ kèm giải thích ngưỡng và diễn giải lâm sàng
   ngắn gọn.
6. Biểu đồ dạng sóng tương tác (Plotly) toàn bộ 12 chuyển đạo (hoặc dải nhịp
   + các đoạn ngắn nếu là PDF), đánh dấu **chấm đỏ** = nhịp đã xác nhận,
   **chấm cam ◇** = nhịp khả nghi cần xem thêm.

Có thể tải nhiều file cùng lúc, mỗi file hiển thị trong một tab riêng.

## 8b. Đóng gói & triển khai

Công cụ được viết bằng Python thuần (không dùng thành phần đóng gói riêng
theo hệ điều hành), nên **không có sẵn file cài đặt .exe/.msi độc lập**.
Thay vào đó, đi kèm file **`Chay_Demo.bat`** (Windows) tự động hoá toàn bộ
việc cài đặt ở lần chạy đầu: tự tải & cài Python 3.11 nếu máy chưa có (không
cần quyền quản trị), tạo môi trường ảo riêng, cài thư viện, rồi mở giao diện
- các lần chạy sau chỉ mất vài giây. Lý do không đóng gói thành một file
`.exe` độc lập kiểu PyInstaller: bộ thư viện xử lý tín hiệu/vẽ đồ thị dùng
trong công cụ (numpy, scipy, PyMuPDF, neurokit2, plotly, Streamlit) rất nặng
và có nhiều import động - đóng gói dạng này thường cho file nặng (200-400MB),
build lâu, dễ lỗi thiếu module ẩn, khó bảo trì hơn nhiều so với cách chạy qua
môi trường ảo Python tiêu chuẩn. Nếu sau này BV muốn có file .exe thực sự
(ví dụ để cài hàng loạt qua hệ thống quản lý phần mềm nội bộ), có thể đầu tư
thêm thời gian build bằng PyInstaller/cx_Freeze **trực tiếp trên máy Windows**
(không build chéo được từ máy chủ Linux).

## 9. Giới hạn hiện tại và hướng phát triển tiếp theo

- **Chỉ hỗ trợ 1 định dạng XML** (Philips PageWriter/Sierra ECG) và PDF dạng
  vector cùng nhà sản xuất. Muốn dùng với máy khác (GE MUSE, Mortara, SCP-ECG
  chuẩn châu Âu...) cần viết thêm reader tương ứng - kiến trúc hiện tại
  (`ECGRecord` chuẩn hoá chung) đã được thiết kế để dễ bổ sung mà không phải
  sửa phần phân tích/giao diện.
- **QTc và trục điện tim** hiện lấy từ số liệu máy sẵn có, chưa tự tính độc
  lập khi chỉ có tín hiệu thô (ví dụ khi hoàn toàn không có số liệu máy đi
  kèm) - cần thêm bước phân định P/QRS/T đầy đủ (ví dụ nâng cấp
  `neurokit2.ecg_delineate` sang toàn bộ các sóng, không chỉ Q/S) nếu muốn
  độc lập hoàn toàn với số liệu máy.
- **Phân loại nhịp** hiện chỉ ở mức rất cơ bản (nhanh/chậm/không đều theo
  thống kê RR) - CHƯA phân biệt được các loại loạn nhịp cụ thể (rung nhĩ,
  cuồng nhĩ, nhịp nhanh thất...). Đây là hướng mở rộng tự nhiên tiếp theo nếu
  BV muốn đầu tư thêm (cần dữ liệu có nhãn chẩn đoán xác nhận bởi bác sĩ để
  huấn luyện/kiểm định mô hình phân loại thật sự, khác với bộ quy tắc ngưỡng
  đơn giản hiện tại).
- **Độ đặc hiệu thấp theo thiết kế** (mục 7) - cần cân nhắc lại ngưỡng dựa
  trên phản hồi thực tế nếu mục tiêu chuyển từ "demo minh hoạ khả năng" sang
  "công cụ dùng hàng ngày", để tránh hiện tượng bác sĩ mất tin tưởng vì cảnh
  báo xuất hiện ở mọi ca.
- Số hoá PDF hiện giả định đúng layout in chuẩn 3x4+1 của Philips PageWriter;
  nếu máy in ra layout khác (ví dụ 6x2, hoặc nhiều dải nhịp) cần điều chỉnh
  logic nhận diện lưới trong `pdf_reader.py`.
- Chưa xử lý PDF dạng ảnh scan (chỉ đọc được văn bản, không số hoá được dạng
  sóng) - nếu đây là tình huống phổ biến trong thực tế BV, có thể cân nhắc
  thêm OCR + thuật toán trích xuất đường cong từ ảnh raster (phức tạp hơn
  nhiều so với PDF vector, độ chính xác sẽ thấp hơn đáng kể).

## 10. Về dữ liệu & quyền riêng tư

Toàn bộ xử lý diễn ra **cục bộ** trên máy chạy công cụ (không có bước gửi dữ
liệu ra dịch vụ bên ngoài nào trong mã nguồn này). Dữ liệu mẫu BV cung cấp đã
được ẩn danh (tên bệnh nhân, mã bệnh nhân đều là giá trị giữ chỗ, tuổi mặc
định 50) - phù hợp cho mục đích demo/kiểm thử kỹ thuật. Khi triển khai với dữ
liệu bệnh nhân thật, cần bổ sung các biện pháp bảo mật/kiểm soát truy cập phù
hợp quy định của BV và pháp luật hiện hành (nằm ngoài phạm vi bản demo này).

## 11. Tài liệu tham khảo

- Sixlettervariables, *"Philips Healthcare's Sierra ECG format XLI
  Compression Scheme"*, 2011 - phân tích ngược thuật toán nén XLI.
  <https://sixlettervariable.blogspot.com/2011/12/philips-healthcares-sierra-ecg-format.html>
- Dự án mã nguồn mở `sierra-ecg-tools`
  <https://github.com/sixlettervariables/sierra-ecg-tools> và thư viện
  Python `sierraecg` (PyPI) dùng trong công cụ này để giải nén XLI.
- Pan J., Tompkins W.J. (1985), *"A Real-Time QRS Detection Algorithm"*,
  IEEE Trans. Biomed. Eng.
- Hamilton P. (2002), *"Open Source ECG Analysis"*, Computers in Cardiology.
- Elgendi M. et al. (2010), *"Frequency Bands Effects on QRS Detection"*,
  BIOSIGNALS.
- Nabian M. et al. (2018), thuật toán phát hiện QRS mặc định trong thư viện
  `neurokit2`.
- Makowski, D. et al. (2021), *"NeuroKit2: A Python toolbox for
  neurophysiological signal processing"*, Behavior Research Methods.
