import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import calendar
import numpy as np
import os

st.set_page_config(page_title="Dự án Window Thủy Triều V2.11.2", layout="wide")
st.title("🌊 Phân Tích Thủy Triều (Bản V2.11.2)")

tz_vn = timezone(timedelta(hours=7))
now_vn = datetime.now(tz_vn)

st.info(f"🕒 Thời gian hiện tại: **{now_vn.strftime('%H:%M:%S - %d/%m/%Y')}** (Múi giờ +7)")

# ==========================================
# CƠ CHẾ AUTO-LOAD FILE
# ==========================================
DEFAULT_FILE = "HLWVT 2026.xlsx"

uploaded_file = st.file_uploader(f"Tải file Excel mới (Hoặc để hệ thống tự đọc {DEFAULT_FILE})", type=['xlsx', 'xls', 'csv'])

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
                # THIẾT LẬP HỆ SỐ & MŨI TÊN (Đã chuyển về 1 mũi tên)
                # ==============================
                if hw_lw == 'HW':
                    arr_cl, arr_cm = '↙', '↙'
                    delta_cm = 65 # HW + 65 phút
                    if level >= 4.0: delta_cl = 235 
                    elif level >= 3.0: delta_cl = 205 
                    elif level >= 2.0: delta_cl = 195 
                    else: delta_cl = 185 
                else:
                    arr_cl, arr_cm = '↗', '↗'
                    delta_cm = 50 # LW + 50 phút
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

        # Đổi tên cột chuẩn hóa
        res_df = pd.DataFrame(res, columns=['Slack CL', 'Slack F28CL', 'DiffCLF28', 'SlackCL Final', 'DirCL', 'SlackCM', 'SlackF28CM', 'DiffCMF28', 'SlackCM Final', 'DirCM'])
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
        
        # CHUẨN BỊ DATAFRAME VỚI TÊN CỘT MỚI
        disp_df = f_df[['Parsed_Date', 'Ký hiệu', col_time_orig, col_level, 'Slack CL', 'Slack F28CL', 'DiffCLF28', 'SlackCL Final', 'DirCL', 'SlackCM', 'SlackF28CM', 'DiffCMF28', 'SlackCM Final', 'DirCM']].copy()
        disp_df.rename(columns={
            'Parsed_Date': 'Date',
            'Ký hiệu': 'HLW Vung Tau',
            col_time_orig: 'Time'
        }, inplace=True)
        
        disp_df['Date'] = disp_df['Date'].dt.strftime('%d/%m/%Y')
        disp_df.loc[disp_df['Date'] == disp_df['Date'].shift(), 'Date'] = ""
        disp_df[col_level] = disp_df[col_level].map('{:.1f}'.format)
        
        # TÍNH NĂNG ẨN / HIỆN CỘT DỮ LIỆU
        st.markdown("---")
        all_cols = disp_df.columns.tolist()
        selected_cols = st.multiselect("⚙️ Tùy chỉnh hiển thị cột:", all_cols, default=all_cols)
        
        # Lọc DataFrame theo cột đã chọn
        disp_df = disp_df[selected_cols]      

        # Định dạng bảng thông minh
        def style_final_table(styler):
            # 1. Đổ nền vàng nhạt cho dòng khởi đầu ngày mới (khi cột Date có chữ)
            def highlight_new_day(row):
                if 'Date' in row.index and row['Date'] != "":
                    # Màu vàng nhạt nhẹ nhàng, không chói mắt
                    return ['background-color: #fff8e1; border-top: 1.5px solid #f1c40f;'] * len(row)
                return [''] * len(row)
            
            styler.apply(highlight_new_day, axis=1)

            # 2. Định dạng chữ HW/LW
            if 'HLW Vung Tau' in selected_cols:
                styler.map(lambda x: 'color: #007bff; font-weight: bold;' if x == 'HW' else ('color: #dc3545; font-weight: bold;' if x == 'LW' else ''), subset=['HLW Vung Tau'])
            
            # 3. Định dạng Cột Final (Tô nền xanh mint - đè lên nền vàng)
            final_cols = [col for col in ['SlackCL Final', 'SlackCM Final'] if col in selected_cols]
            if final_cols:
                styler.map(lambda x: 'background-color: #e8f8f5; font-weight: bold; color: #1c2833; font-size: 15px;' if x != "-" else '', subset=final_cols)
            
            # 4. Định dạng Mũi tên đơn cỡ lớn (DirCL, DirCM)
            dir_cols = [col for col in ['DirCL', 'DirCM'] if col in selected_cols]
            if dir_cols:
                # Tăng font-size lên 22px để mũi tên dài và to hơn, đồng thời bỏ letter-spacing
                styler.map(lambda x: 'font-weight: bold; color: #007bff; font-size: 22px;' if '↙' in str(x) else ('font-weight: bold; color: #dc3545; font-size: 22px;' if '↗' in str(x) else ''), subset=dir_cols)
            
            return styler

        st.dataframe(style_final_table(disp_df.style), use_container_width=True, hide_index=True, height=600)

    except Exception as e:
        st.error(f"❌ Lỗi hệ thống: {e}")
