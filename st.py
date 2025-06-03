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
import streamlit.components.v1 as components  # for embedding HTML

# ─── Configuration ────────────────────────────────────────────────────────────

POPPLER_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "poppler", "bin")
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


# ─── Helper Functions ──────────────────────────────────────────────────────────

def get_poppler_path():
    return POPPLER_PATH

def convert_hindi_digits(text):
    """Convert Devanagari (Hindi) digits to Arabic numerals."""
    hindi_digits = {
        "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
        "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
    }
    return "".join(hindi_digits.get(ch, ch) for ch in text)

def extract_page_text(pdf_path, page_num, lang="eng"):
    """
    Extract text from a single page (0-based index).
    First tries PyPDF2.extract_text(); if empty, runs OCR on that page.
    """
    text = ""
    poppler_path = get_poppler_path()

    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
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
            except Exception:
                page_text = ""

        text = page_text + "\n"

    return text

def extract_text_from_pages(pdf_path, page_indices, lang="eng"):
    """
    Given a list of 0-based page indices, extract text from each page (with OCR fallback).
    Returns a single concatenated string.
    """
    accumulated = ""
    for idx in page_indices:
        accumulated += extract_page_text(pdf_path, idx, lang=lang)
    return accumulated

def extract_text_from_pdf(pdf_path, lang="eng"):
    """
    Extract text from the entire PDF by looping over all pages.
    (Same logic as extract_page_text, repeated for each page.)
    """
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
                except Exception:
                    page_text = ""

            text += page_text + "\n"

    return text

def find_toc_page_indices(pdf_path):
    """
    Scan each page’s raw text (no OCR fallback) to see if it contains 
    any TOC‐related keyword. Returns a list of 0-based page indices.
    """
    reader = PyPDF2.PdfReader(pdf_path)
    keywords = [
        "table of contents", "contents", "foreword", "preface"
    ]
    indices = []

    for i in range(len(reader.pages)):
        page = reader.pages[i]
        raw_text = page.extract_text() or ""
        lower = raw_text.lower()
        if any(kw in lower for kw in keywords):
            indices.append(i)
    return indices

def is_valid_page_number(page_str):
    """Return True if page_str has only Arabic (0–9) or Hindi (०–९) digits."""
    if not page_str:
        return False
    return all(ch in "0123456789०१२३४५६७८९" for ch in page_str)

def parse_toc(text, is_hindi=False):
    """
    Simplified TOC parser:
    - If is_hindi=False, look for English lines ending with digits (e.g., “Title … 123”).
    - If is_hindi=True, look for any line that ends with Hindi or Arabic digits.
    """
    entries = []
    skip_terms_eng = ["table of contents", "contents", "page", "chap", "toc"]
    skip_terms_hindi = ["विषय सूची", "अनुक्रमणिका", "सामग्री", "पृष्ठ", "अध्याय"]

    for raw_line in text.split("\n"):
        line = raw_line.strip()
        if not line or len(line) < 3:
            continue

        if is_hindi:
            if any(term in line for term in skip_terms_hindi):
                continue
        else:
            if any(term in line.lower() for term in skip_terms_eng):
                continue

        if is_hindi:
            m = re.match(r"^(.*\S)\s+([०१२३४५६७८९\d]+)$", line)
            if m:
                chapter = m.group(1).strip()
                page_raw = m.group(2).strip()
                page = convert_hindi_digits(page_raw)
                entries.append({"chapter": chapter, "page": page})
        else:
            m = re.match(r"^(.*?)[\s\.\-]+(\d+)\s*$", line)
            if m:
                chapter = m.group(1).strip()
                page = m.group(2).strip()
                entries.append({"chapter": chapter, "page": page})

    return entries


# ─── Streamlit UI ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="PDF TOC Extractor", layout="wide")
st.title("📄 PDF Table of Contents Extractor")

st.write(
    """
    1. Upload a PDF (e.g., an entire book).  
    2. The app will look for pages containing “table of contents,” “contents,” “foreword,” or “preface.”  
    3. It then extracts only those pages and parses the TOC lines into an editable table.  
    4. You can add rows/columns at any index, then download a CSV named after your PDF.
    """
)

# — Step 1: File Uploader & Preview —────────────────────────────────────────────

uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])
if uploaded_file:
    # Keep raw PDF bytes for later
    pdf_bytes = uploaded_file.read()
    st.session_state["raw_pdf_bytes"] = pdf_bytes

    # Embed the PDF using an <iframe> with type="application/pdf"
    b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_display = f"""
        <iframe
            src="data:application/pdf;base64,{b64_pdf}"
            width="100%"
            height="600px"
            type="application/pdf"
        ></iframe>
    """
    components.html(pdf_display, height=600, scrolling=True)

    # — Step 2: Extract TOC Button —───────────────────────────────────────────

    language = st.selectbox("OCR Language (if needed)", ("eng", "hin", "both"))
    if st.button("Extract TOC"):
        # Save PDF to a temp file so PyPDF2/OCR can read it
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(st.session_state["raw_pdf_bytes"])
            tmp_path = tmp.name

        is_hindi = (language == "hin" or language == "both")
        ocr_lang = "eng+hin" if language == "both" else language

        try:
            # 1️⃣ Find pages likely containing TOC
            toc_indices = find_toc_page_indices(tmp_path)

            if toc_indices:
                # 2️⃣ Extract only those pages
                raw_text = extract_text_from_pages(tmp_path, toc_indices, lang=ocr_lang)
            else:
                # Fallback: process entire PDF
                raw_text = extract_text_from_pdf(tmp_path, lang=ocr_lang)

            # 3️⃣ Parse TOC from the extracted text
            toc_entries = parse_toc(raw_text, is_hindi=is_hindi)

            if not toc_entries:
                st.warning("No TOC entries detected.")
            else:
                df = pd.DataFrame(toc_entries)
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

    # Use st.data_editor to let the user edit cells
    edited_df = st.data_editor(df, num_rows="dynamic", use_container_width=True)
    st.session_state["df"] = edited_df

    st.markdown("---")

    # — Add a blank row at specified index —─────────────────────────────────
    st.write("### ➕ Add a Blank Row")
    max_row_idx = len(st.session_state["df"])
    st.number_input(
        "Insert new row at index (0-based)",
        min_value=0, max_value=max_row_idx, value=max_row_idx, step=1, key="new_row_idx"
    )
    if st.button("Add Row", key="add_row_button"):
        df_current = st.session_state["df"]
        new_row_idx = st.session_state["new_row_idx"]

        blank_row = pd.DataFrame({col: [""] for col in df_current.columns})
        top = df_current.iloc[: new_row_idx].reset_index(drop=True)
        bottom = df_current.iloc[new_row_idx :].reset_index(drop=True)
        new_df = pd.concat([top, blank_row, bottom], ignore_index=True)

        st.session_state["df"] = new_df
        st.experimental_rerun()

    st.markdown("----")

    # — Add a blank column at specified index —─────────────────────────────
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
            col_idx = st.session_state["new_col_idx"]
            col_name = st.session_state["new_col_name"]
            df_current.insert(col_idx, col_name, "")
            st.session_state["df"] = df_current
            st.experimental_rerun()

    st.markdown("---")

    # — Step 4: Download as CSV with PDF-based name —─────────────────────────
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
