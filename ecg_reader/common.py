"""
Cấu trúc dữ liệu dùng chung cho toàn bộ pipeline đọc & phân tích ECG.

ECGRecord là "hợp đồng" (contract) giữa lớp đọc file (xml_reader / pdf_reader)
và lớp xử lý tín hiệu (qrs.py / classify.py) cũng như giao diện (app.py).
Dù dữ liệu gốc là XML (tín hiệu số hoá đầy đủ) hay PDF (số hoá lại từ nét vẽ
vector trên bản in), sau bước đọc file, mọi thứ đều được chuẩn hoá về cùng
một dạng ECGRecord để phần còn lại của chương trình không cần quan tâm nguồn
gốc dữ liệu.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

# Thứ tự 12 chuyển đạo chuẩn theo cách trình bày thông dụng của điện tâm đồ
STANDARD_LEAD_ORDER = ["I", "II", "III", "aVR", "aVL", "aVF",
                        "V1", "V2", "V3", "V4", "V5", "V6"]


@dataclass
class LeadSignal:
    """Tín hiệu của một chuyển đạo, đơn vị mV, đã quy về trục thời gian chung."""
    label: str
    fs: float                     # tần số lấy mẫu (Hz)
    samples_mV: np.ndarray        # mảng 1 chiều, đơn vị mV


@dataclass
class ECGRecord:
    """Kết quả chuẩn hoá của một bản ghi ECG (1 file PDF hoặc XML)."""

    source_path: str
    source_format: str            # "xml" | "pdf"
    # "digital_native": số hoá gốc từ máy (độ tin cậy cao, dùng cho XML Philips)
    # "pdf_digitized": số hoá lại từ nét vẽ vector trong PDF (độ tin cậy thấp hơn)
    signal_quality: str

    leads: Dict[str, LeadSignal] = field(default_factory=dict)
    # Chỉ dùng khi source_format == "pdf": các đoạn tín hiệu ngắn (~2.5s) của
    # từng chuyển đạo trong lưới 3x4 trên bản in, KHÔNG cùng trục thời gian
    # với nhau (mỗi hàng là một cửa sổ thời gian khác nhau) nên không thể
    # gộp chung vào `leads` để phân tích đa chuyển đạo đồng thời. Chỉ dùng để
    # hiển thị và tính các chỉ số riêng của từng chuyển đạo (biên độ, ST...).
    snapshot_leads: Dict[str, LeadSignal] = field(default_factory=dict)

    # Thông tin hành chính / nhân khẩu học (có thể thiếu tuỳ file)
    patient_id: Optional[str] = None
    patient_name: Optional[str] = None
    patient_sex: Optional[str] = None
    patient_age: Optional[str] = None
    acquisition_datetime: Optional[str] = None
    facility_name: Optional[str] = None
    department_name: Optional[str] = None

    # Các thông số đo được do MÁY ghi báo cáo sẵn (nếu có) - dùng để đối chiếu,
    # KHÔNG dùng để thay thế việc tự tính toán của công cụ này.
    device_measurements: Dict[str, Optional[float]] = field(default_factory=dict)
    device_interpretation: List[str] = field(default_factory=list)
    device_severity: Optional[str] = None

    warnings: List[str] = field(default_factory=list)

    def ordered_leads(self) -> List[LeadSignal]:
        """Trả về danh sách LeadSignal theo thứ tự chuẩn I,II,III,aVR,...,V6
        (các chuyển đạo không có trong dữ liệu sẽ bị bỏ qua)."""
        out = []
        for name in STANDARD_LEAD_ORDER:
            if name in self.leads:
                out.append(self.leads[name])
        # thêm các chuyển đạo lạ (không thuộc danh sách chuẩn) vào cuối, nếu có
        for name, sig in self.leads.items():
            if name not in STANDARD_LEAD_ORDER:
                out.append(sig)
        return out

    def duration_sec(self) -> float:
        if not self.leads:
            return 0.0
        any_lead = next(iter(self.leads.values()))
        return len(any_lead.samples_mV) / any_lead.fs
