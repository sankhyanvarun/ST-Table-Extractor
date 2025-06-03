# File: streamlit_app.py

import os
import re
import csv
import tempfile
import base64

import pandas as pd
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
import streamlit as st

# ─── Configuration ────────────────────────────────────────────────────────────

POPPLER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poppler", "bin")
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


# ─── Helper Functions (from your original Flask code) ─────────────────────────

def get_poppler_path():
    return POPPLER_PATH

def convert_hindi_digits(text: str) -> str:
    hindi_digits = {
        "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
        "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
    }
    return "".join(hindi_digits.get(ch, ch) for ch in text)

def extract_text_from_pdf(pdf_path: str, lang: str = "eng") -> str:
    text = ""
    poppler_path = get_poppler_path()

    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        num_pages = len(reader.pages)

        for page_num in range(num_pages):
            page = reader.pages[page_num]
            page_text = page.extract_text() or ""

            if not page_text.strip():
                try:
                    images = convert_from_path(
                        pdf_path,
                        first_page=page_num + 1,
                        last_page=page_num + 1,
                        poppler_path=(poppler_path if os.path.exists(os.path.join(poppler_path, "pdftoppm")) else None),
                        dpi=400,
                        grayscale=True,
                    )
                    if images:
                        img = images[0]
                        page_text = pytesseract.image_to_string(img, lang=lang, config="--psm 6")
                except Exception as e:
                    st.error(f"OCR failed on page {page_num+1}: {e}")
                    page_text = ""

            text += page_text + "\n"

    return text

def is_valid_page_number(page_str: str) -> bool:
    if not page_str:
        return False
    return all(ch in "0123456789०१२३४५६७८९" for ch in page_str)

def parse_toc(text: str, is_hindi: bool = False):
    entries = []

    common_patterns = [
        r"^(.*?)[\s\.\-]+(\d+)\s*$",
        r"^(.*?)[\s\-\_]+(\d+)\s*$",
        r"^\s*(\d+\..*?)[\s\.\-]+(\d+)\s*$",
    ]

    hindi_patterns = [
        r"^\s*([०१२३४५६७८९]+\.\s+.*?)[\s\.\-]*([०१२३४५६७८९\d]+)\s*$",
        r"^(.*?)[\s\-\—]+([०१२३४५६७८९\d]+)\s*$",
        r"^(.*?)[\s\.]+([०१२३४५६७८९\d]+)\s*$",
        r"^(.*?(?:अध्याय|खंड|परिशिष्ट|प्रस्तावना|भाग|अनुभाग|प्रकरण)\s*[०१२३४५६७८९]*[\.\:\-]?\s*.*?)[\s\.\-]*([०१२३४५६७८९\d]+)\s*$",
        r"^(.*?)\s+([०१२३४५६७८९\d]+)$",
    ]

    patterns = hindi_patterns if is_hindi else common_patterns
    skip_terms_eng = ["table of contents", "contents", "page", "chap"]
    skip_terms_hindi = ["विषय सूची", "अनुक्रमणिका", "सामग्री", "पृष्ठ", "अध्याय"]
    skip_terms = skip_terms_hindi if is_hindi else skip_terms_eng

    for line in text.split("\n"):
        line = line.strip()
        if not line or len(line) < 5:
            continue
        if any(term in line.lower() for term in skip_terms):
            continue

        for pattern in patterns:
            match = re.match(pattern, line, re.IGNORECASE | re.UNICODE)
            if not match:
                continue

            groups = match.groups()
            if len(groups) == 2:
                chapter = groups[0].strip()
                page = groups[1].strip()
            elif len(groups) == 3:
                chapter = f"{groups[0]} {groups[1]}".strip()
                page = groups[2].strip()
            else:
                continue

            if is_valid_page_number(page):
                page = convert_hindi_digits(page)
                entries.append({"chapter": chapter, "page": page})
                break
            else:
                fallback = re.search(r"(\d+|[०१२३४५६७८९]+)$", line)
                if fallback:
                    page = fallback.group(1)
                    if is_valid_page_number(page):
                        chapter = line[: fallback.start()].strip()
                        page = convert_hindi_digits(page)
                        entries.append({"chapter": chapter, "page": page})
                        break

    return entries


# ─── Streamlit UI ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="PDF TOC Extractor", layout="centered")
st.title("📄 PDF TOC Extractor")

st.write(
    """
    1. Upload a PDF.  
    2. Use the Zoom slider to preview it.  
    3. Click “Extract TOC” → the app will parse and display it in an editable table.  
    4. Optionally add rows/columns at any index.  
    5. Finally, download a CSV named after your PDF.
    """
)

