import streamlit as st
import pandas as pd
import io
from PIL import Image

st.set_page_config(page_title="FIP Recon Tool V24", layout="wide")

# --- BRANDING ---
try:
    logo_img = Image.open('becu_logo.png')
    col1, col2 = st.columns([1, 8])
    with col1:
        st.image(logo_img, width=100)
    with col2:
        st.title("FIP Recon Tool V24")
except:
    st.title("FIP Recon Tool V24")

st.divider()

def header_hunter(file):
    if file.name.endswith('.csv'):
        try:
            df_raw = pd.read_csv(file, header=None, encoding='utf-8')
        except:
            df_raw = pd.read_csv(file, header=None, encoding='ISO-8859-1')
    else:
        df_raw = pd.read_excel(file, header=None)
    
    header_row_index = 0
    # Search first 50 rows - very aggressive
    for i, row in df_raw.head(50).iterrows():
        vals = [str(v).strip().lower() for v in row.values]
        # Match your specific CUNA and Activity keywords
        if any(keyword in vals for keyword in ['acno', 'acct_nr', 'cert_num', 'cert_holder_fname', 'name']):
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

        # ACTIVITY NAME (SONNYLAL,KAMAL)
        name_col_act = next((c for c in df_act.columns if 'name' in str(c).lower()), None)
        if name_col_act:
            def clean_act_name(val):
                v = str(val).upper()
                if ',' in v:
                    parts = v.split(',')
                    return f"{parts[1].strip()} {parts[0].strip()}"
                return v
            df_act['Display_Name'] = df_act[name_col_act].apply(clean_act_name)
        else:
            df_act['Display_Name'] = "Unknown"

        # CUNA NAME (FNAME, MNAME, LNAME)
        fname_col = next((c for c in df_cuna.columns if 'fname' in str(c).lower()), None)
        lname_col = next((c for c in df_cuna.columns if 'lname' in str(c).lower()), None)
        mname_col = next((c for c in df_cuna.columns if 'mname' in str(c).lower()), None)

        if fname_col and lname_col:
            df_cuna['CUNA_Full_Name'] = df_cuna[fname_col].astype(str).replace('nan', '') + " " + \
                                        (df_cuna[mname_col].astype(str).replace('nan', '') if mname_col else "") + " " + \
                                        df_cuna[lname_col].astype(str).replace('nan', '')
            df_cuna['CUNA_Full_Name'] = df_cuna['CUNA_Full_Name'].str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()
        else:
            df_cuna['CUNA_Full_Name'] = "Unknown"

        # IDENTIFY COLUMNS
        ac_col = next((c for c in df_act.columns if any(k in str(c).lower() for k in ['acno', 'acct_nr'])), df_act.columns[0])
        cuna_id_col = next((c for c in df_cuna.columns if 'acct_nr' in str(c).lower()), df_cuna.columns[0])
        cert_col = next((c for c in df_cuna.columns if 'cert_num' in str(c).lower()), None)
        
        # PREMIUM DETECTION
        def find_best_col(df, targets):
            for c in df.columns:
                if pd.to_numeric(df[c], errors='coerce').isin(targets).any():
                    return c
            return None

        act_prem_col = find_best_col(df_act, FIP_AMOUNTS)
        cuna_prem_col = next((c for c in df_cuna.columns if 'curr' in str(c).lower() and 'prem' in str(c).lower()), None)

        if st.button("🚀 Process Reports"):
            if not act_prem_col or not cuna_prem_col:
                st.error("Could not find premium columns. Please check file headers.")
            else:
                # JOIN LOGIC
                df_act['Join_ID'] = df_act[ac_col].astype(str).str.split('.').str[0].str.lstrip('0').str.strip()
                df_cuna['Join_ID'] = df_cuna[cuna_id_col].astype(str).str.split('.').str[0].str.lstrip('0').str.strip()
                
                df_act['Numeric_Amt'] = pd.to_numeric(df_act[act_prem_col], errors='coerce').fillna(0)
                df_fip = df_act[df_act['Numeric_Amt'].isin(FIP_AMOUNTS)].copy()

                merged = pd.merge(df_fip, df_cuna[['Join_ID', cert_col, 'PLAN', 'CUNA_Full_Name']], on='Join_ID', how='left')
                
                mismatches = merged[merged[cert_col].isna()]
                ghosts = df_cuna[~df_cuna['Join_ID'].isin(df_fip['Join_ID'])].copy()

                full_report = pd.DataFrame()
                full_report['ACCT_NR'] = merged[ac_col]
                full_report['NAME'] = merged['Display_Name']
                full_report['PLAN'] = merged['PLAN']
                full_report['PREMIUM_AMT'] = merged['Numeric_Amt']
                full_report['CERT_NUM'] = merged[cert_col]
                
                cleaned_report = full_report[full_report['CERT_NUM'].notna()].copy()

                t1, t2, t3 = st.tabs(["📄 Results", "🔍 Queries (Mismatches)", "⚠️ Uncollected"])
                
                with t1:
                    st.dataframe(full_report, use_container_width=True)
                    out_full = io.BytesIO()
                    with pd.ExcelWriter(out_full, engine='openpyxl') as writer: full_report.to_excel(writer, index=False)
                    st.download_button("📥 Download Full Report", data=out_full.getvalue(), file_name="Full_FIP_Report.xlsx")
                    
                    out_clean = io.BytesIO()
                    with pd.ExcelWriter(out_clean, engine='openpyxl') as writer: cleaned_report.to_excel(writer, index=False)
                    st.download_button("📥 Download CUNA Upload", data=out_clean.getvalue(), file_name="CUNA_Portal_Upload.xlsx")

                with t2:
                    st.dataframe(mismatches[[ac_col, 'Display_Name', 'Numeric_Amt']], use_container_width=True)

                with t3:
                    st.dataframe(ghosts[[cuna_id_col, 'CUNA_Full_Name', 'PLAN']], use_container_width=True)

    except Exception as e:
        st.error(f"Critical Error: {e}")
