"""
Phân loại / gắn cờ sàng lọc bước đầu (rule-based), KHÔNG phải chẩn đoán.

Nguyên tắc chung: mọi ngưỡng đều được chọn LỎNG HƠN ngưỡng lâm sàng kinh điển
một chút, theo đúng yêu cầu "thà nhầm còn hơn bỏ sót" - nghĩa là công cụ chấp
nhận báo động giả (false positive) nhiều hơn để giảm khả năng bỏ sót ca bất
thường thật (false negative). Mỗi cờ đều có giải thích ngưỡng dùng, để bác sĩ
đọc và tự đánh giá lại.

Đây LÀ MỘT MODULE SÀNG LỌC HỖ TRỢ, KHÔNG THAY THẾ NHẬN ĐỊNH CHUYÊN MÔN CỦA
BÁC SĨ. Không dùng để ra quyết định điều trị.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np


@dataclass
class Flag:
    code: str
    level: str          # "info" | "canh_bao" | "nguy_co_cao"
    message: str
    detail: str


def _get(d: Dict[str, Optional[float]], k: str) -> Optional[float]:
    v = d.get(k)
    return v if v is not None and not (isinstance(v, float) and np.isnan(v)) else None


def classify_heart_rate(hr_bpm: Optional[float]) -> List[Flag]:
    flags = []
    if hr_bpm is None:
        return flags
    if hr_bpm < 60:
        flags.append(Flag(
            "HR_LOW", "canh_bao",
            f"Nhịp chậm (~{hr_bpm:.0f} ck/ph)",
            "Ngưỡng cảnh báo: tần số tim tính được < 60 chu kỳ/phút. "
            "Nghi ngờ nhịp chậm xoang / block nhĩ-thất - cần xem lại dải nhịp gốc.",
        ))
    elif hr_bpm > 100:
        flags.append(Flag(
            "HR_HIGH", "canh_bao",
            f"Nhịp nhanh (~{hr_bpm:.0f} ck/ph)",
            "Ngưỡng cảnh báo: tần số tim tính được > 100 chu kỳ/phút. "
            "Có thể là nhịp nhanh xoang, rung/cuồng nhĩ đáp ứng thất nhanh, "
            "nhịp nhanh thất... cần xem lại dải nhịp gốc.",
        ))
    return flags


def classify_rhythm_regularity(rr_cv: Optional[float], n_beats: int) -> List[Flag]:
    flags = []
    if rr_cv is None or n_beats < 4:
        return flags
    # Ngưỡng nhạy: 0.12 (thấp hơn mức 0.15-0.20 hay dùng để gợi ý AFib trong
    # y văn) để tăng độ nhạy phát hiện nhịp không đều.
    THRESH = 0.12
    if rr_cv >= THRESH:
        flags.append(Flag(
            "RHYTHM_IRREGULAR", "canh_bao",
            f"Nhịp không đều (hệ số biến thiên RR = {rr_cv:.2f})",
            f"Ngưỡng cảnh báo: hệ số biến thiên khoảng RR >= {THRESH:.2f}. "
            "Nghi ngờ rung nhĩ / ngoại tâm thu nhiều / nhịp không đều khác - "
            "cần xem lại dải nhịp gốc (đây là chỉ số thống kê thô, độ nhạy cao "
            "nhưng độ đặc hiệu thấp).",
        ))
    return flags


def classify_qrs_width(qrs_ms: Optional[float]) -> List[Flag]:
    flags = []
    if qrs_ms is None:
        return flags
    # Ngưỡng nhạy 110ms thay vì mốc kinh điển 120ms.
    if qrs_ms >= 110:
        flags.append(Flag(
            "QRS_WIDE", "canh_bao",
            f"QRS giãn rộng (~{qrs_ms:.0f} ms)",
            "Ngưỡng cảnh báo: bề rộng QRS ước tính >= 110 ms. Nghi ngờ block "
            "nhánh (RBBB/LBBB), nhịp thất, hoặc rối loạn dẫn truyền trong "
            "thất khác - cần bác sĩ đọc lại hình dạng QRS.",
        ))
    return flags


def classify_qtc(qtc_ms: Optional[float], sex: Optional[str]) -> List[Flag]:
    flags = []
    if qtc_ms is None:
        return flags
    # Ngưỡng nhạy: 440/450 ms (nam/nữ) thay vì 450/460 ms kinh điển.
    threshold = 450.0 if (sex or "").lower().startswith("f") else 440.0
    if qtc_ms >= threshold:
        flags.append(Flag(
            "QTC_LONG", "nguy_co_cao",
            f"QTc kéo dài (~{qtc_ms:.0f} ms)",
            f"Ngưỡng cảnh báo: QTc >= {threshold:.0f} ms. QTc kéo dài liên quan "
            "nguy cơ xoắn đỉnh (Torsades de Pointes) - cần xem lại và đối "
            "chiếu thuốc đang dùng, điện giải đồ.",
        ))
    return flags


def classify_axis(qrs_axis_deg: Optional[float]) -> List[Flag]:
    flags = []
    if qrs_axis_deg is None:
        return flags
    if qrs_axis_deg < -30:
        flags.append(Flag(
            "AXIS_LEFT", "canh_bao",
            f"Trục lệch trái (~{qrs_axis_deg:.0f} độ)",
            "Trục QRS < -30 độ. Có thể gặp ở block phân nhánh trái trước, "
            "phì đại thất trái, nhồi máu thành dưới cũ...",
        ))
    elif qrs_axis_deg > 90:
        flags.append(Flag(
            "AXIS_RIGHT", "canh_bao",
            f"Trục lệch phải (~{qrs_axis_deg:.0f} độ)",
            "Trục QRS > 90 độ. Có thể gặp ở phì đại thất phải, bệnh phổi mạn, "
            "block phân nhánh trái sau...",
        ))
    return flags


def classify_low_voltage(leads_pp_mV: Dict[str, float]) -> List[Flag]:
    flags = []
    limb = {k: v for k, v in leads_pp_mV.items() if k in ("I", "II", "III", "aVR", "aVL", "aVF")}
    if limb and max(limb.values()) < 0.5:
        flags.append(Flag(
            "LOW_VOLTAGE", "canh_bao",
            "Điện thế thấp ở các chuyển đạo chi",
            "Biên độ đỉnh-đỉnh cao nhất ở các chuyển đạo chi < 0.5 mV. Có thể "
            "gặp trong tràn dịch màng ngoài tim, phù niêm, bệnh phổi mạn, "
            "béo phì, hoặc do tuột điện cực - cần kiểm tra lại kỹ thuật ghi.",
        ))
    return flags


def classify_st_deviation(st_deviation_mV: Dict[str, float]) -> List[Flag]:
    """st_deviation_mV: {lead_label: độ lệch đoạn ST tại J+60ms so với baseline, đơn vị mV}"""
    flags = []
    # Ngưỡng nhạy: 0.1 mV (~1 ô nhỏ) - thấp hơn nhiều so với ngưỡng STEMI kinh điển.
    THRESH = 0.10
    offending = {k: v for k, v in st_deviation_mV.items() if abs(v) >= THRESH}
    if offending:
        leads_str = ", ".join(f"{k} ({v:+.2f} mV)" for k, v in sorted(offending.items()))
        flags.append(Flag(
            "ST_CHANGE", "nguy_co_cao",
            f"Nghi thay đổi đoạn ST ở {len(offending)} chuyển đạo",
            f"Ngưỡng cảnh báo: |lệch ST tại J+60ms| >= {THRESH:.2f} mV. Các "
            f"chuyển đạo: {leads_str}. Đây là phép đo thô một điểm, độ nhạy "
            "cao nhưng RẤT DỄ dương tính giả (do nhiễu đường nền, tư thế) - "
            "bắt buộc bác sĩ xem lại dạng sóng gốc trước khi kết luận.",
        ))
    return flags


def summarize(all_flags: List[Flag]) -> str:
    if not all_flags:
        return "Không phát hiện bất thường theo bộ quy tắc sàng lọc - vẫn cần bác sĩ đọc để kết luận."
    n_high = sum(1 for f in all_flags if f.level == "nguy_co_cao")
    n_warn = sum(1 for f in all_flags if f.level == "canh_bao")
    parts = []
    if n_high:
        parts.append(f"{n_high} cảnh báo mức NGUY CƠ CAO")
    if n_warn:
        parts.append(f"{n_warn} cảnh báo")
    return "Phát hiện " + ", ".join(parts) + " - cần bác sĩ xem lại."
