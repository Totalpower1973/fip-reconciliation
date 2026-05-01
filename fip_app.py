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
        st.caption("Triple Reconciliation: Full Audit, Portal Upload, & Discrepancy Tracking")
except FileNotFoundError:
    st.title("FIP Recon Tool V24")

st.divider()

# --- HELPER FUNCTIONS ---

def load_generic_file(file):
    if file.name.endswith('.csv'):
        try:
            return pd.read_csv(file, header=None, encoding='utf-8')
        except UnicodeDecodeError:
            return pd.read_csv(file, header=None, encoding='ISO-8859-1')
    return pd.read_excel(file, header=None)

def header_hunter(file):
    raw = load_generic_file(file)
    header_row_index = 0
    # Scan for common headers to identify the start of data
    for i, row in raw.head(50).iterrows():
        vals = [str(v).strip().lower() for v in row.values]
        if any(keyword in vals for keyword in ['acno', 'name', 'acct_nr', 'cert_num']):
            header_row_index = i
            break
            
    df = raw.iloc[header_row_index:].copy()
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
    # Filter out empty rows at the bottom
    df = df[df.iloc[:, 0].astype(str).str.len() > 0]
    
    cols = pd.Series(df.columns)
    for dup in cols[cols.duplicated()].unique(): 
        cols[cols == dup] = [f"{dup}_{i}" if i != 0 else dup for i in range(sum(cols == dup))]
    df.columns = cols
    return df

FIP_AMOUNTS = [52.80, 63.40, 79.20, 79.30, 95.10, 105.60, 126.80, 158.40, 190.20, 198.30, 253.60, 261.70, 323.60, 325.10, 380.40, 396.60, 412.10, 472.90, 528.00, 555.10, 634.00, 826.00]

# --- FILE UPLOADS ---
u1, u2, u3 = st.columns(3)
with u1:
    act_file = st.file_uploader("📂 Activity Report (BECU Collected)", type=['csv', 'xlsx', 'xls'])
with u2:
    cuna_file = st.file_uploader("📂 CUNA Billing File", type=['csv', 'xlsx', 'xls'])
with u3:
    so_file = st.file_uploader("📂 Standing Orders (CU Setup)", type=['csv', 'xlsx', 'xls'])

