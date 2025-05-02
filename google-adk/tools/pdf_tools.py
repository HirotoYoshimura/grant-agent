# tools/pdf_tools.py

import os
import requests
import logging
from io import BytesIO
from PyPDF2 import PdfReader,errors # Import specific error
import pymupdf4llm
from typing import Dict, Any
from google.adk.tools import FunctionTool

# Set up logging
logger = logging.getLogger(__name__)

# --- PDF Downloader & Text Extractor Tool ---
def download_and_extract_pdf_text(url: str) -> Dict[str, Any]:
    """
    Downloads a PDF from a URL and extracts text content using PyPDF2.

    Args:
        url (str): The URL of the PDF file.

    Returns:
        Dict[str, Any]: A dictionary with 'status' ('success' or 'error').
                      On success, includes 'extracted_text'.
                      On error, includes 'error_message'.
    """
    logger.info(f"Attempting to download and extract PDF text from: {url}")
    try:
        # Use a common user-agent
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, stream=True, timeout=45) # Increased timeout
        response.raise_for_status()

        content_type = response.headers.get('Content-Type', '').lower()
        if 'application/pdf' not in content_type:
             logger.warning(f"URL content type is not PDF ({content_type}): {url}")
             # Allow proceeding but log warning, as sometimes headers are wrong
             # return {"status": "error", "error_message": f"URL does not point to a PDF (Content-Type: {content_type})"}

        pdf_content = BytesIO(response.content)
        try:
            reader = PdfReader(pdf_content)
            text = ""
            num_pages = len(reader.pages)
            logger.info(f"PDF has {num_pages} pages.")
            for i, page in enumerate(reader.pages):
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                except Exception as page_err:
                     logger.warning(f"Error extracting text from page {i+1} of {url}: {page_err}")
                     text += f"[Error extracting page {i+1}]\n" # Add placeholder for page error
            if not text and num_pages > 0:
                 logger.warning(f"Successfully read PDF structure but extracted no text from {url}.")
                 # Consider returning success with empty text or a specific warning status
                 # return {"status": "success_empty", "extracted_text": "", "message": "PDF read, but no text content extracted."}

            logger.info(f"Successfully extracted text from PDF: {url} (Length: {len(text)})")
            return {"status": "success", "extracted_text": text}
        except errors.PdfReadError as pdf_err:
             logger.error(f"PyPDF2 error reading PDF content from {url}: {pdf_err}")
             return {"status": "error", "error_message": f"Invalid or corrupted PDF file: {pdf_err}"}


    except requests.exceptions.Timeout:
        logger.error(f"Timeout error downloading PDF from {url}")
        return {"status": "error", "error_message": f"Timeout Error after 45 seconds downloading PDF"}
    except requests.exceptions.RequestException as e:
         logger.error(f"HTTP error downloading PDF from {url}: {str(e)}")
         return {"status": "error", "error_message": f"HTTP error downloading PDF: {str(e)}"}
    except Exception as e:
        logger.error(f"Error downloading/extracting PDF from {url}: {str(e)}")
        return {"status": "error", "error_message": f"Failed to process PDF: {str(e)}"}

# Map to the name requested by user
pdf_downloader_tool = FunctionTool(func=download_and_extract_pdf_text)


# --- Local PDF Reader Tool (Markdown) ---
def read_local_pdf_markdown(file_path: str) -> Dict[str, Any]:
    """
    Reads a local PDF file and returns its content as Markdown using PyMuPDF4LLM.

    Args:
        file_path (str): The path to the local PDF file.

    Returns:
        Dict[str, Any]: Dictionary with 'status' ('success'/'error'), 'markdown_content' or 'error_message'.
    """
    logger.info(f"Reading local PDF (Markdown): {file_path}")
    try:
        # SECURITY NOTE: Ensure file_path is validated/restricted in production.
        if not os.path.exists(file_path):
             logger.warning(f"Local PDF file not found: {file_path}")
             return {"status": "error", "error_message": f"Local PDF file not found: {file_path}"}

        # Use pymupdf4llm to convert to Markdown
        md_text = pymupdf4llm.to_markdown(file_path, margins=0)

        logger.info(f"Successfully read local PDF as Markdown: {file_path} (Length: {len(md_text)})")
        return {"status": "success", "markdown_content": md_text}
    except Exception as e:
        logger.error(f"Error reading local PDF {file_path}: {str(e)}")
        return {"status": "error", "error_message": f"Error reading PDF: {str(e)}"}

pdf_reader_tool = FunctionTool(func=read_local_pdf_markdown)