#!/usr/bin/env python3
# tools/common_tools.py

import os
import json
import logging
import time
from pathlib import Path
from typing import Dict, Any
from google.adk.tools import FunctionTool
from googleapiclient.discovery import build
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("../.env")

# Set up logging
logger = logging.getLogger(__name__)

# --- User Profile Reader Tool ---
def read_user_profile(**kwargs) -> Dict[str, Any]:
    # kwargs に何らかの引数が渡されてきても、ここでは使用しない
    file_path = str(Path(__file__).resolve().parent.parent / "knowledge" / "user_preference.txt")
    logger.info(f"Attempting to read user profile from: {file_path}")
    try:
        if not os.path.exists(file_path):
            logger.warning(f"Profile file not found: {file_path}")
            return {"status": "error", "error_message": f"File not found: {file_path}", "file_path": file_path,}
        with open(file_path, 'r', encoding='utf-8') as file: content = file.read()
        logger.info(f"Successfully read profile from: {file_path}")
        return {"status": "success", "profile_text": content, "file_path": file_path,}
    except Exception as e:
        logger.error(f"Error reading user profile from {file_path}: {str(e)}")
        return {"status": "error", "error_message": f"Failed to read profile: {str(e)}", "file_path": file_path,}
profile_reader_tool = FunctionTool(func=read_user_profile)


# --- Custom Google Search Tool (using CSE API) ---
GOOGLE_CSE_API_KEY = os.environ.get("GOOGLE_CSE_API_KEY") # Platform API Key
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID")  # Custom Search Engine ID

def custom_google_search(query: str) -> Dict[str, Any]:
    """Performs Google search using Custom Search Engine API."""
    logger.info(f"Performing Custom Google Search for: {query}")
    time.sleep(2)

    if not GOOGLE_CSE_API_KEY or not GOOGLE_CSE_ID:
        msg = "Google API Key or CSE ID for Custom Search not configured in environment variables."
        logger.error(msg)
        return {"status": "error", "error_message": msg}
    try:
        service = build("customsearch", "v1", developerKey=GOOGLE_CSE_API_KEY, cache_discovery=False) # cache_discovery=False 追加
        result = service.cse().list(q=query, cx=GOOGLE_CSE_ID, num=10).execute()
        items = result.get("items", [])
        logger.info(f"Found {len(items)} results via Custom Search.")
        # Format results for the agent
        formatted_results = [
            {"title": item.get("title"), "link": item.get("link"), "snippet": item.get("snippet")}
            for item in items
        ]
        # Return structured dictionary
        return {"status": "success", "search_query": query, "results": formatted_results}
    except Exception as e:
        logger.error(f"Custom Google Search error: {str(e)}")
        return {"status": "error", "error_message": f"Search failed: {str(e)}", "results": []}

# Wrap as ADK FunctionTool
custom_google_search_tool = FunctionTool(func=custom_google_search)


# --- JSON Saver Tool ---
def save_data_to_json(data: Dict[str, Any], output_path: str) -> Dict[str, Any]:
    logger.info(f"Attempting to save data to JSON: {output_path}")
    try:
        output_dir = os.path.dirname(output_path)
        if output_dir: os.makedirs(output_dir, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f: json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Data successfully saved to {output_path}")
        return {"status": "success", "file_path": output_path}
    except Exception as e:
        logger.error(f"Error saving data to JSON ({output_path}): {str(e)}")
        return {"status": "error", "error_message": f"Failed to save JSON: {str(e)}"}
json_saver_tool = FunctionTool(func=save_data_to_json)