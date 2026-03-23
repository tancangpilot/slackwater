import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import calendar
import numpy as np
import os
import base64

def get_base64_image(image_path):
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode()

# Mã hóa file cờ của bạn
try:
    bin_str = get_base64_image("flagvietnam.png")
    flag_html = f'<img src="data:image/png;base64,{bin_str}" width="25" style="vertical-align: middle; margin-right: 8px;">'
except:
    flag_html = "🇻🇳 " # Dự phòng nếu không tìm thấy file ảnh

st.set_page_config(page_title="Dự án Window Thủy Triều V2.13", layout="wide")
st.title("🌊 Phân Tích Thủy Triều (Bản V2.13)")

tz_vn = timezone(timedelta(hours=7))
now_vn = datetime.now(tz_vn)

# ==========================================
# GIAO DIỆN HEADER (Cùng hàng, tinh gọn)
# ==========================================
DEFAULT_FILE = "HLWVT 2026.xlsx"

col_time, col_upload = st.columns([1.5, 2.5])
with col_time:
    # Căn chỉnh một chút để đồng hồ nằm cân đối với nút uploader bên cạnh
    st.markdown(
        f"""
        <div style='margin-top: 10px; font-size: 16px; padding: 10px; background-color: #e8f4f8; 
        border-radius: 5px; color: #0c5460; border: 1px solid #bee5eb; display: flex; align-items: center;'>
            {flag_html} <b>{now_vn.strftime('%H:%M:%S - %d/%m/%Y')}</b> &nbsp;(+7)
        </div>
        """, 
        unsafe_allow_html=True
    )
    
with col_upload:
    # Ẩn hoàn toàn chữ "Upload Data" đi
    uploaded_file = st.file_uploader("Upload", type=['xlsx', 'xls', 'csv'], label_visibility="collapsed")

file_source = uploaded_file if uploaded_file else (DEFAULT_FILE if os.path.exists(DEFAULT_FILE) else None)

