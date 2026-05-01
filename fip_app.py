import streamlit as st
import pandas as pd
import io
from PIL import Image

st.set_page_config(page_title="FIP Recon Tool V24.3", layout="wide")

# --- BRANDING ---
try:
    logo_img = Image.open('becu_logo.png')
    col1, col2 = st.columns([1, 8])
    with col1:
        st.image(logo_img, width=100)
    with col2:
        st.title("FIP Recon Tool V24.3")
except:
    st.title("FIP Recon Tool V24.3")

st.divider()

def header_hunter(file):
    # Support both CSV and Excel
    if file.name.endswith('.csv'):
        for enc in ['utf-8', 'iso-8859-1', 'cp1252']:
            try:
                file.seek(0)
                df_raw = pd.read_csv(file, header=None, encoding=enc)
                break
            except:
                continue
    else:
        df_raw = pd.read_excel(file, header=None)
    
    # Scan for header row
    header_row_index = 0
    for i, row in df_raw.head(50).iterrows():
        row_str = [str(v).lower().strip() for v in row.values]
        if any(k in row_str for k in ['acno', 'acct_nr', 'cert_num', 'name']):
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

        if st.button("🚀 Process Reports"):
            # 1. FIND PREMIUM COLUMNS (The core of the logic)
            def get_prem_info(df):
                for col in df.columns:
                    nums = pd.to_numeric(df[col], errors='coerce')
                    if not nums.dropna().empty and any(val in FIP_AMOUNTS for val in nums.dropna()):
                        return col, nums
                return None, None

            act_col_name, act_nums = get_prem_info(df_act)
            cuna_col_name, cuna_nums = get_prem_info(df_cuna)

            if act_col_name is None or cuna_col_name is None:
                st.error("Could not find Premium columns. Check if your files contain the dollar amounts.")
                st.stop()

            # 2. IDENTIFY JOIN COLUMNS
            ac_col = next((c for c in df_act.columns if any(k in str(c).lower() for k in ['acno', 'acct_nr'])), df_act.columns[0])
            cuna_id_col = next((c for c in df_cuna.columns if any(k in str(c).lower() for k in ['acct_nr', 'id'])), df_cuna.columns[0])
            cert_col = next((c for c in df_cuna.columns if 'cert_num' in str(c).lower()), None)
            
            # 3. IDENTIFY NAME COLUMNS (With Safety Fallback)
            # Find BECU Name (Activity Report)
            name_act = next((c for c in df_act.columns if 'name' in str(c).lower()), None)
            if name_act:
                df_act['NAME_CLEAN'] = df_act[name_act].astype(str).str.upper()
            else:
                df_act['NAME_CLEAN'] = "UNKNOWN"

            # Find CUNA Name (Billing File)
            fname = next((c for c in df_cuna.columns if 'fname' in str(c).lower()), None)
            lname = next((c for c in df_cuna.columns if 'lname' in str(c).lower()), None)
            
            if fname and lname:
                df_cuna['CUNA_NAME'] = df_cuna[fname].astype(str) + " " + df_cuna[lname].astype(str)
            else:
                # Fallback to any column with 'name' in it
                alt_name = next((c for c in df_cuna.columns if 'name' in str(c).lower()), None)
                df_cuna['CUNA_NAME'] = df_cuna[alt_name].astype(str) if alt_name else "UNKNOWN"

            # 4. DATA STANDARDIZATION
            df_act['Numeric_Amt'] = act_nums.fillna(0)
            df_cuna['CUNA_Amt'] = cuna_nums.fillna(0)
            df_act['Join_ID'] = df_act[ac_col].astype(str).str.split('.').str[0].str.lstrip('0').str.strip()
            df_cuna['Join_ID'] = df_cuna[cuna_id_col].astype(str).str.split('.').str[0].str.lstrip('0').str.strip()

            # 5. RECONCILIATION
            df_fip = df_act[df_act['Numeric_Amt'].isin(FIP_AMOUNTS)].copy()
            merged = pd.merge(df_fip, df_cuna[['Join_ID', cert_col, 'PLAN', 'CUNA_NAME']], on='Join_ID', how='left')
            
            mismatches = merged[merged[cert_col].isna()]
            ghosts = df_cuna[~df_cuna['Join_ID'].isin(df_fip['Join_ID'])].copy()

            # 6. RESULTS
            full_report = pd.DataFrame({
                'ACCT_NR': merged[ac_col],
                'NAME': merged['NAME_CLEAN'],
                'PLAN': merged.get('PLAN', 'N/A'),
                'PREMIUM': merged['Numeric_Amt'],
                'CERT_NUM': merged[cert_col]
            })

            t1, t2, t3 = st.tabs(["📄 Results", "🔍 Queries (Mismatches)", "⚠️ Uncollected"])
            with t1:
                st.dataframe(full_report, use_container_width=True)
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='openpyxl') as w: full_report.to_excel(w, index=False)
                st.download_button("📥 Download Report", data=out.getvalue(), file_name="FIP_Recon.xlsx")
            with t2:
                st.dataframe(mismatches[[ac_col, 'NAME_CLEAN', 'Numeric_Amt']], use_container_width=True)
            with t3:
                st.dataframe(ghosts[['Join_ID', 'CUNA_NAME', 'CUNA_Amt']], use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")
