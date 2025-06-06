import os
import re
import tempfile

from typing import List, Dict

import pandas as pd
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
import streamlit as st

# ─── Configuration ────────────────────────────────────────────────────────────
script_dir = (
    os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
)
POPPLER_PATH = os.path.join(script_dir, "poppler", "bin")
TESSERACT_CMD = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    if os.name == "nt"
    else "/usr/bin/tesseract"
)
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


def get_poppler_path() -> str:
    return POPPLER_PATH


def strip_hindi_chars(text: str) -> str:
    """
    Remove any Devanagari (Hindi) characters from `text`.
    Devanagari Unicode block: U+0900–U+097F
    """
    return re.sub(r"[\u0900-\u097F]+", "", text)


def extract_page_text(pdf_path: str, page_num: int, lang: str = "eng") -> str:
    """
    Extract text from a single page (0-based). If the PDF‐embedded text is empty,
    attempt OCR—only if Poppler (pdftoppm) exists. Do NOT strip Hindi here; that
    will be done later per-line.
    """
    page_text = ""
    poppler_path = get_poppler_path()
    poppler_exists = os.path.exists(os.path.join(poppler_path, "pdftoppm"))

    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        if page_num < len(reader.pages):
            page = reader.pages[page_num]
            page_text = page.extract_text() or ""

            # If PDF text is blank/whitespace, attempt OCR
            if not page_text.strip() and poppler_exists:
                try:
                    images = convert_from_path(
                        pdf_path,
                        first_page=page_num + 1,
                        last_page=page_num + 1,
                        poppler_path=poppler_path,
                        dpi=400,
                        grayscale=True,
                    )
                    if images:
                        img = images[0]
                        page_text = pytesseract.image_to_string(
                            img, lang=lang, config="--psm 6"
                        )
                except Exception:
                    page_text = ""

    return page_text + "\n"


def extract_text_from_pages(
    pdf_path: str, page_indices: List[int], lang: str = "eng"
) -> str:
    """
    Extract (or OCR) text from the specified pages. Hindi characters
    remain in the returned string; parsing will strip them line by line.
    """
    accumulated = ""
    for idx in page_indices:
        accumulated += extract_page_text(pdf_path, idx, lang=lang)
    return accumulated


def extract_text_from_pdf(pdf_path: str, lang: str = "eng") -> str:
    """
    Extract (or OCR) text from all pages, concatenated. Hindi remains until parsing.
    """
    full_text = ""
    poppler_path = get_poppler_path()
    poppler_exists = os.path.exists(os.path.join(poppler_path, "pdftoppm"))

    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        num_pages = len(reader.pages)

        for page_num in range(num_pages):
            page = reader.pages[page_num]
            page_text = page.extract_text() or ""

            if not page_text.strip() and poppler_exists:
                try:
                    images = convert_from_path(
                        pdf_path,
                        first_page=page_num + 1,
                        last_page=page_num + 1,
                        poppler_path=poppler_path,
                        dpi=400,
                        grayscale=True,
                    )
                    if images:
                        img = images[0]
                        page_text = pytesseract.image_to_string(
                            img, lang=lang, config="--psm 6"
                        )
                except Exception:
                    page_text = ""

            full_text += page_text + "\n"

    return full_text


def parse_toc(text: str) -> List[Dict[str, str]]:
    """
    Given a block of text (which may still contain Hindi), examine each line as follows:
    1. Strip out any Devanagari chars (so only English/digits/punctuation remain).
    2. Skip lines containing 'contents', 'page', etc., in English.
    3. Apply a regex to capture "Chapter Title … 12" or "Chapter Title - 12".
    """
    entries: List[Dict[str, str]] = []
    skip_terms = ["table of contents", "contents", "page", "chap", "toc"]

    for raw_line in text.split("\n"):
        # 1) Remove leading/trailing whitespace
        line = raw_line.strip()
        if not line or len(line) < 3:
            continue

        # 2) Strip out Hindi characters from this line only
        cleaned = strip_hindi_chars(line)

        # 3) If the cleaned line still contains any of the skip terms, skip it
        lower_cleaned = cleaned.lower()
        if any(term in lower_cleaned for term in skip_terms):
            continue

        # 4) Try to match "Some Chapter Name …. 5" or "Some Chapter Name - 5"
        m = re.match(r"^(.*?)[\s\.\-]+(\d+)\s*$", cleaned)
        if m:
            chapter = m.group(1).strip()
            page_no = m.group(2).strip()
            entries.append({"chapter": chapter, "page": page_no})

    return entries


