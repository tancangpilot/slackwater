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

try:
    bin_str = get_base64_image("flagvietnam.png")
    flag_html = f'<img src="data:image/png;base64,{bin_str}" width="25" style="vertical-align: middle; margin-right: 8px;">'
except:
    flag_html = "🇻🇳 " 

st.set_page_config(page_title="Dự án Window Thủy Triều V2.24", layout="wide")
st.title("🌊 Phân Tích Thủy Triều (Bản V2.24 - UI Chuỗi Tiếp Sức)")

tz_vn = timezone(timedelta(hours=7))
now_vn = datetime.now(tz_vn)

# ==========================================
# GIAO DIỆN HEADER
# ==========================================
DEFAULT_FILE = "HLWVT 2026.xlsx"

col_time, col_upload = st.columns([1.5, 2.5])
with col_time:
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
            
            if 'CL' in xl.sheet_names:
                has_cl_data = True
                df_cl = xl.parse('CL')
                df_cl.columns = df_cl.columns.astype(str).str.strip().str.upper()
                df_cl = df_cl.dropna(subset=['TIME']).copy() 
                df_cl['DATE'] = df_cl['DATE'].ffill()
                
                dts_f28 = []
                for _, r in df_cl.iterrows():
                    try:
                        d = pd.to_datetime(r['DATE'])
                        t = str(r['TIME']).strip()
                        h, m = map(int, t.split(':')[:2])
                        dts_f28.append(d + pd.Timedelta(hours=h, minutes=m))
                    except: continue
                df_f28 = pd.DataFrame({'F28_DT': dts_f28}).dropna().sort_values('F28_DT')
                
            if 'CM' in xl.sheet_names:
                has_cm_data = True
                df_cm = xl.parse('CM')
                df_cm.columns = df_cm.columns.astype(str).str.strip().str.upper()
                df_cm = df_cm.dropna(subset=['TIME']).copy()
                df_cm['DATE'] = df_cm['DATE'].ffill()
                
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
        df = df.dropna(subset=[col_time_orig, col_level]).copy()
        
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

        valid_indices = []
        for idx, row in df_clean.iterrows():
            amp_val = row['Amplitude'] if pd.notna(row['Amplitude']) else row['Next_Amp']
            if amp_val > 0.4:
                valid_indices.append(idx)
        df_calc = df_clean.loc[valid_indices].copy().reset_index(drop=True)

        res_cl, res_cm = [], []
        final_cl_dts, final_cm_dts = [], []
        
        # BƯỚC 1: TÍNH SLACK FINAL CHO TOÀN BỘ DATA
        for idx, row in df_calc.iterrows():
            hw_lw, level, base_dt = row['Ký hiệu'], row[col_level], row['Event_Datetime']
            
            if hw_lw == 'HW':
                arr = '↙'
                delta_cm = 65 
                if level >= 4.0: delta_cl = 235 
                elif level >= 3.0: delta_cl = 205 
                elif level >= 2.0: delta_cl = 195 
                else: delta_cl = 185 
            else:
                arr = '↗'
                delta_cm = 50 
                if level >= 1.5: delta_cl = 220 
                elif level >= 1.0: delta_cl = 225 
                elif level >= 0.5: delta_cl = 230 
                else: delta_cl = 235 
            
            # Tính CL
            cl_dt = base_dt + pd.Timedelta(minutes=delta_cl)
            cl_s = cl_dt.strftime('%H:%M') + (' (+1)' if cl_dt.date() > base_dt.date() else '')
            final_cl_dt = cl_dt
            f28_s, diff_s = "-", "-"
            
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
            final_cl_dts.append(final_cl_dt)
            res_cl.append([cl_s, f28_s, diff_s, final_s, arr])

            # Tính CM
            cm_dt = base_dt + pd.Timedelta(minutes=delta_cm)
            cm_s = cm_dt.strftime('%H:%M') + (' (+1)' if cm_dt.date() > base_dt.date() else '')
            final_cm_dt = cm_dt
            f28cm_s, diff_cm_s = "-", "-"
            
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
            final_cm_dts.append(final_cm_dt)
            res_cm.append([cm_s, f28cm_s, diff_cm_s, final_cm_s, arr])

        df_calc['SlackCL_DT'] = final_cl_dts
        df_calc['SlackCM_DT'] = final_cm_dts

        # ==========================================
        # MA TRẬN 20 Ô (DYNAMIC TARGET KNOTS CHO CÁT LÁI)
        # ==========================================
        def get_dynamic_knot(amp, dt_mins, is_before):
            if amp <= 0.8:
                if dt_mins <= 270:     return 1.0 if is_before else 0.8
                elif dt_mins <= 355:   return 1.2 if is_before else 1.0
                else:                  return 999.0
            elif amp <= 1.2:
                if dt_mins <= 270:     return 0.8 if is_before else 0.6
                elif dt_mins <= 355:   return 1.5 if is_before else 1.2
                elif dt_mins <= 390:   return 2.0 if is_before else 1.5
                else:                  return 999.0
            elif amp <= 2.0:
                if dt_mins <= 270:     return 0.6 if is_before else 0.45
                elif dt_mins <= 355:   return 1.5 if is_before else 1.2
                elif dt_mins <= 390:   return 2.0 if is_before else 1.5
                elif dt_mins <= 480:   return 2.0 if is_before else 1.5
                else:                  return 2.5 if is_before else 1.5
            else:
                if dt_mins <= 270:     return 0.4 if is_before else 0.3
                elif dt_mins <= 355:   return 1.0 if is_before else 0.8
                elif dt_mins <= 390:   return 1.5 if is_before else 1.2
                elif dt_mins <= 480:   return 2.0 if is_before else 1.5
                else:                  return 2.5 if is_before else 1.5

        # ==========================================
        # BƯỚC 2: THUẬT TOÁN NỘI SUY (TRẢ VỀ DATETIME)
        # ==========================================
        def calc_window_dt(t_slack, boundary_slack, th_mins, amp, target_knot, is_before):
            if pd.isna(t_slack) or pd.isna(th_mins) or pd.isna(amp) or th_mins <= 0 or amp <= 0: return None
            
            speeds = [0, (1/12 * amp) / 0.2, (2/12 * amp) / 0.2, (3/12 * amp) / 0.2] 
            
            if target_knot > speeds[-1]: 
                return boundary_slack.round('5min')
            else:
                for k in range(1, 4):
                    if speeds[k-1] <= target_knot <= speeds[k]:
                        frac = 0 if speeds[k] == speeds[k-1] else (target_knot - speeds[k-1]) / (speeds[k] - speeds[k-1])
                        delta_mins = (k - 1 + frac) * th_mins
                        
                        res_time = t_slack - pd.Timedelta(minutes=delta_mins) if is_before else t_slack + pd.Timedelta(minutes=delta_mins)
                        return res_time.round('5min')
            return None

        def format_dt(dt_val, ref_dt):
            if pd.isna(dt_val) or dt_val is None: return "-"
            time_str = dt_val.strftime('%H:%M')
            if dt_val.date() > ref_dt.date(): time_str += ' (+1)'
            elif dt_val.date() < ref_dt.date(): time_str += ' (-1)'
            return time_str

        raw_b_cl, raw_e_cl = [], []
        raw_b_cm, raw_e_cm = [], []
        
        for i in range(len(df_calc)):
            # Tính Cát Lái
            if i > 0:
                boundary_prev = df_calc['SlackCL_DT'][i-1]
                dur_bef = (df_calc['SlackCL_DT'][i] - boundary_prev).total_seconds() / 60
                amp_bef = abs(df_calc[col_level][i] - df_calc[col_level][i-1])
                target_b_cl = get_dynamic_knot(amp_bef, dur_bef, True)
                raw_b_cl.append(calc_window_dt(df_calc['SlackCL_DT'][i], boundary_prev, dur_bef/6, amp_bef, target_b_cl, True))
            else: raw_b_cl.append(None)
            
            if i < len(df_calc) - 1:
                boundary_next = df_calc['SlackCL_DT'][i+1]
                dur_aft = (boundary_next - df_calc['SlackCL_DT'][i]).total_seconds() / 60
                amp_aft = abs(df_calc[col_level][i+1] - df_calc[col_level][i])
                target_e_cl = get_dynamic_knot(amp_aft, dur_aft, False)
                raw_e_cl.append(calc_window_dt(df_calc['SlackCL_DT'][i], boundary_next, dur_aft/6, amp_aft, target_e_cl, False))
            else: raw_e_cl.append(None)
            
            # Tính Cái Mép
            if i > 0:
                boundary_prev = df_calc['SlackCM_DT'][i-1]
                dur_bef = (df_calc['SlackCM_DT'][i] - boundary_prev).total_seconds() / 60
                amp_bef = abs(df_calc[col_level][i] - df_calc[col_level][i-1])
                raw_b_cm.append(calc_window_dt(df_calc['SlackCM_DT'][i], boundary_prev, dur_bef/6, amp_bef, 1.0, True))
            else: raw_b_cm.append(None)
            
            if i < len(df_calc) - 1:
                boundary_next = df_calc['SlackCM_DT'][i+1]
                dur_aft = (boundary_next - df_calc['SlackCM_DT'][i]).total_seconds() / 60
                amp_aft = abs(df_calc[col_level][i+1] - df_calc[col_level][i])
                raw_e_cm.append(calc_window_dt(df_calc['SlackCM_DT'][i], boundary_next, dur_aft/6, amp_aft, 0.8, False))
            else: raw_e_cm.append(None)

        # ==========================================
        # BƯỚC 3: XỬ LÝ NỐI CHUỖI LIỀN MẠCH (RELAY RACE)
        # ==========================================
        b_cl, e_cl = [], []
        b_cm, e_cm = [], []
        
        for i in range(len(df_calc)):
            # Cát Lái
            b_cl_val = raw_b_cl[i]
            if i > 0 and b_cl_val is not None and raw_e_cl[i-1] is not None:
                if b_cl_val < raw_e_cl[i-1]:  
                    b_cl_val = raw_e_cl[i-1]  
            b_cl.append(format_dt(b_cl_val, df_calc['SlackCL_DT'][i]))
            e_cl.append(format_dt(raw_e_cl[i], df_calc['SlackCL_DT'][i]))

            # Cái Mép
            b_cm_val = raw_b_cm[i]
            if i > 0 and b_cm_val is not None and raw_e_cm[i-1] is not None:
                if b_cm_val < raw_e_cm[i-1]:
                    b_cm_val = raw_e_cm[i-1]
            b_cm.append(format_dt(b_cm_val, df_calc['SlackCM_DT'][i]))
            e_cm.append(format_dt(raw_e_cm[i], df_calc['SlackCM_DT'][i]))

        cl_df = pd.DataFrame(res_cl, columns=['Slack CL', 'Slack F28CL', 'DiffCLF28', 'SlackCL Final', 'Dir'])
        cl_df['Begin Window'] = b_cl
        cl_df['End Window'] = e_cl
        
        cm_df = pd.DataFrame(res_cm, columns=['Slack CM', 'Slack F28CM', 'DiffCMF28', 'SlackCM Final', 'Dir'])
        cm_df['Begin Window'] = b_cm
        cm_df['End Window'] = e_cm

        df_cl_full = pd.concat([df_calc[['Parsed_Date', 'Ký hiệu', col_time_orig, col_level]], cl_df], axis=1)
        df_cm_full = pd.concat([df_calc[['Parsed_Date', 'Ký hiệu', col_time_orig, col_level]], cm_df], axis=1)

        # ==========================================
        # GIAO DIỆN ĐIỀU KHIỂN
        # ==========================================
        st.markdown("---")
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
        
        def style_tab_table(styler, sel_cols, is_cl):
            def highlight_new_day(row):
                if 'Date' in row.index and row['Date'] != "":
                    return ['background-color: #fff8e1; border-top: 1.5px solid #f1c40f;'] * len(row)
                return [''] * len(row)
            styler.apply(highlight_new_day, axis=1)

            if 'HLW Vung Tau' in sel_cols:
                styler.map(lambda x: 'color: #007bff; font-weight: bold;' if x == 'HW' else ('color: #dc3545; font-weight: bold;' if x == 'LW' else ''), subset=['HLW Vung Tau'])
            
            final_col = 'SlackCL Final' if is_cl else 'SlackCM Final'
            if final_col in sel_cols:
                styler.map(lambda x: 'background-color: #e8f8f5; font-weight: bold; color: #1c2833; font-size: 15px;' if x != "-" else '', subset=[final_col])
            
            if 'Dir' in sel_cols:
                styler.map(lambda x: 'font-weight: bold; color: #007bff; font-size: 22px;' if '↙' in str(x) else ('font-weight: bold; color: #dc3545; font-size: 22px;' if '↗' in str(x) else ''), subset=['Dir'])
            
            # ==========================================
            # BỘ LỌC ĐỔI MÀU "CHUỖI TIẾP SỨC"
            # ==========================================
            def highlight_relay(data):
                css = pd.DataFrame('', index=data.index, columns=data.columns)
                
                # Màu Cam mặc định cho các cửa sổ độc lập
                win_cols = [c for c in ['Begin Window', 'End Window'] if c in data.columns]
                for c in win_cols:
                    css[c] = np.where(data[c] != "-", 'background-color: #fdf2e9; font-weight: bold; color: #d35400;', '')
                
                # Màu Xanh Lục Bảo cho các cặp nối tiếp
                if 'Begin Window' in data.columns and 'End Window' in data.columns:
                    indices = data.index.tolist()
                    for i in range(1, len(indices)):
                        idx_prev = indices[i-1]
                        idx_curr = indices[i]
                        
                        # Chỉ soi các dòng liền kề thực sự
                        if idx_curr == idx_prev + 1:
                            prev_end = data.loc[idx_prev, 'End Window']
                            curr_begin = data.loc[idx_curr, 'Begin Window']
                            
                            # Nếu giờ chốt trùng nhau, tô sáng cả hai ô
                            if prev_end == curr_begin and prev_end != "-":
                                relay_style = 'background-color: #d4edda; font-weight: 900; color: #0e6655; font-size: 15px; border-bottom: 2px solid #28b463;'
                                css.loc[idx_prev, 'End Window'] = relay_style
                                css.loc[idx_curr, 'Begin Window'] = relay_style
                return css

            styler.apply(highlight_relay, axis=None)
            
            return styler

        tab_cl, tab_cm = st.tabs(["⚓ TRẠM CÁT LÁI", "🚢 TRẠM CÁI MÉP"])
        
        with tab_cl:
            f_cl = df_cl_full[(df_cl_full['Parsed_Date'] >= start) & (df_cl_full['Parsed_Date'] <= end)].copy()
            f_cl.rename(columns={'Parsed_Date': 'Date', 'Ký hiệu': 'HLW Vung Tau', col_time_orig: 'Time'}, inplace=True)
            f_cl['Date'] = f_cl['Date'].dt.strftime('%d/%m/%Y')
            f_cl.loc[f_cl['Date'] == f_cl['Date'].shift(), 'Date'] = ""
            f_cl[col_level] = f_cl[col_level].map('{:.1f}'.format)
            
            all_cols_cl = f_cl.columns.tolist()
            sel_cl = st.multiselect("⚙️ Ẩn/Hiện cột (Cát Lái):", all_cols_cl, default=all_cols_cl, key="ms_cl")
            st.dataframe(style_tab_table(f_cl[sel_cl].style, sel_cl, is_cl=True), use_container_width=True, hide_index=True, height=600)

        with tab_cm:
            f_cm = df_cm_full[(df_cm_full['Parsed_Date'] >= start) & (df_cm_full['Parsed_Date'] <= end)].copy()
            f_cm.rename(columns={'Parsed_Date': 'Date', 'Ký hiệu': 'HLW Vung Tau', col_time_orig: 'Time'}, inplace=True)
            f_cm['Date'] = f_cm['Date'].dt.strftime('%d/%m/%Y')
            f_cm.loc[f_cm['Date'] == f_cm['Date'].shift(), 'Date'] = ""
            f_cm[col_level] = f_cm[col_level].map('{:.1f}'.format)
            
            all_cols_cm = f_cm.columns.tolist()
            sel_cm = st.multiselect("⚙️ Ẩn/Hiện cột (Cái Mép):", all_cols_cm, default=all_cols_cm, key="ms_cm")
            st.dataframe(style_tab_table(f_cm[sel_cm].style, sel_cm, is_cl=False), use_container_width=True, hide_index=True, height=600)

    except Exception as e:
        st.error(f"❌ Lỗi hệ thống: {e}")
