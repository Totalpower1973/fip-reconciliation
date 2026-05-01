import streamlit as st
import pandas as pd
import io
from PIL import Image

st.set_page_config(page_title="FIP Recon Tool V24", layout="wide")

# --- BRANDING & LOGO SECTION ---
try:
    logo_img = Image.open('becu_logo.png')
    col1, col2 = st.columns([1, 8])
    with col1:
        st.image(logo_img, width=100)
    with col2:
        st.title("FIP Recon Tool V24")
        st.caption("Family Indemnity Plan Monthly Reconciliation")
except FileNotFoundError:
    st.title("FIP Recon Tool V24")
    st.info("Note: Place 'becu_logo.png' in the folder to display the logo.")

st.divider()

# --- CORE FUNCTIONS ---
def header_hunter(file):
    if file.name.endswith('.csv'):
        try:
            df_raw = pd.read_csv(file, header=None, encoding='utf-8')
        except:
            df_raw = pd.read_csv(file, header=None, encoding='ISO-8859-1')
    else:
        df_raw = pd.read_excel(file, header=None)
    
    header_row_index = 0
    for i, row in df_raw.head(25).iterrows():
        vals = [str(v).strip().lower() for v in row.values]
        # Look for the specific CUNA or Activity headers
        if any(keyword in vals for keyword in ['acno', 'name', 'acct_nr', 'cert_num', 'cert_holder_fname']):
            header_row_index = i
            break
            
    df = df_raw.iloc[header_row_index:].copy()
    df.columns = [str(c).strip() for c in df.iloc[0]]
    df = df[1:].reset_index(drop=True)
    df = df[df.iloc[:, 0].astype(str).str.len() > 0]
    return df

FIP_AMOUNTS = [52.80, 63.40, 79.20, 79.30, 95.10, 105.60, 126.80, 158.40, 190.20, 198.30, 253.60, 261.70, 323.60, 325.10, 380.40, 396.60, 412.10, 472.90, 528.00, 555.10, 634.00, 826.00]

# --- FILE UPLOADS ---
u1, u2 = st.columns(2)
with u1:
    act_file = st.file_uploader("📂 Activity Report (CUMME)", type=['csv', 'xlsx', 'xls'])
with u2:
    cuna_file = st.file_uploader("📂 CUNA Billing File", type=['csv', 'xlsx', 'xls'])

