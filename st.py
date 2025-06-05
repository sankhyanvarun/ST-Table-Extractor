import os
import re
import tempfile
import base64
import uuid

import pandas as pd
import PyPDF2
import pytesseract
from pdf2image import convert_from_path
import streamlit as st
import streamlit.components.v1 as components

# ─── Configuration ────────────────────────────────────────────────────────────
script_dir = os.path.dirname(os.path.abspath(__file__)) if "__file__" in locals() else os.getcwd()
POPPLER_PATH = os.path.join(script_dir, "poppler", "bin")
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe" if os.name == 'nt' else "/usr/bin/tesseract"
pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD


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
    """Extract text from a single page (0-based index)."""
    text = ""
    poppler_path = get_poppler_path()

    with open(pdf_path, "rb") as f:
        reader = PyPDF2.PdfReader(f)
        if page_num < len(reader.pages):
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
                    st.error(f"OCR failed on page {page_num+1}: {str(e)}")
                    page_text = ""

            text = page_text + "\n"

    return text

def extract_text_from_pages(pdf_path, page_indices, lang="eng"):
    """Extract text from specified pages."""
    accumulated = ""
    for idx in page_indices:
        accumulated += extract_page_text(pdf_path, idx, lang=lang)
    return accumulated

def extract_text_from_pdf(pdf_path, lang="eng"):
    """Extract text from the entire PDF."""
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
                    st.error(f"OCR failed on page {page_num+1}: {str(e)}")
                    page_text = ""

            text += page_text + "\n"

    return text

def find_toc_page_indices(pdf_path):
    """Find pages containing TOC keywords."""
    try:
        reader = PyPDF2.PdfReader(pdf_path)
        keywords = ["table of contents", "contents", "foreword", "preface"]
        indices = []

        for i in range(len(reader.pages)):
            page = reader.pages[i]
            raw_text = page.extract_text() or ""
            lower = raw_text.lower()
            if any(kw in lower for kw in keywords):
                indices.append(i)
        return indices
    except Exception as e:
        st.error(f"Error finding TOC pages: {str(e)}")
        return []

def parse_toc(text, is_hindi=False):
    """Parse TOC lines into chapter-page entries."""
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

# Initialize session state variables
if 'extracted' not in st.session_state:
    st.session_state.extracted = False
if 'editing' not in st.session_state:
    st.session_state.editing = False
if 'df' not in st.session_state:
    st.session_state.df = None
if 'pdf_name' not in st.session_state:
    st.session_state.pdf_name = ""
if 'raw_pdf_bytes' not in st.session_state:
    st.session_state.raw_pdf_bytes = None

# Main workflow logic
def main():
    with st.expander("ℹ️ How to use", expanded=True):
        st.write("""
        1. **Upload PDF** - Upload any PDF document
        2. **Extract TOC** - Click the button to extract the Table of Contents
        3. **View TOC** - Review the extracted table
        4. **Edit TOC** - Click the edit button to make changes
        5. **Save Changes** - Save your edits when done
        6. **Download** - Export the final TOC as a CSV file
        """)

    # ─── Step 1: File Upload ──────────────────────────────────────────────────
    st.subheader("1. Upload PDF")
    uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"], label_visibility="collapsed")

    if uploaded_file and st.session_state.raw_pdf_bytes is None:
        pdf_bytes = uploaded_file.read()
        st.session_state.raw_pdf_bytes = pdf_bytes
        st.session_state.pdf_name = uploaded_file.name
        st.session_state.extracted = False  # Reset extraction state on new upload
        st.success("PDF uploaded successfully!")

    # ─── Step 2: Extract TOC ─────────────────────────────────────────────────
    if st.session_state.raw_pdf_bytes and not st.session_state.extracted:
        st.subheader("2. Extract Table of Contents")
        
        with st.form("extract_form"):
            language = st.selectbox("OCR Language", ("eng", "hin", "both"), index=0)
            if st.form_submit_button("🔍 Extract TOC"):
                with st.spinner("Extracting TOC..."):
                    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                        tmp.write(st.session_state.raw_pdf_bytes)
                        tmp_path = tmp.name
                    
                    is_hindi = (language == "hin" or language == "both")
                    ocr_lang = "eng+hin" if language == "both" else language
                    
                    try:
                        toc_indices = find_toc_page_indices(tmp_path)
                        if toc_indices:
                            raw_text = extract_text_from_pages(tmp_path, toc_indices, lang=ocr_lang)
                        else:
                            raw_text = extract_text_from_pdf(tmp_path, lang=ocr_lang)
                        
                        toc_entries = parse_toc(raw_text, is_hindi=is_hindi)
                        
                        if toc_entries:
                            st.session_state.df = pd.DataFrame(toc_entries)
                            st.session_state.extracted = True
                            st.success(f"Extracted {len(toc_entries)} TOC entries")
                        else:
                            st.warning("No TOC entries detected.")
                    except Exception as e:
                        st.error(f"Extraction error: {str(e)}")
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
            height=400
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
        csv_name = f"{os.path.splitext(st.session_state.pdf_name)[0]}_TOC.csv" if st.session_state.pdf_name else "table_of_contents.csv"
        
        st.download_button(
            label="💾 Download as CSV",
            data=csv_data,
            file_name=csv_name,
            mime="text/csv",
            use_container_width=True,
            type="primary"
        )

    # ─── PDF Preview Section ─────────────────────────────────────────────────
    if st.session_state.raw_pdf_bytes:
        st.divider()
        st.subheader("PDF Preview")
        st.download_button(
            label="⬇️ Download Original PDF",
            data=st.session_state.raw_pdf_bytes,
            file_name=st.session_state.pdf_name,
            mime="application/pdf",
            use_container_width=True
        )
        
        try:
            # Base64 preview fallback
            b64_pdf = base64.b64encode(st.session_state.raw_pdf_bytes).decode("utf-8")
            pdf_display = f"""
            <iframe
                src="data:application/pdf;base64,{b64_pdf}"
                width="100%"
                height="600px"
                style="border: 1px solid #eee; border-radius: 8px;"
            ></iframe>
            """
            components.html(pdf_display, height=600)
        except Exception as e:
            st.warning(f"Preview unavailable: {str(e)}. Please download the PDF to view it.")

# Run the main function
if __name__ == "__main__":
    main()
