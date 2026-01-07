import streamlit as st
import pandas as pd
from datetime import datetime

# --- 1. PAGE CONFIG ---
st.set_page_config(
    page_title="TotalPower FIP Manager", 
    page_icon="🏦", 
    layout="wide"
)

# Minimal CSS to style the metrics and layout without breaking theme colors
st.markdown("""
    <style>
    /* Professional styling for the metric boxes */
    [data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.05);
        padding: 15px;
        border-radius: 10px;
        border: 1px solid rgba(128, 128, 128, 0.2);
    }
    
    /* Ensure the main area has a slight distinction from the background */
    .block-container {
        padding-top: 2rem;
    }
    </style>
    """, unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def clean_acno(series):
    return pd.to_numeric(series, errors='coerce').fillna(0).astype(int)

def find_header_and_read(file, target_keywords):
    file.seek(0)
    content = file.getvalue().decode('utf-8', errors='ignore').splitlines()
    header_row = 0
    for i, line in enumerate(content[:25]):
        if any(key.lower() in line.lower() for key in target_keywords):
            header_row = i
            break
    file.seek(0)
    df = pd.read_csv(file, header=header_row)
    df.columns = [str(c).strip() for c in df.columns]
    return df

# --- 2. SIDEBAR (Standard Theme Mode) ---
with st.sidebar:
    try:
        st.image("logo.png", width=200)
    except:
        st.title("🏢 TOTAL POWER")
    
    st.markdown("---")
    st.header("📂 1. Setup Data")
    master_file = st.file_uploader("Upload Master List CSV", type=['csv'])
    
    st.markdown("---")
    st.header("💰 2. Management Controls")
    opening_bal = st.number_input("Opening Balance ($)", value=0.0, step=100.0)
    top_x_count = st.number_input("Show Top 'X' Delinquents", value=20, step=5)
    
    st.markdown("---")
    st.caption("🔒 **Security Note:** Data is processed in-memory and is not stored on the server.")

# --- 3. MAIN PAGE HEADER ---
col_h1, col_h2 = st.columns([3, 1])
with col_h1:
    st.title("🏦 FIP Management Dashboard")
    st.markdown("### Member Reconciliation & Financial Audit Portal")
with col_h2:
    st.write(f"**Run Date:** {datetime.now().strftime('%d %b %Y')}")
    st.write(f"**Status:** 🟢 System Active")

if not master_file:
    st.info("👋 Welcome! Please upload the Master List in the sidebar to begin.")
    st.stop()

try:
    df_master = find_header_and_read(master_file, ['AcNo', 'Name'])
    df_master['Match_ID'] = clean_acno(df_master['AcNo'])
except Exception as e:
    st.error(f"Error loading Master List: {e}")
    st.stop()

# --- 4. FILE UPLOADS ---
st.markdown("---")
st.subheader("📁 Upload Monthly Files")
col_u1, col_u2 = st.columns(2)
with col_u1:
    cuna_file = st.file_uploader("Upload CUNA (Billing File)", type=['csv'])
with col_u2:
    pmts_file = st.file_uploader("Upload PMTS (Payment File)", type=['csv'])

if cuna_file and pmts_file:
    try:
        df_cuna = find_header_and_read(cuna_file, ['ACCT_NR', 'PREM'])
        acct_col = [c for c in df_cuna.columns if 'ACCT' in c.upper() or 'ACCT_NR' in c.upper()][0]
        prem_col = [c for c in df_cuna.columns if 'PREM' in c.upper()][0]
        df_cuna['Match_ID'] = clean_acno(df_cuna[acct_col])
        df_cuna['Amount'] = pd.to_numeric(df_cuna[prem_col], errors='coerce').fillna(0)
        bill_totals = df_cuna.groupby('Match_ID')['Amount'].sum().reset_index(name='Billed')

        df_pmts = find_header_and_read(pmts_file, ['AcNo', 'Cr Amt'])
        df_pmts['Match_ID'] = clean_acno(df_pmts['AcNo'])
        cr_cols = [c for c in df_pmts.columns if "Cr Amt" in str(c)]
        df_pmts['Total_Pay'] = df_pmts[cr_cols].apply(pd.to_numeric, errors='coerce').fillna(0).sum(axis=1)
        pay_totals = df_pmts.groupby('Match_ID')['Total_Pay'].sum().reset_index(name='Paid')

        report = df_master[['AcNo', 'Name', 'Match_ID']].copy()
        report = report.merge(bill_totals, on='Match_ID', how='left').fillna(0)
        report = report.merge(pay_totals, on='Match_ID', how='left').fillna(0)
        report['Difference'] = (report['Paid'] - report['Billed']).round(2)
        
        underpaid_all = report[report['Difference'] < -0.01].sort_values(by='Difference')
        overpaid_all = report[report['Difference'] > 0.01].sort_values(by='Difference', ascending=False)
        top_x_df = underpaid_all.head(int(top_x_count))

        total_billed = report['Billed'].sum()
        total_paid = report['Paid'].sum()
        closing_bal = (opening_bal + total_paid) - total_billed

        st.markdown("---")
        st.subheader("📊 Financial Summary")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Opening Balance", f"${opening_bal:,.2f}")
        m2.metric("Total Collected", f"${total_paid:,.2f}")
        m3.metric("Total Billed", f"-${total_billed:,.2f}", delta_color="inverse")
        m4.metric("Estimated Closing", f"${closing_bal:,.2f}")

        if not top_x_df.empty:
            st.markdown("---")
            st.subheader(f"⚠️ Top {int(top_x_count)} Delinquent Accounts")
            chart_data = top_x_df.set_index('Name')['Difference'].abs()
            st.bar_chart(chart_data)

        st.markdown("---")
        st.subheader("🔍 Member Detailed Lookup")
        search_query = st.text_input("Search by Name or Account Number", "")
        display_df = report.copy()
        if search_query:
            display_df = display_df[
                (display_df['Name'].str.contains(search_query, case=False, na=False)) |
                (display_df['AcNo'].astype(str).str.contains(search_query))
            ]
        st.dataframe(display_df[['AcNo', 'Name', 'Billed', 'Paid', 'Difference']], use_container_width=True)

        st.markdown("---")
        st.subheader("📥 Export Final Reports")
        d1, d2, d3 = st.columns(3)
        d1.download_button(label="🔴 Underpaid List", data=underpaid_all.to_csv(index=False), file_name="Underpaid.csv", use_container_width=True)
        d2.download_button(label="🟢 Overpaid List", data=overpaid_all.to_csv(index=False), file_name="Overpaid.csv", use_container_width=True)
        d3.download_button(label="📄 Full Audit Report", data=report.to_csv(index=False), file_name="Full_Audit.csv", use_container_width=True)

    except Exception as e:
        st.error(f"Processing Error: {e}")

st.markdown("---")
st.markdown("<p style='text-align: center; color: grey;'>Total Power Ltd - Internal Reconciliation System</p>", unsafe_allow_html=True)