if act_file and cuna_file:
    try:
        df_act = header_hunter(act_file)
        df_cuna = header_hunter(cuna_file)

        # 1. PROCESS ACTIVITY REPORT NAMES (Format: LAST,FIRST)
        name_col_act = next((c for c in df_act.columns if 'name' in c.lower()), None)
        if name_col_act:
            # Clean up "SONNYLAL,KAMAL" into "KAMAL SONNYLAL" for readability
            def clean_act_name(val):
                val = str(val).upper()
                if ',' in val:
                    parts = val.split(',')
                    return f"{parts[1].strip()} {parts[0].strip()}"
                return val
            df_act['Display_Name'] = df_act[name_col_act].apply(clean_act_name)
        else:
            df_act['Display_Name'] = "Unknown"

        # 2. PROCESS CUNA NAMES (Format: FNAME, MNAME, LNAME)
        # We combine them into a single column so we can show them in the report
        fname_col = next((c for c in df_cuna.columns if 'fname' in c.lower()), None)
        mname_col = next((c for c in df_cuna.columns if 'mname' in c.lower()), None)
        lname_col = next((c for c in df_cuna.columns if 'lname' in c.lower()), None)

        if fname_col and lname_col:
            df_cuna['CUNA_Full_Name'] = df_cuna[fname_col].astype(str).replace('nan', '') + " " + \
                                        df_cuna[mname_col].astype(str).replace('nan', '') + " " + \
                                        df_cuna[lname_col].astype(str).replace('nan', '')
            df_cuna['CUNA_Full_Name'] = df_cuna['CUNA_Full_Name'].str.replace(r'\s+', ' ', regex=True).str.strip()
        else:
            df_cuna['CUNA_Full_Name'] = "Unknown"

        # 3. IDENTIFY JOIN COLUMNS
        ac_col = next((c for c in df_act.columns if 'acno' in c.lower() or 'acct_nr' in c.lower()), df_act.columns[0])
        cuna_id_col = next(c for c in df_cuna.columns if 'acct_nr' in str(c).lower())
        cert_col = next(c for c in df_cuna.columns if 'cert_num' in str(c).lower())
        
        # Determine premium columns
        best_act_amt = next((c for c in df_act.columns if pd.to_numeric(df_act[c], errors='coerce').isin(FIP_AMOUNTS).any()), df_act.columns[-1])
        cuna_prem_col = next((c for c in df_cuna.columns if 'curr' in c.lower() and 'prem' in c.lower()), df_cuna.columns[-1])

        if st.button("🚀 Process Reports"):
            # Standardize IDs for matching
            df_act['Join_ID'] = df_act[ac_col].astype(str).str.split('.').str[0].str.lstrip('0')
            df_cuna['Join_ID'] = df_cuna[cuna_id_col].astype(str).str.split('.').str[0].str.lstrip('0')
            
            df_act['Numeric_Amt'] = pd.to_numeric(df_act[best_act_amt], errors='coerce').fillna(0)
            df_fip = df_act[df_act['Numeric_Amt'].isin(FIP_AMOUNTS)].copy()

            # Merge datasets
            merged = pd.merge(df_fip, df_cuna[['Join_ID', cert_col, 'PLAN', 'CUNA_Full_Name']], on='Join_ID', how='left')
            
            # Identify Mismatches
            mismatches = merged[merged[cert_col].isna()]
            ghosts = df_cuna[~df_cuna['Join_ID'].isin(df_fip['Join_ID'])].copy()

            # BUILD FINAL REPORT
            full_report = pd.DataFrame()
            full_report['ACCT_NR'] = merged[ac_col]
            full_report['NAME (BECU)'] = merged['Display_Name']
            full_report['PLAN'] = merged['PLAN']
            full_report['PREMIUM_AMT'] = merged['Numeric_Amt']
            full_report['CERT_NUM'] = merged[cert_col]
            
            cleaned_report = full_report[full_report['CERT_NUM'].notna()].copy()

            # UI TABS
            tab1, tab2, tab3 = st.tabs(["📄 Export & Preview", "🔍 Queries (Mismatches)", "⚠️ Uncollected Premiums"])
            
            with tab1:
                st.subheader("Summary Table")
                st.dataframe(full_report, use_container_width=True)
                
                col_a, col_b = st.columns(2)
                with col_a:
                    out_full = io.BytesIO()
                    with pd.ExcelWriter(out_full, engine='openpyxl') as writer: 
                        full_report.to_excel(writer, index=False)
                    st.download_button("📥 Download Full Report", data=out_full.getvalue(), file_name="Full_FIP_Report.xlsx")
                with col_b:
                    out_clean = io.BytesIO()
                    with pd.ExcelWriter(out_clean, engine='openpyxl') as writer: 
                        cleaned_report.to_excel(writer, index=False)
                    st.download_button("📥 Download CUNA Upload", data=out_clean.getvalue(), file_name="CUNA_Portal_Upload.xlsx")

            with tab2:
                st.warning(f"Found {len(mismatches)} members paying but missing from CUNA file.")
                st.dataframe(mismatches[[ac_col, 'Display_Name', 'Numeric_Amt']], use_container_width=True)

            with tab3:
                st.error(f"Found {len(ghosts)} members billed by CUNA with no BECU payment.")
                st.dataframe(ghosts[[cuna_id_col, 'CUNA_Full_Name', 'PLAN', cuna_prem_col]], use_container_width=True)

    except Exception as e:
        st.error(f"Processing Error: {e}")
        st.info("Ensure both files have a row containing 'ACNO' or 'CERT_NUM' to identify the headers.")

st.markdown("---")
st.caption("FIP Reconciliation Tool - Version 24 (Split-Name Fix)")
