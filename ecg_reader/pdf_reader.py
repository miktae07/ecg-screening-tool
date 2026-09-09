"""
Đọc file PDF báo cáo điện tâm đồ (dùng khi BỆNH VIỆN CHỈ CÓ FILE PDF, không có
XML đi kèm).

Hai phần độc lập:

1. TRÍCH VĂN BẢN (luôn làm, rất tin cậy): tên bệnh viện/khoa, thông tin bệnh
   nhân (đã ẩn danh trong dữ liệu mẫu), và các thông số máy đã in sẵn trên tờ
   báo cáo (nhịp tim, PR, QRS, QT, QTc, trục điện tim, kết luận). Các máy
   Philips PageWriter xuất PDF với lớp văn bản thật (không phải ảnh chụp) nên
   trích xuất bằng PyMuPDF cho kết quả chính xác gần như tuyệt đối.

2. SỐ HOÁ LẠI DẠNG SÓNG TỪ NÉT VẼ VECTOR (thử nghiệm - "best effort"): các bản
   ghi Philips xuất PDF dạng vector (đường ECG được vẽ bằng các đoạn thẳng nối
   tiếp nhau, KHÔNG phải ảnh bitmap). Nhờ vậy có thể đọc lại toạ độ (x, y) của
   từng điểm trên đường vẽ và quy đổi ngược về (thời gian, điện thế) bằng hệ số
   hiệu chuẩn in trên tờ báo cáo (tốc độ giấy mm/s, độ khuếch đại mm/mV).

   Hạn chế cần lưu ý (đã ghi rõ trong tài liệu kỹ thuật và trong giao diện):
     - Layout in ấn tiêu chuẩn 3 hàng x 4 cột thể hiện các CỬA SỔ THỜI GIAN
       KHÁC NHAU cho mỗi hàng (hàng 1: giây 0-2.5, hàng 2: giây 2.5-5, hàng 3:
       giây 5-7.5) - 4 chuyển đạo trong CÙNG một hàng thì đồng bộ với nhau,
       nhưng KHÔNG đồng bộ với chuyển đạo ở hàng khác. Vì vậy các chuyển đạo
       này chỉ dùng để xem/đo riêng lẻ, KHÔNG dùng để phân tích đa chuyển đạo
       đồng thời (trục điện tim, so sánh thời gian...).
     - Dải nhịp (rhythm strip) ở cuối trang thường dài hơn (ở đây 10 giây) và
       CHỈ GỒM 1 CHUYỂN ĐẠO (thường là II) - đây là nguồn dữ liệu chính để
       tính tần số tim / độ đều nhịp / bề rộng QRS khi chỉ có PDF.
     - Độ phân giải biên độ giới hạn bởi độ chính xác toạ độ trong PDF, thấp
       hơn so với đọc trực tiếp từ XML.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import numpy as np

from .common import ECGRecord, LeadSignal

LEAD_NAMES = ["I", "II", "III", "aVR", "aVL", "aVF", "V1", "V2", "V3", "V4", "V5", "V6"]

MM_PER_PT = 25.4 / 72.0  # 1 điểm PDF (pt) = 25.4/72 mm


def _extract_text_metadata(page) -> Dict[str, object]:
    text = page.get_text()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    info: Dict[str, object] = {
        "facility_name": None,
        "department_name": None,
        "sex": None,
        "acquisition_datetime": None,
        "severity": None,
        "measurements": {},
        "paper_speed_mm_s": 25.0,
        "gain_mm_mV": 10.0,
    }

    if lines:
        info["facility_name"] = lines[0]
    if len(lines) > 1:
        info["department_name"] = lines[1]

    for ln in lines:
        m = re.match(r"^(\d{1,2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2})", ln)
        if m:
            info["acquisition_datetime"] = m.group(1)
        if ln in ("Male", "Female"):
            info["sex"] = ln
        if "ABNORMAL" in ln.upper() or "NORMAL" in ln.upper():
            if ln.startswith("-") or ln.upper().startswith("- "):
                info["severity"] = ln.strip("- ").strip()

    # thông số dạng "HR 147 bpm", "PR 84 ms", "QRSD 73 ms", "QT 330 ms", "QTc 517 ms"
    patterns = {
        "HR_bpm": r"HR\s*\n?\s*(\d+)\s*bpm",
        "PR_ms": r"PR\s*\n?\s*(\d+)\s*ms",
        "QRSd_ms": r"QRSD\s*\n?\s*(\d+)\s*ms",
        "QT_ms": r"QT\s*\n?\s*(\d+)\s*ms",
        "QTcB_ms": r"QTc\s*\n?\s*(\d+)\s*ms",
        "QRS_axis_deg": r"QRS\s*\n?\s*(-?\d+)\s*deg",
        "P_axis_deg": r"P\s*\n?\s*(-?\d+)\s*deg",
        "T_axis_deg": r"T\s*\n?\s*(-?\d+)\s*deg",
    }
    flat = "\n".join(lines)
    meas: Dict[str, float] = {}
    for key, pat in patterns.items():
        m = re.search(pat, flat)
        if m:
            try:
                meas[key] = float(m.group(1))
            except ValueError:
                pass
    info["measurements"] = meas

    m = re.search(r"Chest:\s*([\d.]+)\s*mm/mV", flat)
    if m:
        info["gain_mm_mV"] = float(m.group(1))
    m = re.search(r"Speed:\s*([\d.]+)\s*mm/sec", flat)
    if m:
        info["paper_speed_mm_s"] = float(m.group(1))

    return info


def _label_positions(page) -> List[Tuple[str, float, float]]:
    out = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        t = text.strip()
        if t in LEAD_NAMES:
            out.append((t, x0, y0))
    return out


def _is_trace_like(d) -> bool:
    color = d.get("color")
    width = d.get("width") or 0
    items = d.get("items") or []
    if color is None:
        return False
    if not (max(color) < 0.35):  # gần màu đen
        return False
    if not (0.25 <= width <= 0.7):
        return False
    if len(items) < 300:
        return False
    return all(it[0] == "l" for it in items)


def _polyline_from_drawing(d) -> np.ndarray:
    items = d["items"]
    pts = [items[0][1]] + [it[2] for it in items]
    return np.array([[p.x, p.y] for p in pts], dtype=float)


def _assign_label(rect, labels: List[Tuple[str, float, float]]) -> Optional[str]:
    """Ghép nhãn tên chuyển đạo (vị trí chữ in trên trang) với ô trace gần nhất.

    Lưu ý: không dùng ràng buộc "nhãn phải nằm phía trên trace" một cách cứng
    nhắc, vì với nhịp biên độ QRS lớn, cạnh trên của bounding-box trace (tính
    từ chính nét vẽ) có thể vượt lên cao hơn cả vị trí chữ nhãn. Thay vào đó
    ghép theo khoảng cách (x, y) gần nhất trong một ngưỡng hợp lý.
    """
    best = None
    best_dist = None
    for name, lx, ly in labels:
        dx = abs(lx - rect.x0)
        dy = abs(ly - rect.y0)
        if dx > 60 or dy > 60:
            continue
        dist = dx + dy
        if best_dist is None or dist < best_dist:
            best_dist = dist
            best = name
    return best


def read_pdf(path: str) -> ECGRecord:
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    page = doc[0]

    meta = _extract_text_metadata(page)
    labels = _label_positions(page)
    draws = page.get_drawings()
    traces = [d for d in draws if _is_trace_like(d)]

    if not traces:
        record = ECGRecord(
            source_path=path,
            source_format="pdf",
            signal_quality="pdf_digitized",
        )
        record.warnings.append(
            "Không tìm thấy đường vẽ dạng vector trong PDF (có thể là PDF dạng "
            "ảnh scan) - công cụ hiện chưa hỗ trợ số hoá dạng sóng từ ảnh scan, "
            "chỉ đọc được thông tin văn bản."
        )
    else:
        widths = [d["rect"].x1 - d["rect"].x0 for d in traces]
        median_w = float(np.median(widths))
        sec_per_pt = MM_PER_PT / meta["paper_speed_mm_s"]
        mv_per_pt = MM_PER_PT / meta["gain_mm_mV"]

        rhythm_leads: Dict[str, LeadSignal] = {}
        snapshot_leads: Dict[str, LeadSignal] = {}
        warnings: List[str] = []

        for d in traces:
            rect = d["rect"]
            is_rhythm = (rect.x1 - rect.x0) > median_w * 1.8
            label = _assign_label(rect, labels)
            xy = _polyline_from_drawing(d)

            t_sec = (xy[:, 0] - xy[0, 0]) * sec_per_pt
            baseline_y = float(np.median(xy[:, 1]))
            mv = (baseline_y - xy[:, 1]) * mv_per_pt  # trục y PDF hướng xuống -> đảo dấu

            dt = np.median(np.diff(t_sec)) if len(t_sec) > 1 else None
            fs_est = 1.0 / dt if dt and dt > 0 else 500.0
            t_uniform = np.arange(0, t_sec[-1], 1.0 / fs_est)
            mv_uniform = np.interp(t_uniform, t_sec, mv)

            sig = LeadSignal(label=label or "?", fs=fs_est, samples_mV=mv_uniform)

            if is_rhythm:
                if not label:
                    label = "II"
                    warnings.append(
                        "Không xác định chắc chắn tên chuyển đạo của dải nhịp, "
                        "mặc định coi là chuyển đạo II (phổ biến nhất)."
                    )
                sig.label = label
                rhythm_leads[label] = sig
            elif label:
                snapshot_leads[label] = sig

        if not rhythm_leads and snapshot_leads:
            warnings.append(
                "Không tìm thấy dải nhịp dài (rhythm strip) trong PDF - dùng "
                "tạm đoạn 2.5 giây của chuyển đạo có sẵn để ước lượng, độ tin "
                "cậy sẽ THẤP HƠN NHIỀU so với khi có dải nhịp hoặc file XML."
            )
            # dùng chuyển đạo có năng lượng tín hiệu lớn nhất làm tạm thời "leads" chính
            best_label = max(snapshot_leads, key=lambda k: float(np.std(snapshot_leads[k].samples_mV)))
            rhythm_leads = {best_label: snapshot_leads[best_label]}

        record = ECGRecord(
            source_path=path,
            source_format="pdf",
            signal_quality="pdf_digitized",
            leads=rhythm_leads,
            snapshot_leads=snapshot_leads,
        )
        record.warnings.extend(warnings)
        record.warnings.append(
            "Dữ liệu được số hoá lại từ nét vẽ trong PDF (không phải tín hiệu số "
            "gốc) - độ chính xác về biên độ và thời gian THẤP HƠN so với đọc "
            "trực tiếp từ file XML. Nên ưu tiên dùng file XML nếu có."
        )

    record.facility_name = meta["facility_name"]
    record.department_name = meta["department_name"]
    record.patient_sex = meta["sex"]
    record.acquisition_datetime = meta["acquisition_datetime"]
    record.device_severity = meta["severity"]
    record.device_measurements = meta["measurements"]
    return record