def find_toc_page_indices(pdf_path: str, max_search_pages: int = 20) -> List[int]:
    """
    Look at the first `max_search_pages` pages of the PDF (or fewer if the PDF is shorter).
    For each page:
      1. Extract text (via PyPDF2). If blank and poppler exists, do OCR.
      2. Check the raw text (with both English & Hindi still present) for the substring "contents" (case‐insensitive).
      3. If "contents" is found, run parse_toc(...) on that raw text. If parse_toc returns ≥ 2 entries, mark this page as TOC.
    Return a list of all page indices that look like TOC pages.
    """
    indices: List[int] = []
    poppler_path = get_poppler_path()
    poppler_exists = os.path.exists(os.path.join(poppler_path, "pdftoppm"))

    try:
        reader = PyPDF2.PdfReader(pdf_path)
        num_pages = len(reader.pages)
        search_limit = min(num_pages, max_search_pages)

        for i in range(search_limit):
            page = reader.pages[i]
            raw_text = page.extract_text() or ""

            # If PDF text is blank and poppler exists, do a quick page‐OCR
            if not raw_text.strip() and poppler_exists:
                try:
                    images = convert_from_path(
                        pdf_path,
                        first_page=i + 1,
                        last_page=i + 1,
                        poppler_path=poppler_path,
                        dpi=300,
                        grayscale=True,
                    )
                    if images:
                        raw_text = pytesseract.image_to_string(images[0], lang="eng")
                except Exception:
                    raw_text = ""

            lower_all = raw_text.lower()
            # We look for the English word "contents" (case‐insensitive) in the raw text
            if "contents" in lower_all:
                # Now see if parsing that page yields ≥ 2 valid TOC entries
                possible_entries = parse_toc(raw_text)
                if len(possible_entries) >= 2:
                    indices.append(i)
                    # Don’t break—TOC can span multiple consecutive pages

        return indices

    except Exception as e:
        st.error(f"Error finding TOC pages: {e}")
        return []


# ─── Streamlit UI ──────────────────────────────────────────────────────────────

st.set_page_config(page_title="PDF TOC Extractor", layout="wide")
st.title("📄 PDF Table of Contents Extractor")

# Initialize session state
if "extracted" not in st.session_state:
    st.session_state.extracted = False
if "editing" not in st.session_state:
    st.session_state.editing = False
if "df" not in st.session_state:
    st.session_state.df = None
if "pdf_name" not in st.session_state:
    st.session_state.pdf_name = ""
if "raw_pdf_bytes" not in st.session_state:
    st.session_state.raw_pdf_bytes = None


