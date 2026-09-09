"""
Đọc file XML điện tâm đồ - hiện hỗ trợ định dạng Philips PageWriter /
"Sierra ECG XML" (documenttype = PhilipsECG hoặc SierraECG), là định dạng
của toàn bộ 100 file mẫu do BV Bạch Mai cung cấp.

Kỹ thuật:
- Tín hiệu 12 chuyển đạo trong file này được nén bằng thuật toán độc quyền
  của Philips gọi là "XLI" (LZW 10-bit + giải mã sai phân bậc 2). Thay vì tự
  viết lại bộ giải nén (rất dễ sai sót, khó kiểm chứng), công cụ dùng thư
  viện mã nguồn mở `sierraecg` (cổng lại từ dự án `sierra-ecg-tools` đã được
  cộng đồng reverse-engineer và kiểm chứng từ 2011) để giải nén chính xác
  từng mẫu tín hiệu gốc (nguyên vẹn theo đơn vị ADC, KHÔNG bị mất dữ liệu).
- Sau khi giải nén, mẫu tín hiệu (số nguyên) được nhân với hệ số phân giải
  <resolution> (đơn vị µV/LSB, đọc từ chính file XML, thường là 5 µV) để ra
  điện thế thực (mV).
- Các thông số máy đã đo (nhịp tim, PR, QRS, QT, QTc, trục điện tim, kết luận
  ABNORMAL/NORMAL...) được trích xuất song song để đối chiếu (không dùng để
  thay thế phép tính của công cụ).

Nếu gặp file XML không phải định dạng Philips, hàm sẽ trả về lỗi rõ ràng thay
vì cố đoán mò cấu trúc.
"""

from __future__ import annotations

from typing import Dict, List, Optional
import xml.etree.ElementTree as ET

import numpy as np

from .common import ECGRecord, LeadSignal


class UnsupportedXmlError(RuntimeError):
    pass


def _read_text_any_encoding(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _strip_ns(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _build_local_tree(raw: bytes) -> ET.Element:
    """Philips XML dùng namespace mặc định (xmlns="http://www3.medical.philips.com").
    Để khỏi phải gõ namespace ở mọi chỗ, ta parse rồi đổi tên tag về dạng
    không-namespace ngay trên cây ElementTree.
    """
    root = ET.fromstring(raw)
    for el in root.iter():
        el.tag = _strip_ns(el.tag)
    return root


def _find_text(root: ET.Element, path: str) -> Optional[str]:
    el = root.find(path)
    if el is None or el.text is None:
        return None
    return el.text.strip() or None


def _find_float(root: ET.Element, path: str) -> Optional[float]:
    txt = _find_text(root, path)
    if txt is None:
        return None
    try:
        return float(txt)
    except ValueError:
        return None


def is_philips_xml(path: str) -> bool:
    try:
        raw = _read_text_any_encoding(path)
        # đọc nhanh 4KB đầu để nhận diện, tránh parse toàn bộ file nếu không cần
        head = raw[:4000]
        try:
            head_txt = head.decode("utf-16")
        except UnicodeDecodeError:
            head_txt = head.decode("utf-8", errors="ignore")
        return ("PhilipsECG" in head_txt) or ("SierraECG" in head_txt) or (
            "medical.philips.com" in head_txt
        )
    except Exception:
        return False


def read_philips_xml(path: str) -> ECGRecord:
    import sierraecg  # import cục bộ để lỗi thiếu thư viện không chặn cả module

    raw = _read_text_any_encoding(path)
    root = _build_local_tree(raw)

    doc_type = _find_text(root, ".//documentinfo/documenttype") or ""
    if doc_type not in ("PhilipsECG", "SierraECG"):
        raise UnsupportedXmlError(
            f"Không nhận diện được định dạng XML (documenttype='{doc_type}'). "
            "Hiện công cụ chỉ hỗ trợ Philips PageWriter / Sierra ECG XML."
        )

    # --- giải nén tín hiệu 12 chuyển đạo bằng thư viện sierraecg ---
    sierra_file = sierraecg.read_file(path)
    resolution_uV = _find_float(root, ".//signalcharacteristics/resolution") or 5.0

    leads: Dict[str, LeadSignal] = {}
    fs = None
    for lead in sierra_file.leads:
        fs = float(lead.sampling_freq)
        mv = np.asarray(lead.samples, dtype=np.float64) * (resolution_uV / 1000.0)
        leads[lead.label] = LeadSignal(label=lead.label, fs=fs, samples_mV=mv)

    record = ECGRecord(
        source_path=path,
        source_format="xml",
        signal_quality="digital_native",
        leads=leads,
    )

    # --- thông tin bệnh nhân / hành chính ---
    record.patient_id = _find_text(root, ".//generalpatientdata/patientid")
    record.patient_name = _find_text(root, ".//generalpatientdata/name/lastname")
    record.patient_sex = _find_text(root, ".//generalpatientdata/sex")
    age_el = root.find(".//generalpatientdata/age")
    record.patient_age = age_el.attrib.get("defaultage") if age_el is not None else None

    date_ = None
    time_ = None
    interp_el = root.find(".//interpretations/interpretation")
    if interp_el is not None:
        date_ = interp_el.attrib.get("date")
        time_ = interp_el.attrib.get("time")
    record.acquisition_datetime = f"{date_ or ''} {time_ or ''}".strip() or None

    # institutionname = tên bệnh viện; facilityname = khoa/viện; departmentname = phòng/khoa con
    record.facility_name = _find_text(root, ".//institutionname")
    record.department_name = _find_text(root, ".//facilityname")

    # --- thông số máy đã đo (để đối chiếu) ---
    gm = root.find(".//globalmeasurements")
    meas: Dict[str, Optional[float]] = {}
    if gm is not None:
        mapping = {
            "heartrate": "HR_bpm",
            "print": "PR_ms",
            "qrsdur": "QRSd_ms",
            "qtint": "QT_ms",
            "qtcb": "QTcB_ms",
            "qtcf": "QTcF_ms",
            "qrsfrontaxis": "QRS_axis_deg",
            "pfrontaxis": "P_axis_deg",
            "tfrontaxis": "T_axis_deg",
        }
        for xml_tag, key in mapping.items():
            meas[key] = _find_float(gm, xml_tag)
    record.device_measurements = meas

    severity_el = root.find(".//interpretations/interpretation/severity")
    if severity_el is not None and severity_el.text:
        record.device_severity = severity_el.text.strip()

    statements: List[str] = []
    for st in root.findall(".//interpretations/interpretation//leftstatement"):
        if st.text and st.text.strip():
            statements.append(st.text.strip())
    for st in root.findall(".//interpretations/interpretation//rightstatement"):
        if st.text and st.text.strip():
            statements.append(st.text.strip())
    record.device_interpretation = statements

    if not leads:
        record.warnings.append("Không giải mã được tín hiệu 12 chuyển đạo từ file XML.")

    return record


def read_xml(path: str) -> ECGRecord:
    if is_philips_xml(path):
        return read_philips_xml(path)
    raise UnsupportedXmlError(
        "Định dạng XML này chưa được hỗ trợ. Hiện công cụ chỉ đọc được XML "
        "kiểu Philips PageWriter / Sierra ECG (documenttype=PhilipsECG hoặc "
        "SierraECG). Vui lòng liên hệ để bổ sung định dạng khác."
    )