if act_file and cuna_file:
    try:
        df_act = header_hunter(act_file)
        df_cuna = header_hunter(cuna_file)

        # 1. PRE-PROCESS NAMES & IDS
        name_act_col = next((c for c in df_act.columns if 'name' in c.lower() and 'extra' not in c.lower()), df_act.columns[1])
        df_act['Activity_Name'] = df_act[name_act_col].astype(str).str.upper()

        fname_col = next((c for c in df_cuna.columns if 'fname' in c.lower()), None)
        lname_col = next((c for c in df_cuna.columns if 'lname' in c.lower()), None)
        if fname_col and lname_col:
            df_cuna['CUNA_Name'] = (df_cuna[fname_col].astype(str) + " " + df_cuna[lname_col].astype(str)).str.upper().replace('NAN', '').str.strip()
        else:
            alt_name = next((c for c in df_cuna.columns if 'name' in c.lower()), df_cuna.columns[1])
            df_cuna['CUNA_Name'] = df_cuna[alt_name].astype(str).str.upper()

        ac_col = next((c for c in df_act.columns if 'acno' in c.lower() or 'acct_nr' in c.lower()), df_act.columns[0])
        best_act_col = next((c for c in df_act.columns if pd.to_numeric(df_act[c], errors='coerce').isin(list(FIP_AMOUNTS)).any()), df_act.columns[-1])
        cuna_prem_col = next((c for c in df_cuna.columns if 'curr' in c.lower() and 'prem' in c.lower()), df_cuna.columns[-1])
        prod_col = next((c for c in df_cuna.columns if 'product' in c.lower()), None)

        if st.button("🚀 Run Reconciliation"):
            # Payments Logic (Activity)
            df_act['Numeric_Amt'] = pd.to_numeric(df_act[best_act_col], errors='coerce').fillna(0)
            df_fip_payments = df_act[df_act['Numeric_Amt'].isin(list(FIP_AMOUNTS))].copy()
            df_fip_payments['Join_ID'] = df_fip_payments[ac_col].astype(str).str.split('.').str[0].str.lstrip('0').str.strip()
            df_fip_summary = df_fip_payments.groupby('Join_ID').agg({'Numeric_Amt': 'sum', 'Activity_Name': 'first'}).reset_index()

            # Master List Logic (CUNA) - Clean Total/NaN Rows
            cuna_id_col = next(c for c in df_cuna.columns if 'acct_nr' in str(c).lower())
            cert_col = next(c for c in df_cuna.columns if 'cert_num' in str(c).lower())
            df_cuna_clean = df_cuna.dropna(subset=[cuna_id_col]).copy()
            df_cuna_clean['Join_ID'] = df_cuna_clean[cuna_id_col].astype(str).str.split('.').str[0].str.lstrip('0').str.strip()

            # --- THE MASTER MERGE (Side-by-Side) ---
            merged = pd.merge(df_cuna_clean[['Join_ID', cert_col, 'PLAN', 'CUNA_Name', cuna_prem_col, prod_col]], df_fip_summary, on='Join_ID', how='left')
            merged['Numeric_Amt'] = merged['Numeric_Amt'].fillna(0)

            # --- DISCREPANCY DATASETS ---
            df_queries = df_fip_summary[~df_fip_summary['Join_ID'].isin(df_cuna_clean['Join_ID'])].copy()
            df_uncollected = merged[merged['Numeric_Amt'] == 0].copy()

            # --- UI DASHBOARD ---
            st.subheader("📊 Reconciliation Overview")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("CUNA Billed Total", f"${pd.to_numeric(df_cuna_clean[cuna_prem_col], errors='coerce').sum():,.2f}")
            m2.metric("Total Collected", f"${merged['Numeric_Amt'].sum():,.2f}")
            m3.metric("Queries (Investigate)", len(df_queries))
            m4.metric("Uncollected (0.00)", len(df_uncollected))

            # --- TABS FOR WORKFLOW ---
            tab1, tab2, tab3, tab4 = st.tabs(["📥 Final Downloads", "🔍 Queries (Paid/Not Billed)", "⚠️ Uncollected (Billed/Not Paid)", "📋 Audit Preview"])
            
            with tab1:
                col_a, col_b = st.columns(2)
                with col_a:
                    st.info("Full Side-by-Side Audit")
                    audit_out = merged.copy()
                    audit_out.rename(columns={'Numeric_Amt': 'BECU_PAID', cuna_prem_col: 'CUNA_BILLED'}, inplace=True)
                    out_audit = io.BytesIO()
                    with pd.ExcelWriter(out_audit, engine='openpyxl') as writer: audit_out.to_excel(writer, index=False)
                    st.download_button("📥 Download Audit File", data=out_audit.getvalue(), file_name="Full_Audit_Report.xlsx")

                with col_b:
                    st.success("Clean Portal Upload (All Billed Accounts)")
                    portal_out = merged[['Join_ID', 'CUNA_Name', 'PLAN', 'Numeric_Amt', cert_col]].copy()
                    portal_out.columns = ['ACCT_NR', 'NAME', 'PLAN', 'PREMIUM_PAID', 'CERT_NUM']
                    out_portal = io.BytesIO()
                    with pd.ExcelWriter(out_portal, engine='openpyxl') as writer: portal_out.to_excel(writer, index=False)
                    st.download_button("📥 Download Portal File", data=out_portal.getvalue(), file_name="CUNA_Portal_Final.xlsx")

            with tab2:
                st.warning(f"Found {len(df_queries)} members who paid FIP but are missing from the CUNA Bill.")
                st.dataframe(df_queries, use_container_width=True)

            with tab3:
                st.error(f"Found {len(df_uncollected)} members billed by CUNA with $0.00 collected.")
                st.dataframe(df_uncollected[['Join_ID', 'CUNA_Name', prod_col, cuna_prem_col]], use_container_width=True)
            
            with tab4:
                st.write("Live Preview of Master Reconciliation Table")
                st.dataframe(merged, use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")

st.markdown("---")
st.caption("FIP Reconciliation Tool - Version 24.37 (Complete Dashboard Edition)")
