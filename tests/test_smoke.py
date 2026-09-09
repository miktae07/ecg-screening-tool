"""
Kiểm thử nhanh (smoke test) - không cần pytest, chỉ cần chạy:

    python3 tests/test_smoke.py /duong/dan/toi/mot_file_mau.xml

Dùng để xác nhận cài đặt môi trường (thư viện) đã đúng và pipeline đọc/phân
tích chạy được đầu-cuối trên một file thật, trước khi mở giao diện demo cho
người dùng xem.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ecg_reader import read_ecg_file, analyze_record  # noqa: E402


def main(path: str):
    rec = read_ecg_file(path)
    assert rec.leads, "Không đọc được chuyển đạo nào - kiểm tra lại file đầu vào"
    rep = analyze_record(rec)

    print(f"OK: đọc file '{path}'")
    print(f"  - Định dạng: {rec.source_format} ({rec.signal_quality})")
    print(f"  - Số chuyển đạo: {len(rec.leads)} (+{len(rec.snapshot_leads)} chuyển đạo phụ nếu là PDF)")
    print(f"  - Tần số tim ước tính: {rep.qrs.heart_rate_bpm}")
    print(f"  - Số cờ cảnh báo: {len(rep.flags)}")
    print("  - Không có lỗi trong quá trình xử lý.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Cách dùng: python3 tests/test_smoke.py <duong_dan_file.xml_hoac_.pdf>")
        sys.exit(1)
    main(sys.argv[1])
