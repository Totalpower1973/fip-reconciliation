import streamlit as st
import pandas as pd
import io
from PIL import Image

st.set_page_config(page_title="FIP Recon Tool V24.1", layout="wide")

# --- BRANDING ---
try:
    logo_img = Image.open('becu_logo.png')
    col1, col2 = st.columns([1, 8])
    with col1:
        st.image(logo_img, width=100)
    with col2:
        st.title("FIP Recon Tool V24.1")
except:
    st.title("FIP Recon Tool V24.1")

st.divider()

# --- THE "FORCE FIND" HEADER HUNTER ---
def header_hunter(file):
    if file.name.endswith('.csv'):
        # Try multiple encodings common in banking exports
        for enc in ['utf-8', 'iso-8859-1', 'cp1252']:
            try:
                file.seek(0)
                df_raw = pd.read_csv(file, header=None, encoding=enc)
                break
            except:
                continue
    else:
        df_raw = pd.read_excel(file, header=None)
    
    # Identify the header row by looking for data patterns, not just names
    header_row_index = 0
    for i, row in df_raw.head(50).iterrows():
        row_str = [str(v).lower().strip() for v in row.values]
        # Look for any of your key column markers
        if any(k in row_str for k in ['acno', 'acct_nr', 'cert_num', 'cert_holder_fname', 'name']):
            header_row_index = i
            break
            
    df = df_raw.iloc[header_row_index:].copy()
    df.columns = [str(c).strip() for c in df.iloc[0]]
    df = df[1:].reset_index(drop=True)
    return df.dropna(how='all')

FIP_AMOUNTS = [52.80, 63.40, 79.20, 79.30, 95.10, 105.60, 126.80, 158.40, 190.20, 198.30, 253.60, 261.70, 323.60, 325.10, 380.40, 396.60, 412.10, 472.90, 528.00, 555.10, 634.00, 826.00]

u1, u2 = st.columns(2)
with u1:
    act_file = st.file_uploader("📂 Activity Report (CUMME)", type=['csv', 'xlsx', 'xls'])
with u2:
    cuna_file = st.file_uploader("📂 CUNA Billing File", type=['csv', 'xlsx', 'xls'])

if act_file and cuna_file:
    try:
        df_act = header_hunter(act_file)
        df_cuna = header_hunter(cuna_file)

        # 1. FIND PREMIUM COLUMNS (The "Arg must be a list" Fix)
        def find_premium_column(df):
            for col in df.columns:
                # Convert column to numeric, ignoring errors
                nums = pd.to_numeric(df[col], errors='coerce')
                # If at least one value matches our FIP list, this is our column
                if nums.isin(FIP_AMOUNTS).any():
                    return col, nums
            return None, None

        act_prem_col, act_nums = find_premium_column(df_act)
        cuna_prem_col, cuna_nums = find_premium_column(df_cuna)

        # 2. FIND ACCOUNT/JOIN COLUMNS
        ac_col = next((c for c in df_act.columns if any(k in str(c).lower() for k in ['acno', 'acct_nr'])), df_act.columns[0])
        cuna_id_col = next((c for c in df_cuna.columns if any(k in str(c).lower() for k in ['acct_nr', 'id'])), df_cuna.columns[0])
        cert_col = next((c for c in df_cuna.columns if 'cert_num' in str(c).lower()), None)

        if st.button("🚀 Process Reports"):
            if act_prem_col is None or cuna_prem_col is None:
                st.error("❌ Could not find Premium amounts in one of the files. Please ensure the files contain the $ values.")
                st.write("Columns found in Activity:", list(df_act.columns))
                st.write("Columns found in CUNA:", list(df_cuna.columns))
            else:
                # Add Numeric columns to dataframes
                df_act['Numeric_Amt'] = act_nums.fillna(0)
                df_cuna['CUNA_Amt'] = cuna_nums.fillna(0)

                # Name Processing
                name_col_act = next((c for c in df_act.columns if 'name' in str(c).lower()), None)
                df_act['Display_Name'] = df_act[name_col_act].astype(str).str.upper() if name_col_act else "Unknown"
                
                # Join logic
                df_act['Join_ID'] = df_act[ac_col].astype(str).str.split('.').str[0].str.lstrip('0').str.strip()
                df_cuna['Join_ID'] = df_cuna[cuna_id_col].astype(str).str.split('.').str[0].str.lstrip('0').str.strip()
                
                # Filter for valid FIP payments
                df_fip = df_act[df_act['Numeric_Amt'].isin(FIP_AMOUNTS)].copy()

                # Merge
                merged = pd.merge(df_fip, df_cuna[['Join_ID', cert_col, 'PLAN']], on='Join_ID', how='left')
                
                mismatches = merged[merged[cert_col].isna()]
                ghosts = df_cuna[~df_cuna['Join_ID'].isin(df_fip['Join_ID'])].copy()

                # Results
                full_report = pd.DataFrame({
                    'ACCT_NR': merged[ac_col],
                    'NAME': merged['Display_Name'],
                    'PLAN': merged.get('PLAN', 'N/A'),
                    'PREMIUM_AMT': merged['Numeric_Amt'],
                    'CERT_NUM': merged[cert_col]
                })

                t1, t2, t3 = st.tabs(["📄 Export List", "🔍 Queries (Mismatches)", "⚠️ Uncollected"])
                
                with t1:
                    st.dataframe(full_report, use_container_width=True)
                    out = io.BytesIO()
                    with pd.ExcelWriter(out, engine='openpyxl') as w: full_report.to_excel(w, index=False)
                    st.download_button("📥 Download Report", data=out.getvalue(), file_name="FIP_Recon.xlsx")

                with t2:
                    st.dataframe(mismatches[[ac_col, 'Display_Name', 'Numeric_Amt']], use_container_width=True)

                with t3:
                    st.dataframe(ghosts[[cuna_id_col, 'PLAN', 'CUNA_Amt']], use_container_width=True)

    except Exception as e:
        st.error(f"Critical System Error: {e}")
        st.info("Check: Are the files CSV or Excel? Ensure they aren't password protected.")
