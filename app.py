import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import calendar
import numpy as np
import os

st.set_page_config(page_title="Dự án Window Thủy Triều V2.7 No Chart", layout="wide")
st.title("🌊 Ứng Dụng Phân Tích Thủy Triều (Bản V2.7 - Tối ưu Thực chiến)")

tz_vn = timezone(timedelta(hours=7))
now_vn = datetime.now(tz_vn)

st.info(f"🕒 Thời gian hiện tại: **{now_vn.strftime('%H:%M:%S - %d/%m/%Y')}** (Múi giờ +7)")

# ==========================================
# CƠ CHẾ AUTO-LOAD FILE (V2.4)
# ==========================================
DEFAULT_FILE = "HLWVT 2026.xlsx"

uploaded_file = st.file_uploader(f"Tải file Excel mới (Hoặc để hệ thống tự đọc {DEFAULT_FILE})", type=['xlsx', 'xls', 'csv'])

file_source = uploaded_file if uploaded_file else (DEFAULT_FILE if os.path.exists(DEFAULT_FILE) else None)

if file_source:
    try:
        if isinstance(file_source, str):
            is_csv = file_source.lower().endswith('.csv')
        else:
            is_csv = file_source.name.lower().endswith('.csv')

        if is_csv:
            df = pd.read_csv(file_source)
            has_cl_data = False
        else:
            xl = pd.ExcelFile(file_source)
            has_cl_data = 'CL' in xl.sheet_names
            if has_cl_data:
                df_cl = xl.parse('CL')
                df_cl.columns = df_cl.columns.astype(str).str.strip().str.upper()
                dts_f28 = []
                for _, r in df_cl.iterrows():
                    try:
                        d = pd.to_datetime(r['DATE'])
                        t = str(r['TIME']).strip()
                        h, m = map(int, t.split(':')[:2])
                        dts_f28.append(d + pd.Timedelta(hours=h, minutes=m))
                    except: continue
                df_f28 = pd.DataFrame({'F28_DT': dts_f28}).dropna().sort_values('F28_DT')
            df = xl.parse('HLW-VT')

        df.columns = df.columns.str.strip()
        col_level = 'Level(m)'
        df[col_level] = pd.to_numeric(df[col_level], errors='coerce')
        df['Parsed_Date'] = pd.to_datetime(df['Date'], errors='coerce').bfill(limit=1).ffill()
        
        base_dts = []
        for _, row in df.iterrows():
            try:
                t = str(row['HL Water']).strip()
                h, m = map(int, t.split(':')[:2])
                base_dts.append(row['Parsed_Date'] + pd.Timedelta(hours=h, minutes=m))
            except: base_dts.append(pd.NaT)
        
        df['Event_Datetime'] = base_dts
        df_clean = df.dropna(subset=['Event_Datetime', col_level]).sort_values('Event_Datetime').reset_index(drop=True)
        
        # Tính biên độ
        df_clean['Amplitude'] = abs(df_clean[col_level] - df_clean[col_level].shift(1))
        df_clean['Next_Amp'] = abs(df_clean[col_level].shift(-1) - df_clean[col_level])
        df_clean['Ký hiệu'] = np.where(df_clean[col_level] > df_clean[col_level].shift(1), 'HW', 'LW')

        res = []
        for idx, row in df_clean.iterrows():
            hw_lw, level, base_dt = row['Ký hiệu'], row[col_level], row['Event_Datetime']
            amp_val = row['Amplitude'] if pd.notna(row['Amplitude']) else row['Next_Amp']
            
            cl_s, f28_s, diff_s, final_s, arr = "-", "-", "-", "-", "-"

            # --- CHỈ TÍNH NẾU BIÊN ĐỘ > 0.4 ---
            if amp_val > 0.4:
                if hw_lw == 'HW':
                    arr = '↙'
                    if level >= 4.0: delta = 235 # 3h55
                    elif level >= 3.0: delta = 205 # 3h25
                    elif level >= 2.0: delta = 195 # 3h15
                    else: delta = 185 # 3h05
                else:
                    arr = '↗'
                    if level >= 1.5: delta = 220 # 3h40
                    elif level >= 1.0: delta = 225 # 3h45
                    elif level >= 0.5: delta = 230 # 3h50
                    else: delta = 235 # 3h55
                
                cl_dt = base_dt + pd.Timedelta(minutes=delta)
                cl_dt = cl_dt.replace(minute=(cl_dt.minute // 5) * 5)
                cl_s = cl_dt.strftime('%H:%M') + (' (+1)' if cl_dt.date() > base_dt.date() else '')
                
                final_dt = cl_dt
                if has_cl_data:
                    t_diffs = (df_f28['F28_DT'] - cl_dt).abs()
                    if t_diffs.min() <= pd.Timedelta(hours=3):
                        best_f28 = df_f28.loc[t_diffs.idxmin(), 'F28_DT']
                        f28_s = best_f28.strftime('%H:%M') + (' (+1)' if best_f28.date() > base_dt.date() else '')
                        
                        d_mins = int((cl_dt - best_f28).total_seconds() / 60)
                        diff_s = f"+{d_mins}" if d_mins > 0 else str(d_mins)
                        
                        # LOGIC FINAL CHỐT (35%)
                        early, d_abs = (cl_dt if d_mins < 0 else best_f28), abs(d_mins)
                        if d_abs <= 10: final_dt = early
                        elif d_abs <= 15: final_dt = early + pd.Timedelta(minutes=5)
                        elif d_abs <= 35: final_dt = early + pd.Timedelta(minutes=d_abs//2)
                        else: final_dt = early + pd.Timedelta(minutes=int(d_abs * 0.35))
                        
                        final_dt = final_dt.replace(minute=(final_dt.minute // 5) * 5)
                
                final_s = final_dt.strftime('%H:%M') + (' (+1)' if final_dt.date() > base_dt.date() else '')

            res.append([cl_s, f28_s, diff_s, final_s, arr])

        res_df = pd.DataFrame(res, columns=['Slack CL', 'Slack F28', 'Diff', 'SLACK FINAL', 'Dòng'])
        df_final = pd.concat([df_clean, res_df], axis=1)

        # GIAO DIỆN HIỂN THỊ
        view = st.radio("🔄 Chế độ hiển thị:", ("Chế độ 7 Ngày", "Chế độ xem theo Tháng"), horizontal=True)
        if view == "Chế độ 7 Ngày":
            sel_d = st.date_input("🗓️ Chọn ngày mốc:", now_vn.date())
            start = pd.Timestamp(sel_d) - pd.Timedelta(days=1)
            end = start + pd.Timedelta(days=6)
        else:
            col1, col2 = st.columns(2)
            with col1: s_month = st.selectbox("📅 Tháng:", list(range(1, 13)), index=now_vn.month-1)
            with col2: s_year = st.selectbox("📅 Năm:", [2025, 2026, 2027], index=1)
            start = pd.Timestamp(year=s_year, month=s_month, day=1)
            end = start + pd.offsets.MonthEnd()
        
        f_df = df_final[(df_final['Parsed_Date'] >= start) & (df_final['Parsed_Date'] <= end)].copy()
        f_df['Ngày'] = f_df['Parsed_Date'].dt.strftime('%d/%m/%Y')
        f_df.loc[f_df['Ngày'] == f_df['Ngày'].shift(), 'Ngày'] = ""
        
        # --- ĐỊNH DẠNG SỐ THẬP PHÂN CHO LEVEL(M) ---
        f_df[col_level] = f_df[col_level].map('{:.1f}'.format)
        
        st.info("💡 **Giải thích:** Cột SLACK FINAL được chốt dựa trên quy tắc an toàn thực chiến (Ưu tiên giờ sớm & làm tròn lùi 5p). Nếu biên độ ≤ 0.4m, hệ thống ghi '-' (nước đi ngang).")

        # Định dạng bảng
        def style_final_table(styler):
            styler.map(lambda x: 'color: #007bff; font-weight: bold;' if x == 'HW' else ('color: #dc3545; font-weight: bold;' if x == 'LW' else ''), subset=['Ký hiệu'])
            styler.map(lambda x: 'background-color: #e8f8f5; font-weight: bold; color: #1c2833; font-size: 15px;' if x != "-" else '', subset=['SLACK FINAL'])
            styler.map(lambda x: 'font-weight: bold; color: #007bff;' if x == '↙' else ('font-weight: bold; color: #dc3545;' if x == '↗' else ''), subset=['Dòng'])
            return styler

        st.dataframe(style_final_table(f_df[['Ngày', 'Ký hiệu', 'HL Water', col_level, 'Slack CL', 'Slack F28', 'Diff', 'SLACK FINAL', 'Dòng']].style), use_container_width=True, hide_index=True, height=550)

    except Exception as e:
        st.error(f"❌ Lỗi hệ thống: {e}")
