"""
Giao diện demo - Công cụ đọc & sàng lọc nhanh điện tâm đồ (PDF/XML)
Chạy: streamlit run app.py
"""

from __future__ import annotations

import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

sys.path.insert(0, str(Path(__file__).parent))
warnings.filterwarnings("ignore")

from ecg_reader import read_ecg_file, analyze_record  # noqa: E402
from ecg_reader.common import STANDARD_LEAD_ORDER  # noqa: E402

st.set_page_config(page_title="Sàng lọc ECG nhanh - Demo", layout="wide")

LEVEL_COLOR = {"nguy_co_cao": "#c0392b", "canh_bao": "#e67e22", "info": "#2980b9"}
LEVEL_LABEL = {"nguy_co_cao": "NGUY CƠ CAO", "canh_bao": "CẢNH BÁO", "info": "THÔNG TIN"}


def fmt(v, unit="", nd=0):
    if v is None:
        return "—"
    try:
        if np.isnan(v):
            return "—"
    except TypeError:
        pass
    return f"{v:.{nd}f}{unit}"


def render_disclaimer():
    st.markdown(
        """
> ⚠️ **CHỈ DÙNG ĐỂ DEMO / SÀNG LỌC BƯỚC ĐẦU.**
> Đây KHÔNG phải thiết bị chẩn đoán y tế, chưa qua kiểm định lâm sàng.
> Công cụ được thiết kế thiên về **báo động dư (thà nhầm còn hơn bỏ sót)** -
> mọi cờ cảnh báo đều cần **bác sĩ xem lại dạng sóng gốc** trước khi kết luận.
> Không dùng để tự chẩn đoán hoặc ra quyết định điều trị.
        """
    )


def render_metadata(rec):
    cols = st.columns(5)
    cols[0].metric("Bệnh viện", rec.facility_name or "—")
    cols[1].metric("Khoa/Viện", rec.department_name or "—")
    cols[2].metric("Giới tính", rec.patient_sex or "—")
    cols[3].metric("Tuổi", rec.patient_age or "—")
    cols[4].metric("Thời gian ghi", rec.acquisition_datetime or "—")

    quality = rec.signal_quality
    if quality == "digital_native":
        st.success("Nguồn dữ liệu: **tín hiệu số gốc (XML)** - độ tin cậy cao, đủ 12 chuyển đạo đồng bộ thời gian.")
    else:
        st.warning(
            "Nguồn dữ liệu: **số hoá lại từ nét vẽ PDF** - độ tin cậy THẤP HƠN file XML "
            "(xem phần 'Độ tin cậy' trong tài liệu kỹ thuật). Nên dùng file XML nếu có."
        )
    for w in rec.warnings:
        st.info(f"ℹ️ {w}")


def render_summary(rep):
    n_high = sum(1 for f in rep.flags if f.level == "nguy_co_cao")
    n_warn = sum(1 for f in rep.flags if f.level == "canh_bao")
    if n_high:
        st.error(f"🔴 {rep.summary_text}")
    elif n_warn:
        st.warning(f"🟠 {rep.summary_text}")
    else:
        st.success(f"🟢 {rep.summary_text}")

    if rep.record.device_severity:
        st.caption(f"Kết luận sẵn có từ máy ghi ECG (để đối chiếu, KHÔNG do công cụ này tính): "
                   f"**{rep.record.device_severity}**")


