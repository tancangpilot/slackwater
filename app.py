import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import re
import calendar
import numpy as np
import plotly.graph_objects as go
import os

st.set_page_config(page_title="Dự án Window Thủy Triều V2.4", layout="wide")
st.title("🌊 Ứng Dụng Phân Tích & Trực Quan Hóa Thủy Triều (Bản V2.4 Auto-Load)")

tz_vn = timezone(timedelta(hours=7))
now_vn = datetime.now(tz_vn)

st.info(f"🕒 Thời gian hiện tại: **{now_vn.strftime('%H:%M:%S - %d/%m/%Y')}** (Múi giờ +7)")

# ==========================================
# CƠ CHẾ AUTO-LOAD FILE MẶC ĐỊNH
# ==========================================
DEFAULT_FILE = "HLWVT 2026.xlsx" # Tên file gốc để sẵn trong hệ thống

uploaded_file = st.file_uploader(f"Tải file Excel khác lên (Bỏ qua bước này nếu đã có sẵn file {DEFAULT_FILE})", type=['xlsx', 'xls', 'csv'])

file_source = None
if uploaded_file is not None:
    file_source = uploaded_file
elif os.path.exists(DEFAULT_FILE):
    file_source = DEFAULT_FILE
    st.success(f"✅ Đã tự động đọc dữ liệu từ hệ thống: **{DEFAULT_FILE}** (Không cần Upload lại!)")
else:
    st.warning(f"⚠️ Mẹo: Hãy copy file '{DEFAULT_FILE}' để vào cùng thư mục với file app.py để ứng dụng tự động tải dữ liệu mỗi lần mở web!")