# — Step 1: File Uploader & Zoom Slider —────────────────────────────────────────

uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])
zoom_pct = st.slider("Preview Zoom (%)", min_value=50, max_value=200, value=100, step=10)

if uploaded_file:
    # Display PDF preview inside an <iframe> with zoom scaled by zoom_pct
    pdf_bytes = uploaded_file.read()
    b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    iframe_width = int(700 * (zoom_pct / 100))
    iframe_height = 800

    st.markdown(
        f"""
        <iframe
            src="data:application/pdf;base64,{b64_pdf}"
            width="{iframe_width}px"
            height="{iframe_height}px"
            style="border: none;"
        ></iframe>
        """,
        unsafe_allow_html=True,
    )

    if "raw_pdf_bytes" not in st.session_state:
        st.session_state["raw_pdf_bytes"] = pdf_bytes

    # — Step 2: Extract TOC Button —───────────────────────────────────────────

    language = st.selectbox("OCR Language (if needed)", ("eng", "hin", "both"))
    if st.button("Extract TOC"):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(st.session_state["raw_pdf_bytes"])
            tmp_path = tmp.name

        is_hindi = (language == "hin" or language == "both")
        ocr_lang = "eng+hin" if language == "both" else language

        try:
            raw_text = extract_text_from_pdf(tmp_path, lang=ocr_lang)
            toc_list = parse_toc(raw_text, is_hindi=is_hindi)

            if not toc_list:
                st.warning("No TOC entries detected.")
            else:
                df = pd.DataFrame(toc_list)
                st.session_state["df"] = df

        except Exception as e:
            st.error(f"Extraction error: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            st.stop()
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

# — Step 3: Editable Table & Add Row/Column —─────────────────────────────────

if "df" in st.session_state:
    st.subheader("🔧 Editable Table of Contents")
    df = st.session_state["df"]

    # Show the editable DataFrame (using st.data_editor instead of st.experimental_data_editor)
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    st.session_state["df"] = edited_df

    st.markdown("---")

    # — Add a blank row at chosen index ───────────────────────────────────────
    st.write("### ➕ Add a Blank Row")
    max_row_idx = len(st.session_state["df"])
    # Give the number_input its own key so we can read it on button click
    st.number_input(
        "Insert new row at index (0-based)", 
        min_value=0, max_value=max_row_idx, value=max_row_idx, step=1, key="new_row_idx"
    )
    if st.button("Add Row", key="add_row_button"):
        df_current = st.session_state["df"]
        new_row_idx = st.session_state["new_row_idx"]

        # Create a one-row DataFrame of empty strings matching columns
        blank_row = pd.DataFrame({col: [""] for col in df_current.columns})

        # Split and concatenate at new_row_idx
        top = df_current.iloc[: new_row_idx].reset_index(drop=True)
        bottom = df_current.iloc[new_row_idx :].reset_index(drop=True)
        new_df = pd.concat([top, blank_row, bottom], ignore_index=True)

        st.session_state["df"] = new_df
        st.experimental_rerun()

    st.markdown("----")

    # — Add a blank column at chosen index ──────────────────────────────────
    st.write("### ➕ Add a Blank Column")
    new_col_name = st.text_input("New column name", value="", key="new_col_name")
    max_col_idx = len(st.session_state["df"].columns)
    st.number_input(
        "Insert new column at index (0-based)", 
        min_value=0, max_value=max_col_idx, value=max_col_idx, step=1, key="new_col_idx"
    )
    if st.button("Add Column", key="add_col_button"):
        if st.session_state["new_col_name"].strip() == "":
            st.error("Column name cannot be empty.")
        else:
            df_current = st.session_state["df"]
            new_col_idx = st.session_state["new_col_idx"]
            col_name = st.session_state["new_col_name"]

            df_current.insert(new_col_idx, col_name, "")
            st.session_state["df"] = df_current
            st.experimental_rerun()

    st.markdown("---")

    # — Step 4: Download as CSV with PDF name ────────────────────────────────
    st.write("### 💾 Download CSV")

    original_pdf_name = uploaded_file.name
    base_name = os.path.splitext(original_pdf_name)[0]
    csv_filename = f"{base_name}.csv"

    final_df = st.session_state["df"]
    csv_data = final_df.to_csv(index=False).encode("utf-8")

    st.download_button(
        label="Download TOC as CSV",
        data=csv_data,
        file_name=csv_filename,
        mime="text/csv",
    )