def render_measurements(rep):
    rec = rep.record
    dm = rec.device_measurements
    rows = [
        ("Tần số tim (bpm)", fmt(rep.qrs.heart_rate_bpm), fmt(dm.get("HR_bpm"))),
        ("Số nhịp QRS xác nhận / khả nghi",
         f"{len(rep.qrs.r_peaks_idx)} / {len(rep.qrs.candidate_peaks_idx)}", "—"),
        ("Độ đều nhịp (hệ số biến thiên RR)", fmt(rep.qrs.rr_cv, nd=2), "—"),
        ("Bề rộng QRS ước tính (ms)", fmt(rep.qrs.qrs_duration_ms_median), fmt(dm.get("QRSd_ms"))),
        ("PR (ms, theo máy)", "—", fmt(dm.get("PR_ms"))),
        ("QT (ms, theo máy)", "—", fmt(dm.get("QT_ms"))),
        ("QTc Bazett (ms, theo máy)", "—", fmt(dm.get("QTcB_ms"))),
        ("Trục QRS (độ, theo máy)", "—", fmt(dm.get("QRS_axis_deg"))),
    ]
    st.table(
        {"Thông số": [r[0] for r in rows],
         "Công cụ tự tính": [r[1] for r in rows],
         "Máy ghi ECG báo cáo": [r[2] for r in rows]}
    )
    st.caption(
        "Thông số 'Máy ghi ECG báo cáo' được trích trực tiếp từ file gốc (không phải do công cụ "
        "này tính) - dùng để đối chiếu nhanh. Một số thông số (PR, QT, trục điện tim) hiện công cụ "
        "chưa tự tính mà chỉ hiển thị lại số liệu của máy."
    )


def render_flags(rep):
    if not rep.flags:
        st.write("Không có cờ cảnh báo nào theo bộ quy tắc hiện tại.")
        return
    for f in sorted(rep.flags, key=lambda x: 0 if x.level == "nguy_co_cao" else 1):
        color = LEVEL_COLOR.get(f.level, "#888")
        st.markdown(
            f"<div style='border-left:5px solid {color}; padding:8px 12px; margin-bottom:8px; "
            f"background:rgba(128,128,128,0.07)'>"
            f"<b style='color:{color}'>[{LEVEL_LABEL.get(f.level,f.level)}] {f.message}</b>"
            f"<br><span style='font-size:0.9em'>{f.detail}</span></div>",
            unsafe_allow_html=True,
        )


def _plot_lead(fig, row, col, t, sig, peaks_idx=None, cand_idx=None, fs=500.0, title=""):
    fig.add_trace(go.Scatter(x=t, y=sig, mode="lines", line=dict(width=1, color="#1f77b4"),
                              showlegend=False), row=row, col=col)
    if peaks_idx is not None and len(peaks_idx):
        fig.add_trace(go.Scatter(x=peaks_idx / fs, y=sig[peaks_idx], mode="markers",
                                  marker=dict(color="red", size=6, symbol="circle"),
                                  name="Nhịp xác nhận", showlegend=False),
                      row=row, col=col)
    if cand_idx is not None and len(cand_idx):
        valid = cand_idx[cand_idx < len(sig)]
        if len(valid):
            fig.add_trace(go.Scatter(x=valid / fs, y=sig[valid], mode="markers",
                                      marker=dict(color="orange", size=7, symbol="diamond-open"),
                                      name="Nhịp khả nghi", showlegend=False),
                          row=row, col=col)
    fig.update_yaxes(title_text=title, row=row, col=col)


