"""
Ghép nối toàn bộ pipeline: đọc file -> phát hiện QRS -> đo lường -> gắn cờ
sàng lọc. Đây là điểm vào (entry point) chính mà giao diện (app.py) và script
kiểm thử hàng loạt (validate.py) cùng gọi tới, để đảm bảo logic phân tích chỉ
có MỘT nơi duy nhất (tránh hai chỗ tính khác nhau).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .common import ECGRecord
from .qrs import QRSResult, analyze_lead, _pick_reference_lead
from .morphology import peak_to_peak_mV, st_deviation_mV
from .classify import (
    Flag, classify_heart_rate, classify_rhythm_regularity, classify_qrs_width,
    classify_qtc, classify_axis, classify_low_voltage, classify_st_deviation,
    summarize,
)


class UnsupportedFileError(RuntimeError):
    pass


def read_ecg_file(path: str) -> ECGRecord:
    ext = Path(path).suffix.lower()
    if ext == ".xml":
        from .xml_reader import read_xml
        return read_xml(path)
    if ext == ".pdf":
        from .pdf_reader import read_pdf
        return read_pdf(path)
    raise UnsupportedFileError(f"Không hỗ trợ định dạng file '{ext}'. Chỉ hỗ trợ .xml và .pdf")


@dataclass
class AnalysisReport:
    record: ECGRecord
    reference_lead: str
    qrs: QRSResult
    peak_to_peak_mV: Dict[str, float]
    st_deviation_mV: Dict[str, float]
    flags: List[Flag] = field(default_factory=list)
    summary_text: str = ""
    device_vs_tool_hr_diff: Optional[float] = None


def analyze_record(record: ECGRecord) -> AnalysisReport:
    leads_mV = {name: sig.samples_mV for name, sig in record.leads.items()}
    fs = next(iter(record.leads.values())).fs

    ref_lead = _pick_reference_lead(leads_mV)
    qrs = analyze_lead(leads_mV[ref_lead], fs, ref_lead)

    pp = peak_to_peak_mV(leads_mV)
    st_dev = st_deviation_mV(leads_mV, fs, qrs.r_peaks_idx)

    # nếu là PDF chỉ số hoá được dải nhịp (1 chuyển đạo), bổ sung biên độ /
    # ST của các chuyển đạo "snapshot" (đoạn ngắn, độ tin cậy thấp hơn) để
    # người dùng vẫn thấy được ước lượng, có ghi rõ mức tin cậy trong UI.
    if record.snapshot_leads:
        snap_mV = {name: sig.samples_mV for name, sig in record.snapshot_leads.items()}
        pp.update({k: v for k, v in peak_to_peak_mV(snap_mV).items() if k not in pp})

    flags: List[Flag] = []
    flags += classify_heart_rate(qrs.heart_rate_bpm)
    flags += classify_rhythm_regularity(qrs.rr_cv, len(qrs.r_peaks_idx))
    flags += classify_qrs_width(qrs.qrs_duration_ms_median)

    qtc = record.device_measurements.get("QTcB_ms") or record.device_measurements.get("QTcF_ms")
    flags += classify_qtc(qtc, record.patient_sex)

    axis = record.device_measurements.get("QRS_axis_deg")
    flags += classify_axis(axis)

    flags += classify_low_voltage(pp)

    # ST chỉ đánh giá trên các chuyển đạo có dữ liệu đồng bộ thời gian đầy đủ
    # (record.leads) - tránh dùng snapshot_leads (không đồng bộ) cho việc này.
    if record.signal_quality == "digital_native":
        flags += classify_st_deviation(st_dev)

    device_hr = record.device_measurements.get("HR_bpm")
    hr_diff = None
    if device_hr is not None and qrs.heart_rate_bpm is not None:
        hr_diff = qrs.heart_rate_bpm - device_hr

    return AnalysisReport(
        record=record,
        reference_lead=ref_lead,
        qrs=qrs,
        peak_to_peak_mV=pp,
        st_deviation_mV=st_dev,
        flags=flags,
        summary_text=summarize(flags),
        device_vs_tool_hr_diff=hr_diff,
    )
