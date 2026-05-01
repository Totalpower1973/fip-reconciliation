import streamlit as st
import pandas as pd
import io
from PIL import Image

st.set_page_config(page_title="FIP Recon Tool V24.4", layout="wide")

# --- BRANDING ---
try:
    logo_img = Image.open('becu_logo.png')
    col1, col2 = st.columns([1, 8])
    with col1:
        st.image(logo_img, width=100)
    with col2:
        st.title("FIP Recon Tool V24.4")
except:
    st.title("FIP Recon Tool V24.4")

st.divider()

def load_data(file):
    """Robust file loader for CSV/Excel with encoding fallbacks."""
    if file.name.endswith('.csv'):
        for enc in ['utf-8', 'iso-8859-1', 'cp1252']:
            try:
                file.seek(0)
                return pd.read_csv(file, header=None, encoding=enc)
            except:
                continue
    else:
        file.seek(0)
        return pd.read_excel(file, header=None)
    return None

FIP_AMOUNTS = [52.80, 63.40, 79.20, 79.30, 95.10, 105.60, 126.80, 158.40, 190.20, 198.30, 253.60, 261.70, 323.60, 325.10, 380.40, 396.60, 412.10, 472.90, 528.00, 555.10, 634.00, 826.00]

u1, u2 = st.columns(2)
with u1:
    act_file = st.file_uploader("📂 Activity Report (CUMME)", type=['csv', 'xlsx', 'xls'])
with u2:
    cuna_file = st.file_uploader("📂 CUNA Billing File", type=['csv', 'xlsx', 'xls'])

if act_file and cuna_file:
    try:
        # Load raw dataframes
        raw_act = load_data(act_file)
        raw_cuna = load_data(cuna_file)

        if st.button("🚀 Process Reports"):
            
            def process_file(df_raw, name_tag):
                """Finds headers and premium columns by scanning data content."""
                h_idx = 0
                for i, row in df_raw.head(50).iterrows():
                    vals = [str(v).lower().strip() for v in row.values]
                    if any(k in vals for k in ['acno', 'acct_nr', 'cert_num', 'name', 'fname']):
                        h_idx = i
                        break
                
                df = df_raw.iloc[h_idx:].copy()
                df.columns = [str(c).strip() for c in df.iloc[0]]
                df = df[1:].reset_index(drop=True).dropna(how='all')
                
                # Identify Premium Column by content
                prem_col = None
                nums_series = None
                for col in df.columns:
                    temp_nums = pd.to_numeric(df[col], errors='coerce')
                    if temp_nums.isin(FIP_AMOUNTS).any():
                        prem_col = col
                        nums_series = temp_nums
                        break
                
                return df, prem_col, nums_series

            # Extract structured data
            df_act, col_act, nums_act = process_file(raw_act, "Activity")
            df_cuna, col_cuna, nums_cuna = process_file(raw_cuna, "CUNA")

            # CRITICAL ERROR GATE: Prevent the "arg must be a list" crash
            if col_act is None or col_cuna is None:
                st.error("❌ **Detection Error:** The tool couldn't find a column containing FIP amounts ($52.80, $79.20, etc.).")
                if col_act is None: st.warning("Check the **Activity Report** format.")
                if col_cuna is None: st.warning("Check the **CUNA File** format.")
                st.stop()

            # --- DATA CLEANING ---
            df_act['Numeric_Amt'] = nums_act.fillna(0)
            df_cuna['CUNA_Amt'] = nums_cuna.fillna(0)
            
            # ID Normalization
            ac_key = next((c for c in df_act.columns if any(k in c.lower() for k in ['acno', 'acct_nr'])), df_act.columns[0])
            cuna_key = next((c for c in df_cuna.columns if any(k in c.lower() for k in ['acct_nr', 'id'])), df_cuna.columns[0])
            cert_key = next((c for c in df_cuna.columns if 'cert_num' in c.lower()), None)

            df_act['Join_ID'] = df_act[ac_key].astype(str).str.split('.').str[0].str.lstrip('0').str.strip()
            df_cuna['Join_ID'] = df_cuna[cuna_key].astype(str).str.split('.').str[0].str.lstrip('0').str.strip()

            # Name Handling
            name_col = next((c for c in df_act.columns if 'name' in c.lower()), None)
            df_act['NAME'] = df_act[name_col].astype(str).str.upper() if name_col else "UNKNOWN"

            # --- RECONCILIATION ---
            df_fip = df_act[df_act['Numeric_Amt'].isin(FIP_AMOUNTS)].copy()
            merged = pd.merge(df_fip, df_cuna[['Join_ID', cert_key, 'PLAN']], on='Join_ID', how='left')
            
            mismatches = merged[merged[cert_key].isna()]
            ghosts = df_cuna[~df_cuna['Join_ID'].isin(df_fip['Join_ID'])].copy()

            # --- RESULTS ---
            full_report = pd.DataFrame({
                'ACCT_NR': merged[ac_key],
                'NAME': merged['NAME'],
                'PLAN': merged.get('PLAN', 'N/A'),
                'PREMIUM': merged['Numeric_Amt'],
                'CERT_NUM': merged[cert_key]
            })

            t1, t2, t3 = st.tabs(["📄 Results", "🔍 Queries (Mismatches)", "⚠️ Uncollected"])
            with t1:
                st.dataframe(full_report, use_container_width=True)
                out = io.BytesIO()
                with pd.ExcelWriter(out, engine='openpyxl') as w: full_report.to_excel(w, index=False)
                st.download_button("📥 Download Report", data=out.getvalue(), file_name="FIP_Recon.xlsx")
            with t2:
                st.dataframe(mismatches[[ac_key, 'NAME', 'Numeric_Amt']], use_container_width=True)
            with t3:
                st.dataframe(ghosts[['Join_ID', 'CUNA_Amt']], use_container_width=True)

    except Exception as e:
        st.error(f"System Error: {e}")