def main():
    with st.expander("ℹ️ How to use", expanded=True):
        st.write(
            """
        1. **Upload PDF** – Upload any PDF document  
        2. **Extract TOC** – Click the button to extract the Table of Contents (and include extra pages if desired)  
        3. **View TOC** – Review the extracted table  
        4. **Edit TOC** – Click the edit button to make changes  
        5. **Save Changes** – Save your edits when done  
        6. **Download** – Export the final TOC as a CSV file (or download an empty template if no TOC was found)  
        """
        )

    # ─── Step 1: Upload PDF ───────────────────────────────────────────────────
    st.subheader("1. Upload PDF")
    uploaded_file = st.file_uploader(
        "Choose a PDF file", type=["pdf"], label_visibility="collapsed"
    )

    if uploaded_file and st.session_state.raw_pdf_bytes is None:
        pdf_bytes = uploaded_file.read()
        st.session_state.raw_pdf_bytes = pdf_bytes
        st.session_state.pdf_name = uploaded_file.name
        st.session_state.extracted = False
        st.success("PDF uploaded successfully!")

    # ─── Step 2: Extract TOC ─────────────────────────────────────────────────
    if st.session_state.raw_pdf_bytes and not st.session_state.extracted:
        st.subheader("2. Extract Table of Contents")
        with st.form("extract_form"):
            # We force English OCR—Hindi characters will be stripped per-line later
            st.selectbox("OCR Language", ("eng",), index=0, disabled=True)

            # Allow user to choose how many extra pages (after each detected TOC page) to include, up to 6
            extra_pages = st.number_input(
                "Include how many extra pages after each detected TOC page?",
                min_value=0,
                max_value=6,  # <-- Changed to allow up to 6
                value=2,
                help="If you notice that some TOC entries span into subsequent pages, increase this value.",
            )

            if st.form_submit_button("🔍 Extract TOC"):
                with st.spinner("Extracting TOC..."):
                    # Save uploaded PDF to a temp file
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(st.session_state.raw_pdf_bytes)
                        tmp_path = tmp.name

                    try:
                        # 1) Find potential TOC pages among the first 20 pages
                        toc_indices = find_toc_page_indices(tmp_path, max_search_pages=20)

                        if toc_indices:
                            # Expand each found index by extra_pages (making sure not to exceed num_pages)
                            reader = PyPDF2.PdfReader(tmp_path)
                            num_pages = len(reader.pages)

                            expanded_indices = set()
                            for i in toc_indices:
                                for offset in range(0, extra_pages + 1):
                                    candidate = i + offset
                                    if candidate < num_pages:
                                        expanded_indices.add(candidate)
                            final_indices = sorted(expanded_indices)

                            # 2) Extract text from all expanded TOC pages (OCR if needed)
                            raw_text = extract_text_from_pages(tmp_path, final_indices, lang="eng")

                        else:
                            # If none detected, fall back to entire PDF
                            raw_text = extract_text_from_pdf(tmp_path, lang="eng")

                        # 3) Parse the collected text to extract chapter→page entries
                        toc_entries = parse_toc(raw_text)

                        if toc_entries:
                            st.session_state.df = pd.DataFrame(toc_entries)
                            st.session_state.extracted = True
                            st.success(f"Extracted {len(toc_entries)} TOC entries")
                        else:
                            st.warning("No TOC entries detected.")
                            # Offer an empty CSV template with columns Page no, Chapter name
                            empty_df = pd.DataFrame(columns=["Page no", "Chapter name"])
                            csv_data_empty = empty_df.to_csv(index=False).encode("utf-8")
                            st.download_button(
                                label="💾 Download Empty TOC Template (CSV)",
                                data=csv_data_empty,
                                file_name="empty_TOC_template.csv",
                                mime="text/csv",
                                use_container_width=True,
                            )
                    except Exception as e:
                        st.error(f"Extraction error: {e}")
                    finally:
                        if os.path.exists(tmp_path):
                            os.remove(tmp_path)

    # ─── Step 3: View TOC ────────────────────────────────────────────────────
    if st.session_state.extracted and st.session_state.df is not None:
        st.subheader("3. Extracted Table of Contents")
        st.dataframe(st.session_state.df, use_container_width=True, height=400)
        if st.button("✏️ Edit TOC", use_container_width=True):
            st.session_state.editing = True

    # ─── Step 4: Edit Mode ───────────────────────────────────────────────────
    if st.session_state.editing and st.session_state.df is not None:
        st.subheader("4. Edit Table of Contents")
        edited_df = st.data_editor(
            st.session_state.df,
            key="toc_editor",
            num_rows="dynamic",
            use_container_width=True,
            height=400,
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("💾 Save Changes", use_container_width=True, type="primary"):
                st.session_state.df = edited_df
                st.session_state.editing = False
                st.success("Changes saved successfully!")
        with col2:
            if st.button("❌ Cancel Editing", use_container_width=True):
                st.session_state.editing = False

    # ─── Step 5/6: Download CSV ──────────────────────────────────────────────
    if st.session_state.extracted and st.session_state.df is not None:
        st.subheader("5. Download Results")
        csv_data = st.session_state.df.to_csv(index=False).encode("utf-8")
        csv_name = (
            f"{os.path.splitext(st.session_state.pdf_name)[0]}_TOC.csv"
            if st.session_state.pdf_name
            else "table_of_contents.csv"
        )
        st.download_button(
            label="💾 Download TOC as CSV",
            data=csv_data,
            file_name=csv_name,
            mime="text/csv",
            use_container_width=True,
            type="primary",
        )


if __name__ == "__main__":
    main()
