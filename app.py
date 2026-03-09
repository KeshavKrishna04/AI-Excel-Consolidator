import streamlit as st
import pandas as pd
import os
import tempfile
import io
import contextlib
import time

from main import run_pipeline


# --------------------------------------------------
# Page Config
# --------------------------------------------------
st.set_page_config(
    page_title="AI Data Consolidator",
    page_icon="📊",
    layout="wide"
)

# --------------------------------------------------
# Soft UI Styling (easy on eyes)
# --------------------------------------------------
st.markdown("""
<style>
.stApp {
    background-color: #f6f7fb;
}

.log-box {
    background-color: #0f172a;
    color: #e5e7eb;
    padding: 16px;
    border-radius: 8px;
    font-family: monospace;
    font-size: 13px;
    line-height: 1.6;
    max-height: 420px;
    overflow-y: auto;
}

.section-card {
    background-color: white;
    padding: 20px;
    border-radius: 10px;
    border: 1px solid #e5e7eb;
    margin-bottom: 20px;
}

.badge {
    display: inline-block;
    padding: 6px 12px;
    border-radius: 999px;
    background-color: #eef2ff;
    color: #3730a3;
    font-weight: 600;
    font-size: 13px;
}
</style>
""", unsafe_allow_html=True)


# --------------------------------------------------
# Header
# --------------------------------------------------
st.title("AI Data Consolidator")
st.markdown(
    "Consolidate **Sales, Nielsen, Pricing, Competitor & Baseline** Excel data "
    "using AI-powered schema intelligence."
)

st.markdown("---")


# --------------------------------------------------
# Upload Section
# --------------------------------------------------
st.markdown('<div class="section-card">', unsafe_allow_html=True)
st.subheader("Upload Excel Files")

domains = ["sales", "nielsen", "pricing", "competitor", "baseline"]
uploaded_files = {}

cols = st.columns(2)
for i, domain in enumerate(domains):
    with cols[i % 2]:
        uploaded_files[domain] = st.file_uploader(
            f"{domain.capitalize()} File",
            type=["xlsx", "xls"],
            key=domain
        )
st.markdown('</div>', unsafe_allow_html=True)


# --------------------------------------------------
# Run Pipeline
# --------------------------------------------------
if st.button("🚀 Consolidate Data", use_container_width=True):

    provided = {d: f for d, f in uploaded_files.items() if f is not None}
    if not provided:
        st.error("Please upload at least one Excel file to consolidate.")
        st.stop()

    os.makedirs("outputs", exist_ok=True)

    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("🧠 AI Agent Commentary (Live)")
    log_placeholder = st.empty()
    st.markdown('</div>', unsafe_allow_html=True)

    # ✅ FIX: use mutable list instead of nonlocal
    log_buffer = []

    def write_log(line: str):
        log_buffer.append(line)
        log_placeholder.markdown(
            "<div class='log-box'>" + "\n".join(log_buffer) + "</div>",
            unsafe_allow_html=True
        )

    with tempfile.TemporaryDirectory() as temp_dir:
        vendor_files = []

        for file in provided.values():
            path = os.path.join(temp_dir, file.name)
            with open(path, "wb") as f:
                f.write(file.getbuffer())
            vendor_files.append(path)

        write_log(f"📥 Received {len(vendor_files)} file(s): " + ", ".join([os.path.basename(p) for p in vendor_files]))
        write_log("🤖 Initializing AI consolidation engine...")
        time.sleep(0.3)

        stdout_capture = io.StringIO()

        try:
            with contextlib.redirect_stdout(stdout_capture):
                run_pipeline(vendor_files)

            stdout_capture.seek(0)
            for line in stdout_capture.read().splitlines():
                write_log("• " + line)
                time.sleep(0.03)

        except Exception as e:
            write_log(f"❌ ERROR: {e}")
            st.stop()

    output_path = "outputs/consolidated_output.xlsx"

    if not os.path.exists(output_path):
        st.error("Pipeline finished but output file not found.")
        st.stop()

    write_log("✅ Consolidation completed successfully.")


    # --------------------------------------------------
    # Output Summary
    # --------------------------------------------------
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("📦 Output Summary")

    file_size_kb = os.path.getsize(output_path) / 1024
    st.markdown(f"**File size:** {file_size_kb:.2f} KB")

    excel_data = pd.read_excel(output_path, sheet_name=None)

    st.markdown(f"**Sheets generated:** {len(excel_data)}")

    summary_cols = st.columns(len(excel_data))
    for col, (sheet, df) in zip(summary_cols, excel_data.items()):
        with col:
            st.markdown(f"<span class='badge'>{sheet}</span>", unsafe_allow_html=True)
            st.metric("Rows", len(df))
            st.metric("Columns", len(df.columns))

    st.markdown('</div>', unsafe_allow_html=True)


    # --------------------------------------------------
    # Preview
    # --------------------------------------------------
    st.markdown('<div class="section-card">', unsafe_allow_html=True)
    st.subheader("🔍 Data Preview")

    tabs = st.tabs(list(excel_data.keys()))
    for tab, (sheet, df) in zip(tabs, excel_data.items()):
        with tab:
            st.dataframe(df.head(25), use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)


    # --------------------------------------------------
    # Download
    # --------------------------------------------------
    with open(output_path, "rb") as f:
        st.download_button(
            "⬇️ Download Consolidated Excel",
            f,
            file_name="consolidated_output.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
