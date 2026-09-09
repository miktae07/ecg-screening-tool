"""
Script kiểm thử (validation) chạy pipeline trên toàn bộ tập mẫu do BV cung cấp
(100 cặp file .xml/.pdf), rồi đối chiếu với các thông số MÁY đã tính sẵn để
đánh giá độ chính xác một cách khách quan, có số liệu.

Cách chạy:
    python3 validate.py /duong/dan/den/thu_muc_chua_file_mau

Kết quả: in ra màn hình + ghi ra validation_report.csv (chi tiết từng file)
và in bảng tổng hợp cuối cùng (dùng để đưa vào tài liệu kỹ thuật).

LƯU Ý: script này không chỉnh sửa hay gửi dữ liệu bệnh nhân đi đâu cả - chỉ
đọc file cục bộ và ghi báo cáo số liệu tổng hợp (không chứa thông tin định
danh bệnh nhân) ra thư mục hiện tại.
"""

from __future__ import annotations

import csv
import sys
import time
import traceback
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

from ecg_reader import read_ecg_file, analyze_record  # noqa: E402


def main(sample_dir: str, limit: int | None = None):
    sample_dir = Path(sample_dir)
    xml_files = sorted(sample_dir.glob("*.xml"))
    if limit:
        xml_files = xml_files[:limit]

    rows = []
    t_start = time.time()
    for i, xf in enumerate(xml_files):
        pf = xf.with_suffix(".pdf")
        row = {"file": xf.stem}
        try:
            t0 = time.time()
            xrec = read_ecg_file(str(xf))
            xrep = analyze_record(xrec)
            row["xml_time_s"] = round(time.time() - t0, 2)
            row["device_hr"] = xrec.device_measurements.get("HR_bpm")
            row["xml_tool_hr"] = xrep.qrs.heart_rate_bpm
            row["device_qrsd"] = xrec.device_measurements.get("QRSd_ms")
            row["xml_tool_qrsd"] = xrep.qrs.qrs_duration_ms_median
            row["device_severity"] = xrec.device_severity
            row["xml_n_flags"] = len(xrep.flags)
            row["xml_flag_codes"] = ";".join(f.code for f in xrep.flags)
            row["xml_n_peaks"] = len(xrep.qrs.r_peaks_idx)
        except Exception as e:
            row["xml_error"] = f"{type(e).__name__}: {e}"

        if pf.exists():
            try:
                t0 = time.time()
                prec = read_ecg_file(str(pf))
                prep = analyze_record(prec)
                row["pdf_time_s"] = round(time.time() - t0, 2)
                row["pdf_tool_hr"] = prep.qrs.heart_rate_bpm
                row["pdf_n_flags"] = len(prep.flags)
                row["pdf_flag_codes"] = ";".join(f.code for f in prep.flags)
                row["pdf_n_peaks"] = len(prep.qrs.r_peaks_idx)
                row["pdf_n_rhythm_leads"] = len(prec.leads)
                row["pdf_n_snapshot_leads"] = len(prec.snapshot_leads)
            except Exception as e:
                row["pdf_error"] = f"{type(e).__name__}: {e}"

        rows.append(row)
        print(f"[{i+1}/{len(xml_files)}] {xf.stem}  "
              f"HR device={row.get('device_hr')} xml_tool={row.get('xml_tool_hr')} "
              f"pdf_tool={row.get('pdf_tool_hr')}  severity={row.get('device_severity')} "
              f"n_flags(xml/pdf)={row.get('xml_n_flags')}/{row.get('pdf_n_flags')}"
              + (f"  XML-ERROR: {row['xml_error']}" if "xml_error" in row else "")
              + (f"  PDF-ERROR: {row['pdf_error']}" if "pdf_error" in row else ""))

    out_csv = Path(__file__).parent / "validation_report.csv"
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    # ---- tổng hợp ----
    def valid_pairs(key_a, key_b):
        return [(r[key_a], r[key_b]) for r in rows
                 if r.get(key_a) is not None and r.get(key_b) is not None]

    xml_hr_pairs = valid_pairs("device_hr", "xml_tool_hr")
    pdf_hr_pairs = valid_pairs("device_hr", "pdf_tool_hr")

    def mae_corr(pairs):
        if len(pairs) < 2:
            return None, None
        a = np.array([p[0] for p in pairs])
        b = np.array([p[1] for p in pairs])
        return float(np.mean(np.abs(a - b))), float(np.corrcoef(a, b)[0, 1])

    xml_mae, xml_corr = mae_corr(xml_hr_pairs)
    pdf_mae, pdf_corr = mae_corr(pdf_hr_pairs)

    def sev(r):
        return (r.get("device_severity") or "").upper().strip("- ").strip()

    n_abnormal = sum(1 for r in rows if sev(r) == "ABNORMAL ECG")
    n_abnormal_flagged = sum(1 for r in rows if sev(r) == "ABNORMAL ECG" and (r.get("xml_n_flags") or 0) > 0)
    n_normal = sum(1 for r in rows if "NORMAL" in sev(r) and "ABNORMAL" not in sev(r))
    n_normal_flagged = sum(1 for r in rows if "NORMAL" in sev(r) and "ABNORMAL" not in sev(r) and (r.get("xml_n_flags") or 0) > 0)
    n_borderline = sum(1 for r in rows if "BORDERLINE" in sev(r))
    n_borderline_flagged = sum(1 for r in rows if "BORDERLINE" in sev(r) and (r.get("xml_n_flags") or 0) > 0)

    n_xml_err = sum(1 for r in rows if "xml_error" in r)
    n_pdf_err = sum(1 for r in rows if "pdf_error" in r)

    print("\n================ TỔNG HỢP ================")
    print(f"Tổng số file: {len(rows)}  (lỗi đọc XML: {n_xml_err}, lỗi đọc PDF: {n_pdf_err})")
    print(f"[XML] Sai số tuyệt đối trung bình HR so với máy (MAE): {xml_mae:.2f} bpm | tương quan r = {xml_corr:.3f}  (n={len(xml_hr_pairs)})")
    if pdf_mae is not None:
        print(f"[PDF-số hoá] Sai số tuyệt đối trung bình HR so với máy (MAE): {pdf_mae:.2f} bpm | tương quan r = {pdf_corr:.3f}  (n={len(pdf_hr_pairs)})")
    print(f"Trong số {n_abnormal} ca máy kết luận 'ABNORMAL ECG': công cụ gắn được >=1 cờ cảnh báo cho {n_abnormal_flagged} ca "
          f"({(100.0*n_abnormal_flagged/n_abnormal if n_abnormal else 0):.1f}% - độ nhạy sàng lọc thô so với kết luận máy)")
    print(f"Trong số {n_normal} ca máy kết luận bình thường: công cụ VẪN gắn cờ cho {n_normal_flagged} ca "
          f"({(100.0*n_normal_flagged/n_normal if n_normal else 0):.1f}% - tỷ lệ dương tính giả kỳ vọng, do thiết kế ưu tiên độ nhạy)")
    print(f"Trong số {n_borderline} ca máy kết luận 'BORDERLINE': công cụ gắn cờ cho {n_borderline_flagged} ca "
          f"({(100.0*n_borderline_flagged/n_borderline if n_borderline else 0):.1f}%)")
    print(f"Thời gian xử lý trung bình mỗi file XML: {np.mean([r['xml_time_s'] for r in rows if 'xml_time_s' in r]):.2f} giây")
    print(f"Đã ghi chi tiết từng file vào: {out_csv}")
    print(f"Tổng thời gian chạy: {time.time()-t_start:.1f} giây")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Cách dùng: python3 validate.py <thư_mục_chứa_file_mẫu> [số_lượng_giới_hạn]")
        sys.exit(1)
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    main(sys.argv[1], limit)
