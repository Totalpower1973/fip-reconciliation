import streamlit as st
import pandas as pd
from datetime import datetime

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

# --- APP LAYOUT ---
st.set_page_config(page_title="FIP Reconciliation Tool", layout="wide")
st.title("🏦 FIP Management Dashboard (V7)")

with st.sidebar:
    st.header("1. Setup")
    master_file = st.file_uploader("Upload Master List CSV", type=['csv'])
    st.markdown("---")
    st.header("2. Financials")
    opening_bal = st.number_input("Enter Opening Balance ($)", value=0.0, step=100.0)
    
    st.markdown("---")
    st.header("3. Delinquency Filter")
    # NEW: Threshold Input
    threshold = st.number_input("Show shortfalls greater than ($):", value=0.0, step=10.0)
    # NEW: Count Input for Chart
    top_n = st.number_input("Number of accounts for chart:", value=10, step=5)

if master_file:
    try:
        df_master = find_header_and_read(master_file, ['AcNo', 'Name'])
        df_master['Match_ID'] = clean_acno(df_master['AcNo'])
    except Exception as e:
        st.error(f"Master List Error: {e}")
        st.stop()
else:
    st.info("Please upload the Master List to start.")
    st.stop()

st.header("4. Monthly Processing")
col1, col2 = st.columns(2)
with col1:
    cuna_file = st.file_uploader("Upload CUNA (Billing)", type=['csv'])
with col2:
    pmts_file = st.file_uploader("Upload PMTS (Payments)", type=['csv'])

if cuna_file and pmts_file:
    try:
        # --- PROCESS BILLING & PAYMENTS ---
        df_cuna = find_header_and_read(cuna_file, ['ACCT_NR', 'PREM'])
        acct_col = [c for c in df_cuna.columns if 'ACCT' in c.upper()][0]
        prem_col = [c for c in df_cuna.columns if 'PREM' in c.upper()][0]
        df_cuna['Match_ID'] = clean_acno(df_cuna[acct_col])
        df_cuna['Amount'] = pd.to_numeric(df_cuna[prem_col], errors='coerce').fillna(0)
        bill_totals = df_cuna.groupby('Match_ID')['Amount'].sum().reset_index(name='Billed')

        df_pmts = find_header_and_read(pmts_file, ['AcNo', 'Cr Amt'])
        df_pmts['Match_ID'] = clean_acno(df_pmts['AcNo'])
        cr_cols = [c for c in df_pmts.columns if "Cr Amt" in str(c)]
        df_pmts['Total_Pay'] = df_pmts[cr_cols].apply(pd.to_numeric, errors='coerce').fillna(0).sum(axis=1)
        pay_totals = df_pmts.groupby('Match_ID')['Total_Pay'].sum().reset_index(name='Paid')

        # --- MERGE & ANALYZE ---
        report = df_master[['AcNo', 'Name', 'Match_ID']].copy()
        report = report.merge(bill_totals, on='Match_ID', how='left').fillna(0)
        report = report.merge(pay_totals, on='Match_ID', how='left').fillna(0)
        report['Difference'] = (report['Paid'] - report['Billed']).round(2)
        report['Run_Date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # --- FILTERED LISTS ---
        # "Difference" is negative for underpaid. 
        # We want to find people where the shortfall (abs value) is bigger than threshold.
        underpaid_filtered = report[report['Difference'] <= -threshold]
        overpaid = report[report['Difference'] > 0.01]

        # --- FINANCIAL SUMMARY ---
        total_billed = report['Billed'].sum()
        total_paid = report['Paid'].sum()
        closing_bal = (opening_bal + total_paid) - total_billed

        st.markdown("---")
        st.subheader("📊 Financial Overview")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Opening Balance", f"${opening_bal:,.2f}")
        m2.metric("Total Collected", f"${total_paid:,.2f}")
        m3.metric("Total Billed", f"-${total_billed:,.2f}", delta_color="inverse")
        m4.metric("Closing Balance", f"${closing_bal:,.2f}")

        # --- VISUALIZATION: DYNAMIC TOP N ---
        st.markdown("---")
        chart_list = report[report['Difference'] < -0.01].sort_values(by='Difference').head(int(top_n))
        if not chart_list.empty:
            st.subheader(f"⚠️ Top {int(top_n)} Shortfalls")
            chart_data = chart_list.set_index('Name')['Difference'].abs()
            st.bar_chart(chart_data)
        
        # --- SEARCH & TABLE ---
        st.markdown("---")
        st.subheader(f"📋 Delinquent Accounts (Shortfall >= ${threshold:,.2f})")
        
        display_df = underpaid_filtered.copy()
        search_query = st.text_input("🔍 Search within this list (Name or Account)", "")
        
        if search_query:
            display_df = display_df[
                (display_df['Name'].str.contains(search_query, case=False, na=False)) |
                (display_df['AcNo'].astype(str).str.contains(search_query))
            ]
        
        st.dataframe(display_df[['AcNo', 'Name', 'Billed', 'Paid', 'Difference']], use_container_width=True)

        # --- EXPORTS ---
        st.subheader("📥 Export Final Reports")
        d1, d2, d3 = st.columns(3)
        # The download button now honors the threshold you set!
        d1.download_button(f"🔴 Underpaid (Threshold: ${threshold})", underpaid_filtered.to_csv(index=False), "Filtered_Underpaid.csv", use_container_width=True)
        d2.download_button("🟢 Overpaid (Credits)", overpaid.to_csv(index=False), "Overpaid_FIP.csv", use_container_width=True)
        d3.download_button("📄 Full Management Report", report.to_csv(index=False), "Full_Report.csv", use_container_width=True)

    except Exception as e:
        st.error(f"Error: {e}")