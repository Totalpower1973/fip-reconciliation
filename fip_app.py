import streamlit as st
import pandas as pd
import io
from PIL import Image

st.set_page_config(page_title="FIP Recon Tool V24", layout="wide")

# --- BRANDING & LOGO SECTION ---
try:
    # Using the BECU logo
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
        # Added low_memory=False and specific encoding for cloud compatibility
        try:
            df_raw = pd.read_csv(file, header=None, encoding='utf-8')
        except UnicodeDecodeError:
            df_raw = pd.read_csv(file, header=None, encoding='ISO-8859-1')
    else:
        df_raw = pd.read_excel(file, header=None)
    
    header_row_index = 0
    # Scan first 20 rows to find the header
    for i, row in df_raw.head(20).iterrows():
        vals = [str(v).strip().lower() for v in row.values]
        if any(keyword in vals for keyword in ['acno', 'name', 'acct_nr', 'cert_num']):
            header_row_index = i
            break
            
    df = df_raw.iloc[header_row_index:].copy()
    
    # Improved column identification logic
    new_cols = []
    for i, col in enumerate(df.iloc[0]):
        val = str(col).strip()
        # Robust check for empty headers which often cause issues on Cloud
        if val.lower() in ['nan', '', 'none', 'unnamed:']:
            new_cols.append(f"Col_Index_{i}")
        else:
            new_cols.append(val)
            
    df.columns = new_cols
    df = df[1:].reset_index(drop=True)
    df.columns = [str(c).strip() for c in df.columns]
    
    # Filter out empty rows
    df = df[df.iloc[:, 0].astype(str).str.len() > 0]
    
    # Filter for Plan records
    plan_col = next((c for c in df.columns if 'plan' in c.lower()), None)
    if plan_col:
        df = df[df[plan_col].astype(str).str.contains("Plan", case=False, na=False)]
    
    # De-duplicate column names
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

        # DEBUG: Uncomment the line below if names still don't show to see detected columns
        # st.write("Detected Columns:", df_act.columns.tolist())

        # Name Logic (Improved detection)
        # Look for 'name' but avoid 'extra' or generic 'Col_Index'
        name_options = [c for c in df_act.columns if 'name' in c.lower() and 'col_index' not in c.lower()]
        name_main = name_options[0] if name_options else df_act.columns[1]
        
        # Look for potential overflow name columns
        name_extra = next((c for c in df_act.columns if 'col_index' in c.lower() or 'extra' in c.lower()), None)
        
        if name_extra and name_extra != name_main:
            df_act['Full_Name'] = df_act[name_main].astype(str).replace('nan', '') + " " + \
                                  df_act[name_extra].astype(str).replace('nan', '')
            df_act['Full_Name'] = df_act['Full_Name'].str.strip()
        else:
            df_act['Full_Name'] = df_act[name_main].astype(str).replace('nan', 'Unknown Name')

        ac_col = next((c for c in df_act.columns if 'acno' in c.lower() or 'acct_nr' in c.lower()), df_act.columns[0])
        best_act_col = next((c for c in df_act.columns if pd.to_numeric(df_act[c], errors='coerce').isin(FIP_AMOUNTS).any()), df_act.columns[-1])
        cuna_prem_col = next((c for c in df_cuna.columns if 'curr' in c.lower() and 'prem' in c.lower()), df_cuna.columns[13])

        if st.button("🚀 Process Reports"):
            df_act['Numeric_Amt'] = pd.to_numeric(df_act[best_act_col], errors='coerce').fillna(0)
            df_fip = df_act[df_act['Numeric_Amt'].isin(FIP_AMOUNTS)].copy()
            df_fip['Join_ID'] = df_fip[ac_col].astype(str).str.split('.').str[0].str.lstrip('0')

            df_cuna['CUNA_Amt'] = pd.to_numeric(df_cuna[cuna_prem_col], errors='coerce').fillna(0)
            cuna_id_col = next(c for c in df_cuna.columns if 'acct_nr' in str(c).lower())
            cert_col = next(c for c in df_cuna.columns if 'cert_num' in str(c).lower())
            df_cuna['Join_ID'] = df_cuna[cuna_id_col].astype(str).str.split('.').str[0].str.lstrip('0')

            total_collected = df_fip['Numeric_Amt'].sum()
            total_billed = df_cuna['CUNA_Amt'].sum()

            st.subheader("📊 Financial Dashboard")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("BECU Collected", f"${total_collected:,.2f}")
            m2.metric("CUNA Billed", f"${total_billed:,.2f}")
            m3.metric("Net Variance", f"${total_collected - total_billed:,.2f}")
            m4.metric("Total Matches", len(df_fip))

            merged = pd.merge(df_fip, df_cuna[['Join_ID', cert_col, 'PLAN']], on='Join_ID', how='left')
            ghosts = df_cuna[~df_cuna['Join_ID'].isin(df_fip['Join_ID'])].copy()
            mismatches = merged[merged[cert_col].isna()]

            full_report = pd.DataFrame()
            full_report['ACCT_NR'] = merged[ac_col]
            full_report['NAME'] = merged['Full_Name']
            full_report['PLAN'] = merged['PLAN']
            full_report['PREMIUM_AMT'] = merged['Numeric_Amt']
            full_report['CERT_NUM'] = merged[cert_col]
            
            cleaned_report = full_report[full_report['CERT_NUM'].notna()].copy()

            tab1, tab2, tab3 = st.tabs(["📄 Export & Preview", "🔍 Queries (Mismatches)", "⚠️ Uncollected Premiums"])
            
            with tab1:
                st.write("### Data Preview (Full List)")
                st.dataframe(full_report, use_container_width=True)
                st.divider()
                col_a, col_b = st.columns(2)
                with col_a:
                    st.info(f"**Internal Report**\n{len(full_report)} records")
                    out_full = io.BytesIO()
                    with pd.ExcelWriter(out_full, engine='openpyxl') as writer: 
                        full_report.to_excel(writer, index=False)
                    st.download_button("📥 Download Full Report", data=out_full.getvalue(), file_name="Full_FIP_Report.xlsx")
                with col_b:
                    st.success(f"**CUNA Upload**\n{len(cleaned_report)} records")
                    out_clean = io.BytesIO()
                    with pd.ExcelWriter(out_clean, engine='openpyxl') as writer: 
                        cleaned_report.to_excel(writer, index=False)
                    st.download_button("📥 Download Cleaned Upload", data=out_clean.getvalue(), file_name="CUNA_Portal_Upload.xlsx")

            with tab2:
                st.warning(f"Found {len(mismatches)} members paying premiums missing from CUNA Bill.")
                st.dataframe(mismatches[[ac_col, 'Full_Name', 'Numeric_Amt']], use_container_width=True)

            with tab3:
                st.error(f"Found {len(ghosts)} members billed by CUNA where no payment was found.")
                # Fallback for CUNA names if specific columns are missing
                cuna_name_cols = [c for c in ghosts.columns if 'name' in c.lower()]
                st.dataframe(ghosts[cuna_name_cols + ['CUNA_Amt']], use_container_width=True)

    except Exception as e:
        st.error(f"Error processing reports: {e}")
        st.exception(e) # Provides a traceback for easier debugging

# --- FOOTER ---
st.markdown("---")
st.caption("FIP Reconciliation Tool - Version 24")