if file_source:
    try:
        is_csv = str(file_source).lower().endswith('.csv') if isinstance(file_source, str) else file_source.name.lower().endswith('.csv')

        has_cl_data = False
        has_cm_data = False

        if is_csv:
            df = pd.read_csv(file_source)
        else:
            xl = pd.ExcelFile(file_source)
            
            # Đọc sheet CL
            if 'CL' in xl.sheet_names:
                has_cl_data = True
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
                
            # Đọc sheet CM
            if 'CM' in xl.sheet_names:
                has_cm_data = True
                df_cm = xl.parse('CM')
                df_cm.columns = df_cm.columns.astype(str).str.strip().str.upper()
                dts_f28cm = []
                for _, r in df_cm.iterrows():
                    try:
                        d = pd.to_datetime(r['DATE'])
                        t = str(r['TIME']).strip()
                        h, m = map(int, t.split(':')[:2])
                        dts_f28cm.append(d + pd.Timedelta(hours=h, minutes=m))
                    except: continue
                df_f28cm = pd.DataFrame({'F28_DT': dts_f28cm}).dropna().sort_values('F28_DT')

            df = xl.parse('HLW-VT')

        df.columns = df.columns.str.strip()
        col_time_orig = 'HL Water'
        col_level = 'Level(m)'
        df[col_level] = pd.to_numeric(df[col_level], errors='coerce')
        df['Parsed_Date'] = pd.to_datetime(df['Date'], errors='coerce').bfill(limit=1).ffill()
        
        base_dts = []
        for _, row in df.iterrows():
            try:
                t = str(row[col_time_orig]).strip()
                h, m = map(int, t.split(':')[:2])
                base_dts.append(row['Parsed_Date'] + pd.Timedelta(hours=h, minutes=m))
            except: base_dts.append(pd.NaT)
        
        df['Event_Datetime'] = base_dts
        df_clean = df.dropna(subset=['Event_Datetime', col_level]).sort_values('Event_Datetime').reset_index(drop=True)
        
        df_clean['Amplitude'] = abs(df_clean[col_level] - df_clean[col_level].shift(1))
        df_clean['Next_Amp'] = abs(df_clean[col_level].shift(-1) - df_clean[col_level])
        df_clean['Ký hiệu'] = np.where(df_clean[col_level] > df_clean[col_level].shift(1), 'HW', 'LW')

        res = []
        for idx, row in df_clean.iterrows():
            hw_lw, level, base_dt = row['Ký hiệu'], row[col_level], row['Event_Datetime']
            amp_val = row['Amplitude'] if pd.notna(row['Amplitude']) else row['Next_Amp']
            
            cl_s, f28_s, diff_s, final_s = "-", "-", "-", "-"
            cm_s, f28cm_s, diff_cm_s, final_cm_s = "-", "-", "-", "-"
            arr_cl, arr_cm = "-", "-"

            if amp_val > 0.4:
                # ==============================
                # THIẾT LẬP HỆ SỐ (TỶ LỆ KIM CƯƠNG)
                # ==============================
                if hw_lw == 'HW':
                    arr_cl, arr_cm = '↙', '↙'
                    delta_cm = 70  # CHỐT: HW + 70 phút
                    if level >= 4.0: delta_cl = 235 
                    elif level >= 3.0: delta_cl = 205 
                    elif level >= 2.0: delta_cl = 195 
                    else: delta_cl = 185 
                else:
                    arr_cl, arr_cm = '↗', '↗'
                    delta_cm = 50  # CHỐT: LW + 50 phút
                    if level >= 1.5: delta_cl = 220 
                    elif level >= 1.0: delta_cl = 225 
                    elif level >= 0.5: delta_cl = 230 
                    else: delta_cl = 235 
                
                # ==============================
                # TÍNH TOÁN CÁT LÁI (CL)
                # ==============================
                cl_dt = base_dt + pd.Timedelta(minutes=delta_cl)
                cl_s = cl_dt.strftime('%H:%M') + (' (+1)' if cl_dt.date() > base_dt.date() else '')
                
                final_cl_dt = cl_dt
                if has_cl_data:
                    t_diffs = (df_f28['F28_DT'] - cl_dt).abs()
                    if t_diffs.min() <= pd.Timedelta(hours=3):
                        best_f28 = df_f28.loc[t_diffs.idxmin(), 'F28_DT']
                        f28_s = best_f28.strftime('%H:%M') + (' (+1)' if best_f28.date() > base_dt.date() else '')
                        
                        d_mins = int((cl_dt - best_f28).total_seconds() / 60)
                        diff_s = f"+{d_mins}" if d_mins > 0 else str(d_mins)
                        
                        early, d_abs = (cl_dt if d_mins < 0 else best_f28), abs(d_mins)
                        if d_abs <= 15: final_cl_dt = early
                        else: final_cl_dt = early + pd.Timedelta(minutes=int(d_abs * 0.35))
                        
                        final_cl_dt = final_cl_dt.replace(minute=(final_cl_dt.minute // 5) * 5)
                final_s = final_cl_dt.strftime('%H:%M') + (' (+1)' if final_cl_dt.date() > base_dt.date() else '')

                # ==============================
                # TÍNH TOÁN CÁT MÉP (CM)
                # ==============================
                cm_dt = base_dt + pd.Timedelta(minutes=delta_cm)
                cm_s = cm_dt.strftime('%H:%M') + (' (+1)' if cm_dt.date() > base_dt.date() else '')
                
                final_cm_dt = cm_dt
                if has_cm_data:
                    t_diffs_cm = (df_f28cm['F28_DT'] - cm_dt).abs()
                    if t_diffs_cm.min() <= pd.Timedelta(hours=3):
                        best_f28cm = df_f28cm.loc[t_diffs_cm.idxmin(), 'F28_DT']
                        f28cm_s = best_f28cm.strftime('%H:%M') + (' (+1)' if best_f28cm.date() > base_dt.date() else '')
                        
                        d_mins_cm = int((cm_dt - best_f28cm).total_seconds() / 60)
                        diff_cm_s = f"+{d_mins_cm}" if d_mins_cm > 0 else str(d_mins_cm)
                        
                        early_cm, d_abs_cm = (cm_dt if d_mins_cm < 0 else best_f28cm), abs(d_mins_cm)
                        if d_abs_cm <= 15: final_cm_dt = early_cm
                        else: final_cm_dt = early_cm + pd.Timedelta(minutes=int(d_abs_cm * 0.35))
                        
                        final_cm_dt = final_cm_dt.replace(minute=(final_cm_dt.minute // 5) * 5)
                final_cm_s = final_cm_dt.strftime('%H:%M') + (' (+1)' if final_cm_dt.date() > base_dt.date() else '')

            res.append([cl_s, f28_s, diff_s, final_s, arr_cl, cm_s, f28cm_s, diff_cm_s, final_cm_s, arr_cm])

        res_df = pd.DataFrame(res, columns=['Slack CL', 'Slack F28CL', 'DiffCLF28', 'SlackCL Final', 'DirCL', 'SlackCM', 'SlackF28CM', 'DiffCMF28', 'SlackCM Final', 'DirCM'])
        df_final = pd.concat([df_clean, res_df], axis=1)

        # ==========================================
        # GIAO DIỆN ĐIỀU KHIỂN & HIỂN THỊ
        # ==========================================
        st.markdown("---")
        
        # Đưa Label và Radio Button lên cùng 1 hàng bằng chia cột
        col_label, col_radio = st.columns([1.2, 8.8])
        with col_label:
            st.markdown("<p style='margin-top: 10px; font-weight: bold; font-size: 16px;'>🔄 Chế độ hiển thị:</p>", unsafe_allow_html=True)
        with col_radio:
            view = st.radio("Chế độ hiển thị", ("Week", "Month"), horizontal=True, label_visibility="collapsed")
        
        if view == "Week":
            sel_d = st.date_input("🗓️ Chọn ngày mốc:", now_vn.date())
            start = pd.Timestamp(sel_d) - pd.Timedelta(days=1)
            end = start + pd.Timedelta(days=6)
        else:
            col_m1, col_m2 = st.columns(2)
            with col_m1: s_month = st.selectbox("📅 Tháng:", list(range(1, 13)), index=now_vn.month-1)
            with col_m2: s_year = st.selectbox("📅 Năm:", [2025, 2026, 2027], index=1)
            start = pd.Timestamp(year=s_year, month=s_month, day=1)
            end = start + pd.offsets.MonthEnd()
        
        f_df = df_final[(df_final['Parsed_Date'] >= start) & (df_final['Parsed_Date'] <= end)].copy()
        
        disp_df = f_df[['Parsed_Date', 'Ký hiệu', col_time_orig, col_level, 'Slack CL', 'Slack F28CL', 'DiffCLF28', 'SlackCL Final', 'DirCL', 'SlackCM', 'SlackF28CM', 'DiffCMF28', 'SlackCM Final', 'DirCM']].copy()
        disp_df.rename(columns={
            'Parsed_Date': 'Date',
            'Ký hiệu': 'HLW Vung Tau',
            col_time_orig: 'Time'
        }, inplace=True)
        
        disp_df['Date'] = disp_df['Date'].dt.strftime('%d/%m/%Y')
        disp_df.loc[disp_df['Date'] == disp_df['Date'].shift(), 'Date'] = ""
        disp_df[col_level] = disp_df[col_level].map('{:.1f}'.format)
        
        all_cols = disp_df.columns.tolist()
        selected_cols = st.multiselect("⚙️ Ẩn/Hiện cột tùy ý:", all_cols, default=all_cols)
        disp_df = disp_df[selected_cols]

        # ==========================================
        # ĐỊNH DẠNG BẢNG
        # ==========================================
        def style_final_table(styler):
            # Tô nền dòng bắt đầu ngày mới
            def highlight_new_day(row):
                if 'Date' in row.index and row['Date'] != "":
                    return ['background-color: #fff8e1; border-top: 1.5px solid #f1c40f;'] * len(row)
                return [''] * len(row)
            
            styler.apply(highlight_new_day, axis=1)

            if 'HLW Vung Tau' in selected_cols:
                styler.map(lambda x: 'color: #007bff; font-weight: bold;' if x == 'HW' else ('color: #dc3545; font-weight: bold;' if x == 'LW' else ''), subset=['HLW Vung Tau'])
            
            final_cols = [col for col in ['SlackCL Final', 'SlackCM Final'] if col in selected_cols]
            if final_cols:
                styler.map(lambda x: 'background-color: #e8f8f5; font-weight: bold; color: #1c2833; font-size: 15px;' if x != "-" else '', subset=final_cols)
            
            dir_cols = [col for col in ['DirCL', 'DirCM'] if col in selected_cols]
            if dir_cols:
                styler.map(lambda x: 'font-weight: bold; color: #007bff; font-size: 22px;' if '↙' in str(x) else ('font-weight: bold; color: #dc3545; font-size: 22px;' if '↗' in str(x) else ''), subset=dir_cols)
            
            return styler

        st.dataframe(style_final_table(disp_df.style), use_container_width=True, hide_index=True, height=600)

    except Exception as e:
        st.error(f"❌ Lỗi hệ thống: {e}")
