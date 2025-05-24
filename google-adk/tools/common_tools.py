# tools/common_tools.py

import os
import json
import logging
import time
import re
import requests
from typing import Dict, Any, List, Optional
from google.adk.tools import FunctionTool
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
# from googleapiclient.discovery import build # APIが不要となるため削除
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv("/workspace/google-adk/.env")

# Set up logging
logger = logging.getLogger(__name__)

# --- User Profile Reader Tool ---
def read_user_profile() -> Dict[str, Any]:
    file_path = "/workspace/google-adk/knowledge/user_preference.txt"
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


# --- API不要な検索ツール ---
_WEB_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

def search_duckduckgo(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """DuckDuckGoで検索を実行する（API不要）"""
    logger.info(f"Performing DuckDuckGo search for: {query}")
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        response = requests.get(url, headers=_WEB_HEADERS, timeout=20)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        for result in soup.select('.result'):
            title_elem = result.select_one('.result__title')
            link_elem = result.select_one('.result__url')
            snippet_elem = result.select_one('.result__snippet')
            
            if title_elem and link_elem:
                title = title_elem.get_text(strip=True)
                link = link_elem.get('href', '')
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                
                # URLをクリーンアップ
                if link.startswith('/'):
                    link = f"https://duckduckgo.com{link}"
                
                results.append({
                    "title": title,
                    "link": link,
                    "snippet": snippet
                })
                
                if len(results) >= max_results:
                    break
                    
        return results
    except Exception as e:
        logger.error(f"DuckDuckGo search error: {str(e)}")
        return []

def search_searx(query: str, max_results: int = 10) -> List[Dict[str, str]]:
    """Searxで検索を実行する（API不要・複数インスタンスをフォールバックとして使用）"""
    logger.info(f"Performing Searx search for: {query}")
    
    # 公開Searxインスタンスのリスト（1つ目が失敗した場合に次を試行）
    searx_instances = [
        "https://searx.be/search",
        "https://search.ononoki.org/search", 
        "https://search.sapti.me/search",
        "https://search.mdosch.de/search"
    ]
    
    for instance in searx_instances:
        try:
            params = {
                "q": query,
                "format": "html",
                "language": "en-US",
                "categories": "general",
                "time_range": "",
                "safesearch": "0"
            }
            
            response = requests.get(instance, params=params, headers=_WEB_HEADERS, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            
            results = []
            # 検索結果のセレクタはインスタンスによって異なる場合があるため、複数試行
            result_elements = (
                soup.select('.result') or 
                soup.select('.result-default') or 
                soup.select('.result-item')
            )
            
            for result in result_elements:
                title_elem = (
                    result.select_one('.result-title') or 
                    result.select_one('.result-header') or
                    result.select_one('h4') or
                    result.select_one('h3')
                )
                
                link_elem = result.select_one('a')
                snippet_elem = (
                    result.select_one('.result-content') or 
                    result.select_one('.result-snippet') or
                    result.select_one('.content')
                )
                
                if title_elem and link_elem:
                    title = title_elem.get_text(strip=True)
                    link = link_elem.get('href', '')
                    snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""
                    
                    results.append({
                        "title": title,
                        "link": link,
                        "snippet": snippet
                    })
                    
                    if len(results) >= max_results:
                        break
            
            if results:  # 結果が見つかった場合
                logger.info(f"Found {len(results)} results via Searx search.")
                return results
                
        except Exception as e:
            logger.warning(f"Searx search error with instance {instance}: {str(e)}")
            continue  # 次のインスタンスを試す
    
    logger.error("All Searx instances failed")
    return []  # すべてのインスタンスが失敗した場合は空のリストを返す

def api_free_web_search(query: str) -> Dict[str, Any]:
    """API不要の検索ツール（複数の検索エンジンを組み合わせて使用）"""
    logger.info(f"Performing API-free web search for: {query}")
    time.sleep(1)  # 短い待機時間
    
    try:
        # 最初にSearxで検索
        results = search_searx(query)
        
        # Searxの結果が不十分な場合、DuckDuckGoでバックアップ
        if len(results) < 5:
            ddg_results = search_duckduckgo(query)
            
            # 重複を避けるために既存のURLをチェック
            existing_urls = {r["link"] for r in results}
            for r in ddg_results:
                if r["link"] not in existing_urls:
                    results.append(r)
                    existing_urls.add(r["link"])
                    
                    # 10件まで収集
                    if len(results) >= 10:
                        break
        
        logger.info(f"Found total {len(results)} results via API-free search.")
        
        # 結果を整形
        return {
            "status": "success", 
            "search_query": query, 
            "results": results
        }
    except Exception as e:
        logger.error(f"API-free web search error: {str(e)}")
        return {
            "status": "error", 
            "error_message": f"Search failed: {str(e)}", 
            "results": []
        }

# もとのCustom Google Search関連コードを削除し、APIフリーバージョンに置き換え
web_search_tool = FunctionTool(func=api_free_web_search)


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