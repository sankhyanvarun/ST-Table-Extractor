# PDF Table of Contents Extractor

![image](https://github.com/user-attachments/assets/f3f6fabd-ffcd-4c97-a810-0a1cfb39045c)


The PDF Table of Contents Extractor is a powerful Streamlit application that automatically extracts table of contents information from PDF documents. It handles both text-based and scanned PDFs using OCR technology, and provides an intuitive interface for editing and exporting the extracted data.

## Key Features

- 🔍 **Automatic TOC Detection**: Intelligently identifies TOC pages in PDF documents
- 📄 **OCR Support**: Extracts text from scanned PDFs using Tesseract OCR
- ✏️ **Editable Results**: Modify extracted TOC entries with an intuitive data editor
- ➕ **Insert Rows**: Add new entries at any position in the table
- 💾 **CSV Export**: Download the final TOC as a CSV file
- 🐘 **Large PDF Handling**: Automatically processes only the first 70 pages for PDFs over 100MB
- 🌐 **Hindi Character Filtering**: Cleans Devanagari characters from extracted text

## How It Works

1. **PDF Upload**: Upload any PDF document (including scanned books)
2. **TOC Extraction**: The app analyzes the PDF to find TOC pages and extracts entries
3. **Review & Edit**: Examine the extracted TOC and make modifications as needed
4. **Insert Rows**: Add new entries at specific positions in the table
5. **Export**: Download the final table of contents as a CSV file

## Installation

To run this application locally:

1. Clone the repository:
```bash
git clone (https://github.com/sankhyanvarun/ST-Table-Extractor)
cd ST-Table-Extractor
```

2. Install required dependencies:
```bash
pip install -r requirements.txt
```

3. Install system dependencies:
- **Poppler**: Required for PDF processing
- **Tesseract OCR**: Required for text extraction from images

4. Run the application:
```bash
streamlit run st.py
```

## Configuration

The application requires the following configurations:

1. Set `POPPLER_PATH` to the directory containing Poppler binaries
2. Set `TESSERACT_CMD` to the Tesseract executable path

Example configuration for Windows:
```python
POPPLER_PATH = r"C:\path\to\poppler\bin"
TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
```

## Usage Notes

- For PDFs over 100MB, only the first 70 pages are processed to optimize performance
- The app works best with PDFs that have a clear table of contents structure
- Editing features allow you to correct any extraction errors or add missing entries
- For scanned PDFs, ensure good quality images for accurate OCR results

## Requirements

- Python 3.7+
- Streamlit
- PyPDF2
- pandas
- pdf2image
- pytesseract
- Pillow
- poppler-utils (system dependency)
- tesseract-ocr (system dependency)

## Deployment

The application is designed to run on Streamlit Cloud. To deploy:

1. Create a `requirements.txt` file with all Python dependencies
2. Include Poppler binaries in your repository (for Windows deployment)
3. Configure the Tesseract path in the application code
4. Deploy to Streamlit Cloud following their documentation

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request for any improvements.

## Support

For support or questions, please open an issue in the GitHub repository.
