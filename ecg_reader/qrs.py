"""
Phát hiện phức bộ QRS và tính các thông số cơ bản từ tín hiệu ECG đã số hoá.

Triết lý thiết kế (theo yêu cầu của BV): "THÀ NHẦM CÒN HƠN BỎ SÓT" - nhưng áp
dụng có kiểm soát, sau khi thử nghiệm cho thấy nếu hợp (union) mù quáng toàn
bộ kết quả của nhiều thuật toán, riêng những thuật toán kém ổn định hơn trên
tín hiệu nhiều nhiễu/bất thường (đặc biệt Hamilton 2002 và Elgendi 2010) tạo
ra rất nhiều đỉnh giả không khớp nhịp thật, làm tần số tim tính ra SAI LỆCH
NGHIÊM TRỌNG (gấp 1.5-2 lần thực tế trong thử nghiệm ban đầu trên chính bộ dữ
liệu mẫu của bệnh viện) - phản tác dụng, khiến cảnh báo trở nên vô nghĩa.

Giải pháp áp dụng - "đồng thuận có trọng số" (ensemble voting):

1. Chạy đồng thời 4 thuật toán phát hiện QRS đã công bố và kiểm chứng rộng
   rãi: NeuroKit2 mặc định (Nabian et al. 2018), Pan & Tompkins (1985),
   Hamilton (2002), Elgendi et al. (2010).
2. Gộp các đỉnh do các thuật toán khác nhau tìm ra nhưng cùng rơi vào một
   cửa sổ +-120ms (coi là cùng một nhịp thật) thành một "cụm".
3. Một cụm được từ >= 2/4 thuật toán ĐỘC LẬP cùng đồng ý -> coi là NHỊP ĐÃ
   XÁC NHẬN (confirmed), dùng để tính tần số tim, độ đều nhịp, bề rộng QRS.
4. Một cụm chỉ có 1/4 thuật toán tìm thấy -> coi là NHỊP NGHI NGỜ (candidate,
   "khả nghi"): KHÔNG đưa vào các con số thống kê định lượng (để tránh làm
   sai lệch tần số tim), nhưng VẪN được hiển thị riêng trên biểu đồ (ký hiệu
   khác) để bác sĩ tự xem lại - đây chính là chỗ áp dụng tinh thần "thà nhầm
   còn hơn bỏ sót": thay vì im lặng bỏ qua, công cụ vẫn báo cho người dùng
   biết "có thể có một nhịp ở đây, các thuật toán chưa thống nhất".
5. Ngưỡng sinh lý cứng duy nhất: khoảng cách tối thiểu giữa 2 nhịp xác nhận
   là 200ms (tương ứng < 300 nhịp/phút) - không lọc theo hình dạng/biên độ để
   tránh loại nhầm ngoại tâm thu hay nhịp bất thường thật.

Cách làm này giữ được độ nhạy cao hơn một thuật toán đơn lẻ (nhờ cơ chế đồng
thuận đa thuật toán và việc vẫn hiển thị các nhịp khả nghi), đồng thời tránh
được hiện tượng tần số tim bị thổi phồng phi thực tế do một thuật toán kém ổn
định "hallucinate". Độ chính xác thực đo trên 100 file mẫu được báo cáo minh
bạch trong tài liệu kỹ thuật đi kèm (validate.py).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

try:
    import neurokit2 as nk
except Exception:  # pragma: no cover
    nk = None

ENSEMBLE_METHODS = ["neurokit", "pantompkins1985", "hamilton2002", "elgendi2010"]
MIN_RR_SEC = 0.20          # 300 bpm - giới hạn sinh lý cứng
CLUSTER_WINDOW_SEC = 0.12  # cửa sổ gộp các đỉnh của các thuật toán khác nhau
MIN_VOTES_CONFIRMED = 2    # số thuật toán tối thiểu đồng thuận để tính là "đã xác nhận"


@dataclass
class QRSResult:
    lead_used: str
    fs: float
    r_peaks_idx: np.ndarray            # nhịp ĐÃ XÁC NHẬN (>=2/4 thuật toán đồng thuận)
    r_peaks_time_sec: np.ndarray
    candidate_peaks_idx: np.ndarray    # nhịp KHẢ NGHI (chỉ 1/4 thuật toán) - để hiển thị thêm
    rr_intervals_ms: np.ndarray
    heart_rate_bpm: Optional[float]
    heart_rate_min_bpm: Optional[float]
    heart_rate_max_bpm: Optional[float]
    rr_cv: Optional[float]             # hệ số biến thiên RR (SD/mean) -> độ đều nhịp
    qrs_duration_ms_median: Optional[float]
    qrs_duration_ms_list: List[float]
    per_method_counts: Dict[str, int]  # số đỉnh mỗi thuật toán tìm được (để QC)
    notes: List[str] = field(default_factory=list)


def _pick_reference_lead(leads: Dict[str, "np.ndarray"]) -> str:
    """Chọn chuyển đạo đại diện để phát hiện QRS: ưu tiên II (kinh điển cho
    nhịp), nếu không có thì chọn chuyển đạo có năng lượng tín hiệu (độ lệch
    chuẩn) lớn nhất, tức QRS rõ nhất."""
    if "II" in leads:
        return "II"
    if not leads:
        raise ValueError("Không có chuyển đạo nào để phát hiện QRS")
    return max(leads.keys(), key=lambda k: float(np.std(leads[k])))


def _enforce_min_rr(peaks_idx: np.ndarray, fs: float, min_rr_sec: float) -> np.ndarray:
    if len(peaks_idx) == 0:
        return peaks_idx
    peaks_idx = np.sort(peaks_idx)
    kept = [int(peaks_idx[0])]
    min_gap = min_rr_sec * fs
    for p in peaks_idx[1:]:
        if p - kept[-1] < min_gap:
            continue
        kept.append(int(p))
    return np.asarray(kept, dtype=int)


def _vote_cluster(all_points: List["tuple[int, str]"], fs: float
                   ) -> "tuple[np.ndarray, np.ndarray]":
    """all_points: danh sách (vị trí mẫu, tên thuật toán). Trả về
    (nhịp_đã_xác_nhận, nhịp_khả_nghi)."""
    if not all_points:
        return np.array([], dtype=int), np.array([], dtype=int)

    all_points = sorted(all_points, key=lambda x: x[0])
    window = CLUSTER_WINDOW_SEC * fs

    clusters: List[List["tuple[int, str]"]] = [[all_points[0]]]
    for p in all_points[1:]:
        if p[0] - clusters[-1][-1][0] <= window:
            clusters[-1].append(p)
        else:
            clusters.append([p])

    confirmed, candidate = [], []
    for c in clusters:
        methods = set(m for _, m in c)
        loc = int(round(np.median([idx for idx, _ in c])))
        if len(methods) >= MIN_VOTES_CONFIRMED:
            confirmed.append(loc)
        else:
            candidate.append(loc)

    return (_enforce_min_rr(np.array(confirmed, dtype=int), fs, MIN_RR_SEC),
            np.array(sorted(candidate), dtype=int))


def detect_qrs_ensemble(signal_mV: np.ndarray, fs: float
                         ) -> "tuple[np.ndarray, np.ndarray, Dict[str, int]]":
    """Chạy nhiều thuật toán phát hiện QRS rồi đồng thuận theo số phiếu bầu.
    Trả về (nhịp_đã_xác_nhận, nhịp_khả_nghi, số_đỉnh_mỗi_thuật_toán)."""
    if nk is None:
        raise RuntimeError("Thiếu thư viện neurokit2 (pip install neurokit2)")

    cleaned = nk.ecg_clean(signal_mV, sampling_rate=fs, method="neurokit")

    all_points: List["tuple[int, str]"] = []
    per_method: Dict[str, int] = {}
    for method in ENSEMBLE_METHODS:
        try:
            _, info = nk.ecg_peaks(cleaned, sampling_rate=fs, method=method, correct_artifacts=False)
            peaks = np.asarray(info.get("ECG_R_Peaks", np.array([], dtype=int)), dtype=int)
        except Exception:
            peaks = np.array([], dtype=int)
        per_method[method] = int(len(peaks))
        all_points.extend((int(p), method) for p in peaks)

    confirmed, candidate = _vote_cluster(all_points, fs)
    return confirmed, candidate, per_method


def estimate_qrs_widths_ms(cleaned_signal: np.ndarray, fs: float, r_peaks: np.ndarray) -> List[float]:
    """Ước lượng bề rộng QRS quanh mỗi đỉnh R bằng phương pháp phân định
    (delineation) của NeuroKit2 (method="peak" -> Q/S peak theo từng nhịp).
    Nếu một nhịp không phân định được (thường do nhiễu/nằm sát mép tín hiệu),
    nhịp đó bị bỏ qua khỏi thống kê độ rộng nhưng KHÔNG bị loại khỏi danh sách
    nhịp đã đếm."""
    if nk is None or len(r_peaks) < 2:
        return []
    try:
        _, waves = nk.ecg_delineate(cleaned_signal, r_peaks, sampling_rate=fs, method="peak")
        q_peaks = waves.get("ECG_Q_Peaks", [])
        s_peaks = waves.get("ECG_S_Peaks", [])
        widths = []
        n = min(len(q_peaks), len(s_peaks))
        for i in range(n):
            q, s = q_peaks[i], s_peaks[i]
            if q is None or s is None:
                continue
            if isinstance(q, float) and np.isnan(q):
                continue
            if isinstance(s, float) and np.isnan(s):
                continue
            w = (float(s) - float(q)) / fs * 1000.0
            if 40 <= w <= 200:  # loại bỏ giá trị vô lý về mặt sinh lý
                widths.append(w)
        return widths
    except Exception:
        return []


def analyze_lead(signal_mV: np.ndarray, fs: float, lead_label: str) -> QRSResult:
    peaks, candidates, per_method = detect_qrs_ensemble(signal_mV, fs)
    notes: List[str] = []

    rr_ms = np.diff(peaks) / fs * 1000.0 if len(peaks) > 1 else np.array([])

    hr = hr_min = hr_max = rr_cv = None
    if len(rr_ms) > 0:
        inst_hr = 60000.0 / rr_ms
        hr = float(np.median(inst_hr))
        hr_min = float(np.min(inst_hr))
        hr_max = float(np.max(inst_hr))
        if np.mean(rr_ms) > 0:
            rr_cv = float(np.std(rr_ms) / np.mean(rr_ms))
    else:
        notes.append("Không đủ số nhịp để tính tần số tim / độ đều nhịp.")

    if len(candidates) > 0:
        notes.append(
            f"Có {len(candidates)} vị trí nghi ngờ là nhịp QRS nhưng chỉ 1/4 "
            "thuật toán phát hiện được (chưa đủ đồng thuận) - hiển thị riêng "
            "trên biểu đồ, không tính vào tần số tim, cần xem lại bằng mắt."
        )

    cleaned = nk.ecg_clean(signal_mV, sampling_rate=fs, method="neurokit") if nk else signal_mV
    widths = estimate_qrs_widths_ms(cleaned, fs, peaks) if len(peaks) > 0 else []
    qrs_median = float(np.median(widths)) if widths else None
    if not widths:
        notes.append("Không ước lượng được bề rộng QRS chi tiết (tín hiệu nhiễu hoặc quá ít nhịp).")

    return QRSResult(
        lead_used=lead_label,
        fs=fs,
        r_peaks_idx=peaks,
        r_peaks_time_sec=peaks / fs if len(peaks) else peaks.astype(float),
        candidate_peaks_idx=candidates,
        rr_intervals_ms=rr_ms,
        heart_rate_bpm=hr,
        heart_rate_min_bpm=hr_min,
        heart_rate_max_bpm=hr_max,
        rr_cv=rr_cv,
        qrs_duration_ms_median=qrs_median,
        qrs_duration_ms_list=widths,
        per_method_counts=per_method,
        notes=notes,
    )
