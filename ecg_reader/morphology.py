"""
Các phép đo hình thái đơn giản trên toàn bộ 12 chuyển đạo, dùng vị trí đỉnh R
đã phát hiện trên MỘT chuyển đạo tham chiếu (vì 12 chuyển đạo được ghi đồng
thời trên cùng một trục thời gian, nên vị trí nhịp tìm được ở 1 chuyển đạo áp
dụng được cho tất cả các chuyển đạo còn lại).

Đây là các ước lượng THÔ, mục đích sàng lọc nhanh, KHÔNG thay thế phép đo
chính xác trên máy ECG hoặc việc đọc trực tiếp dạng sóng của bác sĩ.
"""

from __future__ import annotations

from typing import Dict

import numpy as np


def peak_to_peak_mV(leads_mV: Dict[str, np.ndarray]) -> Dict[str, float]:
    return {name: float(np.max(sig) - np.min(sig)) for name, sig in leads_mV.items()}


def st_deviation_mV(
    leads_mV: Dict[str, np.ndarray],
    fs: float,
    r_peaks_idx: np.ndarray,
    baseline_offset_ms: float = -80.0,
    st_offset_ms: float = 140.0,
) -> Dict[str, float]:
    """Ước lượng độ lệch đoạn ST cho mỗi chuyển đạo:
    - Điểm nền (baseline): trước đỉnh R `baseline_offset_ms` (nằm trong đoạn PR).
    - Điểm ST: sau đỉnh R `st_offset_ms` (xấp xỉ J + 60ms với QRS trung bình
      ~80ms - đây là quy ước đơn giản hoá, không cá thể hoá theo từng nhịp).
    Kết quả là độ lệch trung vị (median) qua toàn bộ nhịp phát hiện được,
    giúp giảm ảnh hưởng của nhiễu ở một vài nhịp lẻ.
    """
    if r_peaks_idx is None or len(r_peaks_idx) == 0:
        return {name: 0.0 for name in leads_mV}

    base_off = int(round(baseline_offset_ms / 1000.0 * fs))
    st_off = int(round(st_offset_ms / 1000.0 * fs))

    result: Dict[str, float] = {}
    for name, sig in leads_mV.items():
        n = len(sig)
        devs = []
        for r in r_peaks_idx:
            bi = r + base_off
            si = r + st_off
            if 0 <= bi < n and 0 <= si < n:
                devs.append(float(sig[si] - sig[bi]))
        result[name] = float(np.median(devs)) if devs else 0.0
    return result
