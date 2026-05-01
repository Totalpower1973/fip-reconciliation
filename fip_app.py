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

st.divider()

# --- CORE FUNCTIONS ---
def header_hunter(file):
    if file.name.endswith('.csv'):
        try:
            df_raw = pd.read_csv(file, header=None, encoding='utf-8')
        except UnicodeDecodeError:
            df_raw = pd.read_csv(file, header=None, encoding='ISO-8859-1')
    else:
        df_raw = pd.read_excel(file, header=None)
    
    header_row_index = 0
    for i, row in df_raw.head(50).iterrows():
        vals = [str(v).strip().lower() for v in row.values]
        if any(keyword in vals for keyword in ['acno', 'name', 'acct_nr', 'cert_num']):
            header_row_index = i
            break
            
    df = df_raw.iloc[header_row_index:].copy()
    new_cols = []
    for i, col in enumerate(df.iloc[0]):
        val = str(col).strip()
        if val.lower() in ['nan', '', 'none', 'unnamed:']:
            new_cols.append(f"Extra_Field_{i}")
        else:
            new_cols.append(val)
            
    df.columns = new_cols
    df = df[1:].reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    df = df[df.iloc[:, 0].astype(str).str.len() > 0]
    
    plan_col = next((c for c in df.columns if 'plan' in c.lower()), None)
    if plan_col:
        df = df[df[plan_col].astype(str).str.contains("Plan", case=False, na=False)]
    
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols == dup] = [f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols
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

        # 1. PRE-PROCESS NAMES
        # Backup name from Activity Report
        name_act_col = next((c for c in df_act.columns if 'name' in c.lower() and 'extra' not in c.lower()), df_act.columns[1])
        df_act['Activity_Name'] = df_act[name_act_col].astype(str).str.upper()

        # Primary name from CUNA
        fname_col = next((c for c in df_cuna.columns if 'fname' in c.lower()), None)
        lname_col = next((c for c in df_cuna.columns if 'lname' in c.lower()), None)

        if fname_col and lname_col:
            df_cuna['CUNA_Name'] = df_cuna[fname_col].astype(str) + " " + df_cuna[lname_col].astype(str)
            df_cuna['CUNA_Name'] = df_cuna['CUNA_Name'].str.upper().replace('NAN', '').str.strip()
        else:
            alt_name = next((c for c in df_cuna.columns if 'name' in c.lower()), df_cuna.columns[1])
            df_cuna['CUNA_Name'] = df_cuna[alt_name].astype(str).str.upper()

        # 2. IDENTIFY COLUMNS
        ac_col = next((c for c in df_act.columns if 'acno' in c.lower() or 'acct_nr' in c.lower()), df_act.columns[0])
        best_act_col = None
        for c in df_act.columns:
            if pd.to_numeric(df_act[c], errors='coerce').isin(FIP_AMOUNTS).any():
                best_act_col = c
                break
        if not best_act_col: best_act_col = df_act.columns[-1]

        cuna_prem_col = next((c for c in df_cuna.columns if 'curr' in c.lower() and 'prem' in c.lower()), df_cuna.columns[-1])

        if st.button("🚀 Process Reports"):
            df_act['Numeric_Amt'] = pd.to_numeric(df_act[best_act_col], errors='coerce').fillna(0)
            df_fip = df_act[df_act['Numeric_Amt'].isin(FIP_AMOUNTS)].copy()
            df_fip['Join_ID'] = df_fip[ac_col].astype(str).str.split('.').str[0].str.lstrip('0')

            df_cuna['CUNA_Amt'] = pd.to_numeric(df_cuna[cuna_prem_col], errors='coerce').fillna(0)
            cuna_id_col = next(c for c in df_cuna.columns if 'acct_nr' in str(c).lower())
            cert_col = next(c for c in df_cuna.columns if 'cert_num' in str(c).lower())
            df_cuna['Join_ID'] = df_cuna[cuna_id_col].astype(str).str.split('.').str[0].str.lstrip('0')

            # MERGE
            merged = pd.merge(df_fip, df_cuna[['Join_ID', cert_col, 'PLAN', 'CUNA_Name']], on='Join_ID', how='left')
            
            # Identify Mismatches
            mismatches = merged[merged[cert_col].isna()].copy()
            # For mismatches, since CUNA_Name is null, we fill it with the Activity_Name
            mismatches['Display_Name'] = mismatches['CUNA_Name'].fillna(mismatches['Activity_Name'])
            
            ghosts = df_cuna[~df_cuna['Join_ID'].isin(df_fip['Join_ID'])].copy()

            # FINAL TABLES
            full_report = pd.DataFrame()
            full_report['ACCT_NR'] = merged[ac_col]
            full_report['NAME'] = merged['CUNA_Name'].fillna(merged['Activity_Name'])
            full_report['PLAN'] = merged['PLAN']
            full_report['PREMIUM_AMT'] = merged['Numeric_Amt']
            full_report['CERT_NUM'] = merged[cert_col]
            cleaned_report = full_report[full_report['CERT_NUM'].notna()].copy()

            # UI
            st.subheader("📊 Financial Dashboard")
            m1, m2, m3 = st.columns(3)
            m1.metric("BECU Collected", f"${df_fip['Numeric_Amt'].sum():,.2f}")
            m2.metric("CUNA Billed", f"${df_cuna['CUNA_Amt'].sum():,.2f}")
            m3.metric("Total Matches", len(df_fip))

            tab1, tab2, tab3 = st.tabs(["📄 Export & Preview", "🔍 Queries (Mismatches)", "⚠️ Uncollected Premiums"])
            
            with tab1:
                st.dataframe(full_report, use_container_width=True)
                col_a, col_b = st.columns(2)
                with col_a:
                    out_full = io.BytesIO()
                    with pd.ExcelWriter(out_full, engine='openpyxl') as writer: full_report.to_excel(writer, index=False)
                    st.download_button("📥 Download Full Report", data=out_full.getvalue(), file_name="Full_FIP_Report.xlsx")
                with col_b:
                    out_clean = io.BytesIO()
                    with pd.ExcelWriter(out_clean, engine='openpyxl') as writer: cleaned_report.to_excel(writer, index=False)
                    st.download_button("📥 Download Cleaned Upload", data=out_clean.getvalue(), file_name="CUNA_Portal_Upload.xlsx")

            with tab2:
                st.warning(f"Found {len(mismatches)} members missing from CUNA Bill.")
                # Now showing the Name column using the Activity report backup
                st.dataframe(mismatches[[ac_col, 'Display_Name', 'Numeric_Amt']], use_container_width=True)

            with tab3:
                st.error(f"Found {len(ghosts)} members billed by CUNA with no payment found.")
                st.dataframe(ghosts[['Join_ID', 'CUNA_Name', 'CUNA_Amt']], use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")

st.markdown("---")
st.caption("FIP Reconciliation Tool - Version 24.2")
