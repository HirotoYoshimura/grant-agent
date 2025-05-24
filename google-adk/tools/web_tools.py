# tools/web_tools.py

import requests
import logging
import urllib.parse
from bs4 import BeautifulSoup
from typing import Dict, Any
from google.adk.tools import FunctionTool, ToolContext # ToolContext for potential stateful use
import os 
import time
from dotenv import load_dotenv
from pathlib import Path

# Set up logging
logger = logging.getLogger(__name__)

# Load environment variables from .env file
load_dotenv(Path.cwd() / ".env")

# --- Constants ---
_WEB_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}
_MAX_WEB_TEXT_LENGTH = 100000 # Limit text extraction length

# --- Helper Function ---
def _extract_main_content_from_soup(soup: BeautifulSoup, max_length: int) -> str:
    """Helper to extract main text content, limited by length."""
    time.sleep(2)
    if not soup: return "No content parsed."
    # Remove common non-content tags
    for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'iframe', 'header', 'aside', 'form', 'button', 'input']):
        tag.decompose()

    # Try finding common main content containers
    main_content = (soup.find('main') or
                    soup.find('article') or
                    soup.find('div', id='content') or
                    soup.find('div', class_='content') or
                    soup.find('div', id='main') or
                    soup.find('div', class_='main') or
                    soup.body) # Fallback to body

    if not main_content: return "Could not find main content body."

    text = main_content.get_text(separator='\n', strip=True)

    # Limit length
    if len(text) > max_length:
        return text[:max_length] + f"... [Content truncated at {max_length} chars]"
    return text if text else "Content extracted but empty."

# --- Web Browser Tool ---
def browse_web_page(url: str) -> Dict[str, Any]:
    """
    Fetches and extracts the main text content of a given URL. Suitable for basic scraping.

    Args:
        url (str): The URL to browse.

    Returns:
        Dict[str, Any]: Dictionary with 'status', 'url', 'content' or 'error_message'.
    """
    logger.info(f"Browsing URL: {url}")
    time.sleep(1)
    try:
        response = requests.get(url, headers=_WEB_HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        content = _extract_main_content_from_soup(soup, _MAX_WEB_TEXT_LENGTH)
        return {"status": "success", "url": url, "content": content}
    except requests.exceptions.Timeout:
         logger.error(f"Timeout error browsing {url}")
         return {"status": "error", "url": url, "error_message": f"Timeout Error after 20 seconds"}
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP error browsing {url}: {e}")
        return {"status": "error", "url": url, "error_message": f"HTTP Error: {e}"}
    except Exception as e:
        logger.error(f"Error browsing {url}: {e}")
        return {"status": "error", "url": url, "error_message": f"Browsing Error: {e}"}

# Map to the names requested by the user
web_scraper_tool = FunctionTool(func=browse_web_page) # Use for general scraping/content fetching
# 'web_navigator_tool' implies state, which isn't implemented here.
# We'll alias the browser tool for now, but stateful navigation is different.
web_navigator_tool = web_scraper_tool


# --- Link Extractor Tool ---
def extract_links_from_page(url: str) -> Dict[str, Any]:
    """
    Fetches a URL and extracts all valid links (absolute URL and link text).

    Args:
        url (str): The URL to extract links from.

    Returns:
        Dict[str, Any]: Dictionary with 'status', 'url', 'links' (list of dicts {'url': str, 'text': str}) or 'error_message'.
    """
    logger.info(f"Extracting links from: {url}")
    try:
        response = requests.get(url, headers=_WEB_HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href')
            # Clean link text, default if empty
            text = ' '.join(a_tag.get_text(strip=True).split()) or "[No link text]"
            # Filter out javascript, mailto, internal anchors, and empty links
            if href and not href.startswith(('javascript:', '#', 'mailto:', 'tel:')) and href.strip():
                try:
                    absolute_url = urllib.parse.urljoin(url, href.strip())
                    # Basic validation of the formed URL
                    if urllib.parse.urlparse(absolute_url).scheme in ('http', 'https'):
                        links.append({"url": absolute_url, "text": text})
                except ValueError:
                     logger.warning(f"Could not parse or join URL: base={url}, href={href}")
                     continue # Skip invalid URLs

        logger.info(f"Extracted {len(links)} links from {url}")
        return {"status": "success", "url": url, "links": links}
    except requests.exceptions.Timeout:
        logger.error(f"Timeout error extracting links from {url}")
        return {"status": "error", "url": url, "error_message": f"Timeout Error after 20 seconds"}
    except requests.exceptions.RequestException as e:
        logger.error(f"HTTP error extracting links from {url}: {e}")
        return {"status": "error", "url": url, "error_message": f"HTTP Error: {e}"}
    except Exception as e:
        logger.error(f"Error extracting links from {url}: {e}")
        return {"status": "error", "url": url, "error_message": f"Link Extraction Error: {e}"}

adk_extract_links_tool = FunctionTool(func=extract_links_from_page)