if file_source is not None:
    try:
        # Kiểm tra định dạng file là CSV hay Excel
        is_csv = False
        if isinstance(file_source, str):
            is_csv = file_source.lower().endswith('.csv')
        else:
            is_csv = file_source.name.lower().endswith('.csv')

        if is_csv:
            xl_sheet_names = ['HLW-VT']
            df = pd.read_csv(file_source)
            has_cl_data = False
        else:
            xl = pd.ExcelFile(file_source)
            has_cl_data = False
            if 'CL' in xl.sheet_names:
                df_cl = xl.parse('CL')
                df_cl.columns = df_cl.columns.astype(str).str.strip().str.upper()
                if 'DATE' in df_cl.columns and 'TIME' in df_cl.columns:
                    dts = []
                    for _, r in df_cl.iterrows():
                        try:
                            d = pd.to_datetime(r['DATE'])
                            if pd.isna(d): dts.append(pd.NaT); continue
                            t = r['TIME']
                            if isinstance(t, str): h, m = map(int, t.strip().split(':')[:2])
                            else: h, m = t.hour, t.minute
                            dts.append(d + pd.Timedelta(hours=h, minutes=m))
                        except: dts.append(pd.NaT)
                    df_cl['F28_Datetime'] = dts
                    df_cl = df_cl.dropna(subset=['F28_Datetime']).reset_index(drop=True)
                    has_cl_data = not df_cl.empty
            
            df = xl.parse('HLW-VT')
            
        df.columns = df.columns.str.strip()
        col_date, col_time, col_level = 'Date', 'HL Water', 'Level(m)'
        
        if col_date not in df.columns or col_time not in df.columns or col_level not in df.columns:
            st.error(f"Lỗi: Không tìm thấy đủ cột '{col_date}', '{col_time}', '{col_level}' trong sheet HLW-VT.")
        else:
            df[col_level] = pd.to_numeric(df[col_level], errors='coerce')

            def parse_smart_date(val):
                if pd.isna(val): return pd.NaT
                val_str = str(val).strip()
                if val_str.isalpha(): return pd.NaT 
                try:
                    return pd.to_datetime(val_str, errors='coerce')
                except:
                    return pd.NaT

            df['Parsed_Date'] = df[col_date].apply(parse_smart_date)
            df['Parsed_Date'] = df['Parsed_Date'].bfill(limit=1).ffill()
            df = df.dropna(subset=[col_time]).copy()
            df['Date_Filter'] = df['Parsed_Date']
            
            base_dts = []
            for idx, row in df.iterrows():
                time_val = row[col_time]
                date_val = row['Date_Filter']
                try:
                    if isinstance(time_val, (datetime, pd.Timestamp)):
                        h, m = time_val.hour, time_val.minute
                    elif hasattr(time_val, 'hour'): 
                        h, m = time_val.hour, time_val.minute
                    else:
                        h, m = map(int, str(time_val).strip().split(':')[:2])
                    base_dts.append(date_val + pd.Timedelta(hours=h, minutes=m))
                except:
                    base_dts.append(pd.NaT)
            
            df['Event_Datetime'] = base_dts
            df = df.dropna(subset=['Event_Datetime']).sort_values('Event_Datetime').reset_index(drop=True)

            df['Duration_hrs'] = df['Event_Datetime'].diff().dt.total_seconds() / 3600
            df['Amplitude'] = abs(df[col_level] - df[col_level].shift(1))
            
            level_err = df[(df[col_level] > 5.0) | (df[col_level] < -0.5)]
            time_err = df[(df['Duration_hrs'] < 2.5) & (df['Amplitude'] > 1.0)]
            gap_err = df[df['Duration_hrs'] > 16.0]
            
            anomalies = pd.concat([level_err, time_err, gap_err]).drop_duplicates(subset=['Event_Datetime']).sort_values('Event_Datetime')
            if not anomalies.empty:
                st.error(f"🚨 CẢNH BÁO: Phát hiện {len(anomalies)} dòng dữ liệu vô lý trong file Excel.")

            df_clean = df[(df[col_level] <= 5.0) & (df[col_level] >= -0.5)].copy().reset_index(drop=True)
            df_clean['Next_Amplitude'] = abs(df_clean[col_level].shift(-1) - df_clean[col_level])
            df_clean['Level_num'] = df_clean[col_level] 
            
            prev_level = df_clean[col_level].shift(1)
            next_level = df_clean[col_level].shift(-1)
            is_hw = (df_clean[col_level] > prev_level) | (prev_level.isna() & (df_clean[col_level] > next_level))
            df_clean['Ký hiệu'] = ['HW' if hw else 'LW' for hw in is_hw]
            
            def format_dt(dt_val, base_dt_val):
                s = dt_val.strftime('%H:%M')
                if dt_val.date() > base_dt_val.date(): s += ' (+1)'
                elif dt_val.date() < base_dt_val.date(): s += ' (-1)'
                return s

            slack_times, arrows, slack_f28_times, diffs, final_slacks, final_slacks_dt = [], [], [], [], [], []
            for idx, row in df_clean.iterrows():
                hw_lw = row['Ký hiệu']
                level = row[col_level]
                base_dt = row['Event_Datetime']
                amp = row['Amplitude']
                next_amp = row['Next_Amplitude']
                
                if pd.isna(amp): amp = next_amp
                if pd.isna(next_amp): next_amp = amp
                min_amp = min(amp, next_amp) if pd.notna(amp) else 0
                
                # LỌC NƯỚC ĐỨNG
                if min_amp <= 0.4:
                    slack_times.append("Nước đứng")
                    arrows.append("-")
                    slack_f28_times.append("-")
                    diffs.append("-")
                    final_slacks.append("Nước đứng")
                    final_slacks_dt.append(pd.NaT)
                    continue
                
                # CÔNG THỨC CL V2.2
                if hw_lw == 'HW':
                    arr = '↙'
                    if level >= 4.0: delta = pd.Timedelta(hours=3, minutes=55)
                    elif level >= 3.0: delta = pd.Timedelta(hours=3, minutes=25)
                    elif level >= 2.0: delta = pd.Timedelta(hours=3, minutes=15)
                    else: delta = pd.Timedelta(hours=3, minutes=5)
                else:
                    arr = '↗'
                    if level >= 1.5: delta = pd.Timedelta(hours=3, minutes=40)
                    elif level >= 1.0: delta = pd.Timedelta(hours=3, minutes=45)
                    elif level >= 0.5: delta = pd.Timedelta(hours=3, minutes=50)
                    else: delta = pd.Timedelta(hours=3, minutes=55)
                        
                new_dt = base_dt + delta
                rounded_minute = (new_dt.minute // 5) * 5
                new_dt = new_dt.replace(minute=rounded_minute)
                
                cl_str = format_dt(new_dt, base_dt)
                slack_times.append(cl_str)
                arrows.append(arr)
                
                # TẠO SLACK FINAL (TỐI ƯU 35%)
                if has_cl_data:
                    time_diffs = (df_cl['F28_Datetime'] - new_dt).abs()
                    min_idx = time_diffs.idxmin()
                    closest_f28 = df_cl.loc[min_idx, 'F28_Datetime']
                    
                    diff_mins = int((new_dt - closest_f28).total_seconds() / 60)
                    diff_mins_abs = abs(diff_mins)
                    
                    if diff_mins_abs <= 180:
                        f28_str = format_dt(closest_f28, base_dt)
                        slack_f28_times.append(f28_str)
                        diff_str = f"+{diff_mins}" if diff_mins > 0 else f"{diff_mins}"
                        diffs.append(diff_str)
                        
                        earlier_dt = new_dt if diff_mins < 0 else closest_f28
                        
                        if diff_mins_abs <= 10:
                            final_dt = earlier_dt
                        elif 10 < diff_mins_abs <= 15:
                            final_dt = earlier_dt + pd.Timedelta(minutes=5)
                        elif 15 < diff_mins_abs <= 35:
                            half_diff = diff_mins_abs // 2
                            final_dt = earlier_dt + pd.Timedelta(minutes=half_diff)
                        else:
                            thirty_five_percent = int(diff_mins_abs * 0.35)
                            final_dt = earlier_dt + pd.Timedelta(minutes=thirty_five_percent)
                            
                        # Làm tròn lùi 5 phút
                        rm = (final_dt.minute // 5) * 5
                        final_dt = final_dt.replace(minute=rm)
                        
                        final_slacks.append(format_dt(final_dt, base_dt))
                        final_slacks_dt.append(final_dt)
                            
                    else:
                        slack_f28_times.append("-")
                        diffs.append("-")
                        final_slacks.append(f"{cl_str} (Dự phòng)")
                        final_slacks_dt.append(new_dt)
                else:
                    slack_f28_times.append("")
                    diffs.append("")
                    final_slacks.append(cl_str)
                    final_slacks_dt.append(new_dt)
                    
            df_clean['Slack Water CL'] = slack_times
            df_clean['Slack Water F28'] = slack_f28_times
            df_clean['Sai khác (phút)'] = diffs
            df_clean['SLACK FINAL (CHỐT)'] = final_slacks
            df_clean['Slack_Datetime_Final'] = final_slacks_dt
            df_clean['Dòng chảy'] = arrows

            st.write("---")
            view_mode = st.radio("🔄 Vui lòng chọn chế độ hiển thị:", 
                                 ("Chế độ 7 Ngày", "Chế độ xem theo Tháng"), horizontal=True)
            st.write("") 
            
            if view_mode == "Chế độ 7 Ngày":
                col1, col2 = st.columns(2)
                with col1: selected_date = st.date_input("🗓️ Chọn mốc ngày hiện tại:", now_vn.date())
                anchor_date = pd.Timestamp(selected_date)
                start_date = anchor_date - pd.Timedelta(days=1)
                end_date = start_date + pd.Timedelta(days=6)
            else: 
                col1, col2, col3 = st.columns(3)
                with col1: selected_month = st.selectbox("📅 Chọn Tháng:", list(range(1, 13)), index=now_vn.month - 1)
                with col2: selected_year = st.selectbox("📅 Chọn Năm:", list(range(now_vn.year - 1, now_vn.year + 4)), index=1)
                last_day_of_month = calendar.monthrange(selected_year, selected_month)[1]
                start_date = pd.Timestamp(year=selected_year, month=selected_month, day=1)
                end_date = pd.Timestamp(year=selected_year, month=selected_month, day=last_day_of_month)

            mask = (df_clean['Date_Filter'] >= start_date) & (df_clean['Date_Filter'] <= end_date)
            filtered_df = df_clean.loc[mask].copy().reset_index(drop=True)
            
            if filtered_df.empty:
                st.warning(f"Không có dữ liệu trong khoảng từ {start_date.strftime('%d/%m/%Y')} đến {end_date.strftime('%d/%m/%Y')}")
            else:
                # 1. HIỂN THỊ BẢNG SỐ LIỆU
                display_df = filtered_df.copy()
                display_df['Ngày'] = display_df['Date_Filter'].dt.strftime('%d/%m/%Y')
                display_df.loc[display_df['Ngày'] == display_df['Ngày'].shift(), 'Ngày'] = ""
                display_df[col_level] = display_df[col_level].map('{:.1f}'.format)
                
                final_df = display_df[['Ngày', 'Ký hiệu', col_time, col_level, 'Slack Water CL', 'Slack Water F28', 'Sai khác (phút)', 'SLACK FINAL (CHỐT)', 'Dòng chảy']]
                
                day_groups = (display_df['Date_Filter'] != display_df['Date_Filter'].shift()).cumsum()
                def highlight_alternating_days(row):
                    group_id = day_groups.iloc[row.name]
                    return ['background-color: rgba(150, 150, 150, 0.15)'] * len(row) if group_id % 2 == 0 else ['background-color: transparent'] * len(row)
                def color_text_hw_lw(val):
                    if val == 'HW': return 'color: #007bff; font-weight: bold;'
                    elif val == 'LW': return 'color: #dc3545; font-weight: bold;'
                    return ''
                def color_arrows(val):
                    if val == '↙': return 'color: #007bff; font-weight: bold; font-size: 16px;'
                    elif val == '↗': return 'color: #dc3545; font-weight: bold; font-size: 16px;'
                    elif val == '-': return 'color: #888888; font-weight: bold;'
                    return ''
                def color_diff(val):
                    try:
                        v = int(val.replace('+', ''))
                        if v > 35: return 'color: #c0392b; font-weight: bold;'
                        elif v < -35: return 'color: #16a085; font-weight: bold;'
                        elif v > 0: return 'color: #d35400; font-weight: bold;' 
                        elif v < 0: return 'color: #27ae60; font-weight: bold;'
                    except: pass
                    return ''
                def color_final(val):
                    if 'Nước đứng' in str(val): return 'color: #888888; font-style: italic;'
                    if '(Dự phòng)' in str(val): return 'color: #d35400;'
                    return 'font-weight: bold; color: #1c2833; font-size: 16px; background-color: #e8f8f5;' 

                styled_df = final_df.style.apply(highlight_alternating_days, axis=1)\
                                          .map(color_text_hw_lw, subset=['Ký hiệu'])\
                                          .map(color_arrows, subset=['Dòng chảy'])\
                                          .map(color_diff, subset=['Sai khác (phút)'])\
                                          .map(color_final, subset=['SLACK FINAL (CHỐT)'])
                
                st.info("💡 **Giải thích Cột SLACK FINAL:** Lệch ≤ 10p (Lấy sớm hơn); Lệch 11-15p (+5p vào bên sớm); Lệch 16-35p (+50% lệch vào bên sớm); Lệch > 35p (+35% lệch vào bên sớm). **Tất cả làm tròn lùi về 5 phút.**")
                
                if view_mode == "Chế độ 7 Ngày":
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)
                else:
                    st.dataframe(styled_df, use_container_width=True, hide_index=True, height=500)

                # ==========================================
                # 2. VẼ BIỂU ĐỒ TRỰC QUAN (PLOTLY LINE CHART)
                # ==========================================
                st.markdown("---")
                st.subheader("📈 Đồ thị Mô phỏng Mực nước & Thời điểm Đổi dòng")
                
                fig = go.Figure()

                # Vẽ đường cong mực nước (Smooth Line)
                fig.add_trace(go.Scatter(
                    x=filtered_df['Event_Datetime'], 
                    y=filtered_df['Level_num'],
                    mode='lines+markers',
                    line_shape='spline', # Uốn cong mượt mà như sóng thật
                    name='Đỉnh/Chân Triều',
                    line=dict(color='#2980b9', width=3),
                    marker=dict(size=8, color='#2980b9'),
                    hovertemplate="<b>%{x|%d/%m/%Y %H:%M}</b><br>Mức nước: %{y:.1f}m<extra></extra>"
                ))

                # Nội suy để chấm điểm Slack Water lên đường cong
                valid_slacks = filtered_df.dropna(subset=['Slack_Datetime_Final'])
                if not valid_slacks.empty:
                    x_nums = filtered_df['Event_Datetime'].astype(np.int64)
                    y_nums = filtered_df['Level_num']
                    
                    slack_x_nums = valid_slacks['Slack_Datetime_Final'].astype(np.int64)
                    
                    # Nội suy tuyến tính tìm tọa độ Y (Mức nước tại thời điểm đổi dòng)
                    slack_y = np.interp(slack_x_nums, x_nums, y_nums)
                    
                    # Vẽ các điểm Đổi dòng bằng dấu [X] màu đỏ
                    fig.add_trace(go.Scatter(
                        x=valid_slacks['Slack_Datetime_Final'],
                        y=slack_y,
                        mode='markers',
                        name='Giờ Đổi Dòng (Slack Final)',
                        marker=dict(size=14, color='#c0392b', symbol='x', line=dict(width=2, color='#c0392b')),
                        hovertemplate="<b>🕒 Đổi dòng lúc: %{x|%H:%M (Ngày %d/%m)}</b><br>Mức nước ước tính: ~%{y:.1f}m<extra></extra>"
                    ))

                # Kẻ vạch đỏ cảnh báo Triều Cường (HW >= 4.0m)
                fig.add_hline(y=4.0, line_dash="dash", line_color="#e74c3c", 
                              annotation_text=" Vạch Cảnh Báo Triều Cường (≥ 4.0m)", 
                              annotation_position="top left",
                              annotation_font_color="#e74c3c")

                # Tối ưu giao diện đồ thị
                fig.update_layout(
                    xaxis_title="Thời gian",
                    yaxis_title="Mức nước (m)",
                    hovermode="x unified",
                    template="plotly_white",
                    height=450,
                    margin=dict(l=20, r=20, t=40, b=20),
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )

                st.plotly_chart(fig, use_container_width=True)
                    
    except Exception as e:
        st.error(f"Đã có lỗi xảy ra: {e}")