def render_waveforms(rec, rep):
    st.subheader("Dạng sóng 12 chuyển đạo")
    if rec.signal_quality == "digital_native":
        leads = rec.ordered_leads()
        n = len(leads)
        rows, cols = (n + 1) // 2, 2
        fig = make_subplots(rows=rows, cols=cols, shared_xaxes=False,
                             subplot_titles=[l.label for l in leads])
        for i, lead in enumerate(leads):
            r, c = i // cols + 1, i % cols + 1
            t = np.arange(len(lead.samples_mV)) / lead.fs
            peaks = rep.qrs.r_peaks_idx if lead.label == rep.reference_lead else None
            cands = rep.qrs.candidate_peaks_idx if lead.label == rep.reference_lead else None
            _plot_lead(fig, r, c, t, lead.samples_mV, peaks, cands, lead.fs, lead.label)
        fig.update_layout(height=220 * rows, margin=dict(t=40, b=10))
        st.plotly_chart(fig, width='stretch')
        st.caption("Chấm đỏ = nhịp QRS đã được >= 2/4 thuật toán đồng thuận xác nhận (chỉ đánh dấu "
                   f"trên chuyển đạo tham chiếu **{rep.reference_lead}**, dùng để tính các thông số). "
                   "Chấm cam (◇) = vị trí khả nghi nhưng chưa đủ đồng thuận - cần xem thêm.")
    else:
        st.markdown("**Dải nhịp (rhythm strip) - dùng để tính tần số tim / độ đều nhịp:**")
        for label, lead in rec.leads.items():
            fig = make_subplots(rows=1, cols=1)
            t = np.arange(len(lead.samples_mV)) / lead.fs
            _plot_lead(fig, 1, 1, t, lead.samples_mV, rep.qrs.r_peaks_idx, rep.qrs.candidate_peaks_idx,
                       lead.fs, label)
            fig.update_layout(height=250, margin=dict(t=20, b=10))
            st.plotly_chart(fig, width='stretch')

        if rec.snapshot_leads:
            st.markdown(
                "**12 chuyển đạo trích từ lưới in (mỗi đoạn ~2.5 giây, KHÔNG cùng trục thời gian "
                "với nhau và với dải nhịp ở trên - chỉ dùng để xem hình thái từng chuyển đạo):**"
            )
            leads_sorted = [rec.snapshot_leads[n] for n in STANDARD_LEAD_ORDER if n in rec.snapshot_leads]
            rows, cols = (len(leads_sorted) + 3) // 4, 4
            fig = make_subplots(rows=rows, cols=cols, subplot_titles=[l.label for l in leads_sorted])
            for i, lead in enumerate(leads_sorted):
                r, c = i // cols + 1, i % cols + 1
                t = np.arange(len(lead.samples_mV)) / lead.fs
                _plot_lead(fig, r, c, t, lead.samples_mV, None, None, lead.fs, lead.label)
            fig.update_layout(height=180 * rows, margin=dict(t=30, b=10))
            st.plotly_chart(fig, width='stretch')


def process_file(uploaded_file):
    suffix = Path(uploaded_file.name).suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded_file.getbuffer())
        tmp_path = tmp.name
    rec = read_ecg_file(tmp_path)
    rep = analyze_record(rec)
    return rec, rep


def check_password() -> bool:
    """Màn hình đăng nhập bằng mật khẩu chung, đọc từ st.secrets['app_password'].
    Chặn truy cập vào toàn bộ ứng dụng cho tới khi nhập đúng mật khẩu."""
    if st.session_state.get("authenticated"):
        return True

    st.title("🫀 Sàng lọc ECG - Đăng nhập")
    password = st.text_input("Mật khẩu truy cập", type="password")
    if st.button("Đăng nhập") or password:
        expected = st.secrets.get("app_password")
        if not expected:
            st.error("Chưa cấu hình mật khẩu (app_password) trong Streamlit Secrets.")
            return False
        if password == expected:
            st.session_state["authenticated"] = True
            st.rerun()
        elif password:
            st.error("Sai mật khẩu.")
    return False


def main():
    if not check_password():
        return

    st.title("🫀 Công cụ đọc & sàng lọc nhanh điện tâm đồ (PDF / XML)")
    st.caption("Bản demo kỹ thuật - BV Bạch Mai · Viện Tim mạch")
    render_disclaimer()

    uploaded_files = st.file_uploader(
        "Tải lên file ECG (.xml hoặc .pdf) - có thể chọn nhiều file cùng lúc",
        type=["xml", "pdf"], accept_multiple_files=True,
    )

    if not uploaded_files:
        st.info("Chưa có file nào được tải lên. Nếu có cả file .xml lẫn .pdf của cùng một bản ghi, "
                 "nên ưu tiên tải file .xml (độ chính xác cao hơn).")
        return

    tabs = st.tabs([f.name for f in uploaded_files])
    for tab, uf in zip(tabs, uploaded_files):
        with tab:
            try:
                with st.spinner("Đang đọc & phân tích..."):
                    rec, rep = process_file(uf)
            except Exception as e:
                st.error(f"Không xử lý được file này: {type(e).__name__}: {e}")
                continue

            render_metadata(rec)
            st.divider()
            render_summary(rep)
            st.divider()
            col_a, col_b = st.columns([1, 1])
            with col_a:
                st.subheader("Các cờ sàng lọc")
                render_flags(rep)
            with col_b:
                st.subheader("Thông số đo được")
                render_measurements(rep)
            st.divider()
            render_waveforms(rec, rep)


if __name__ == "__main__":
    main()
