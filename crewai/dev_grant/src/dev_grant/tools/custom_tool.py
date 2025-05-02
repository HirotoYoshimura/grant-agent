import os
import json
import re
import requests
import logging
from io import BytesIO
from typing import Dict, List, Any, Optional, ClassVar
from crewai.tools import BaseTool
from googleapiclient.discovery import build
from PyPDF2 import PdfReader
import pymupdf4llm
from bs4 import BeautifulSoup
import urllib.parse
import csv

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load API keys from environment variables
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID")  # Custom Search Engine ID

class UserProfileReaderTool(BaseTool):
    """ユーザープロファイル情報をテキストファイルから読み取るツール"""
    
    name: str = "UserProfileReaderTool"
    description: str = "ユーザープロファイル情報をテキストファイルから読み取り、解析します。"
    
    def _run(self, file_path=None) -> Dict[str, str]:
        """
        ユーザープロファイル情報をテキストファイルから読み取り、解析します。
        ファイル形式は自由で、テキストからプロファイル情報を抽出します。
        Args:
            None

        Returns:
            ユーザープロファイル情報を含む辞書
        """
        try:
            file_path="/workspace/crewai/dev_grant/knowledge/user_preference.txt"
            
            # ファイルパスが存在することを確認
            if not os.path.exists(file_path):
                logger.warning(f"指定されたプロファイルファイル {file_path} が存在しません。")
                return {
                    "profile_text": f"ファイル {file_path} が見つかりません",
                    "file_path": file_path,
                    "format": "error"
                }
            
            # ファイルを読み込む
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            
            return {
                "profile_text": content,
                "file_path": file_path,
                "format": "free_text"
            }
                
        except Exception as e:
            logger.error(f"ユーザープロファイルの読み取りエラー: {str(e)}")
            # エラーが発生しても最低限の情報を返す
            return {
                "profile_text": f"プロファイルの読み取りに失敗しました: {str(e)}",
                "file_path": file_path if file_path else "不明",
                "format": "error"
            }

class GoogleSearchTool(BaseTool):
    """Google Custom Search APIを使用して検索するツール"""
    
    name: str = "GoogleSearchTool"
    description: str = "Google Custom Search APIを使用して検索します。"
    
    def _run(self, query: str, num_results: int = 10) -> List[Dict[str, Any]]:
        """
        Google Custom Search APIを使用して検索します。
        
        Args:
            query: 検索クエリ
            num_results: 返す結果の数
            
        Returns:
            検索結果の辞書のリスト
        """
        try:
            service = build("customsearch", "v1", developerKey=GOOGLE_API_KEY)
            result = service.cse().list(q=query, cx=GOOGLE_CSE_ID, num=num_results).execute()
            
            if "items" in result:
                return result["items"]
            else:
                logger.warning(f"クエリに対する結果が見つかりませんでした: {query}")
                return []
        except Exception as e:
            logger.error(f"Google検索エラー: {str(e)}")
            return []

class PDFDownloaderTool(BaseTool):
    """URLからPDFをダウンロードするツール"""
    
    name: str = "PDFDownloaderTool"
    description: str = "URLからPDFコンテンツをダウンロードします。"
    
    def _run(self, url: str) -> Optional[str]:
        """
        URLからPDFコンテンツをダウンロードします。
        
        Args:
            url: PDFのURL
            
        Returns:
            ダウンロードしたPDFの内容（テキスト形式）または失敗した場合はNone
        """
        try:
            response = requests.get(url, stream=True)
            response.raise_for_status()  # HTTPエラーの場合に例外を発生
            
            # PDFコンテンツをバイトとして取得
            pdf_content = BytesIO(response.content)
            
            # PDFからテキストを抽出
            reader = PdfReader(pdf_content)
            text = ""
            for page in reader.pages:
                text += page.extract_text() + "\n"
                
            return text
        except Exception as e:
            logger.error(f"{url}からのPDFダウンロード/抽出エラー: {str(e)}")
            return None

class PDFReaderTool(BaseTool):
    name: str = "PDFReaderTool"
    description: str = "PyMuPDF4LLM を利用してPDFファイルを読み込み、Markdown形式のテキストを返すツール"

    def _run(self, file_path: str) -> str:
        try:
            # margins=0 とすることで余白を取り払った状態で全ページを抽出
            md_text = pymupdf4llm.to_markdown(file_path, margins=0)
            return md_text
        except Exception as e:
            return f"Error reading PDF: {e}"

class JSONSaverTool(BaseTool):
    """結果をJSONファイルに保存するツール"""
    
    name: str = "JSONSaverTool"
    description: str = "結果をJSONファイルに保存します。"
    
    def _run(self, data: Dict[str, Any], output_path: str) -> str:
        """
        結果をJSONファイルに保存します。
        
        Args:
            data: 保存するデータ
            output_path: 出力JSONファイルへのパス
            
        Returns:
            保存されたファイルへのパス
        """
        try:
            # 出力ディレクトリが存在することを確認
            output_dir = os.path.dirname(output_path)
            os.makedirs(output_dir, exist_ok=True)
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"結果が{output_path}に保存されました")
            return output_path
        except Exception as e:
            logger.error(f"結果のJSONへの保存エラー: {str(e)}")
            raise


# class BrowserbaseTool(BaseTool):
#     """A tool to load a URL using a headless webbrowser"""

#     name: str = "BrowserbaseTool"
#     description: str = "A tool to load a URL using a headless webbrowser"

#     def _run(self, url: str):
#         """
#         Loads a URL using a headless webbrowser

#         :param url: The URL to load
#         :return: The text content of the page
#         """
#         with sync_playwright() as playwright:
#             browser = playwright.chromium.connect_over_cdp(
#                 "wss://connect.browserbase.com?apiKey="
#                 + os.environ["BROWSERBASE_API_KEY"]
#             )
#             context = browser.contexts[0]
#             page = context.pages[0]
#             page.goto(url)

#             # Wait for the flight search to finish
#             sleep(25)

#             content = html2text(page.content())
#             browser.close()
#             return content
    

class WebNavigationHelper:
    """Webナビゲーション機能を提供するヘルパークラス"""
    
    def __init__(self, max_text_length=100000):
        self._headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self._current_url = None
        self._history = []
        self._current_page_content = None
        self._current_page_soup = None
        self.max_text_length = max_text_length  # 抽出するテキストの最大長
    
    def browse(self, url: str) -> str:
        """指定されたURLのウェブページを閲覧"""
        try:
            response = requests.get(url, headers=self._headers)
            response.raise_for_status()
            
            self._current_url = url
            self._history.append(url)
            self._current_page_content = response.text
            self._current_page_soup = BeautifulSoup(response.text, 'html.parser')
            
            main_content = self._extract_main_content()
            return f"URL: {url}\n\n{main_content}"
        except Exception as e:
            return f"ページの閲覧中にエラーが発生しました: {str(e)}"
    
    def extract_links(self) -> str:
        """現在のページからリンクを抽出"""
        if not self._current_page_soup:
            return "ページが読み込まれていません。最初にページを閲覧してください。"
        
        try:
            links = []
            for a_tag in self._current_page_soup.find_all('a', href=True):
                href = a_tag.get('href')
                text = a_tag.get_text(strip=True)
                if href and not href.startswith('javascript:') and not href.startswith('#'):
                    absolute_url = urllib.parse.urljoin(self._current_url, href)
                    links.append({"url": absolute_url, "text": text if text else "[No text]"})
            
            return json.dumps(links, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"リンク抽出中にエラーが発生しました: {str(e)}"
    
    def follow_link_by_text(self, link_text: str) -> str:
        """リンクテキストでリンクをたどる"""
        if not self._current_page_soup:
            return "ページが読み込まれていません。最初にページを閲覧してください。"
        
        try:
            for a_tag in self._current_page_soup.find_all('a', href=True):
                if link_text.lower() in a_tag.get_text().lower():
                    href = a_tag.get('href')
                    if href and not href.startswith('javascript:') and not href.startswith('#'):
                        absolute_url = urllib.parse.urljoin(self._current_url, href)
                        return self.browse(absolute_url)
            
            return f"'{link_text}'というテキストを含むリンクが見つかりませんでした"
        except Exception as e:
            return f"リンクをたどる際にエラーが発生しました: {str(e)}"
    
    def get_history(self) -> str:
        """ブラウジング履歴を取得"""
        if not self._history:
            return "ブラウジング履歴がありません"
        
        history_str = "ブラウジング履歴:\n\n"
        for i, url in enumerate(self._history):
            history_str += f"{i+1}. {url}\n"
        
        return history_str
    
    def _extract_main_content(self) -> str:
        """ページから主要なコンテンツを抽出"""
        if not self._current_page_soup:
            return "ページが読み込まれていません"
        
        # 不要な要素を削除
        for tag in self._current_page_soup.find_all(['script', 'style', 'nav', 'footer', 'iframe']):
            tag.decompose()        

        # 主要コンテンツの抽出処理
        for container in ['main', 'article', '.content', '#content', '.main', '#main']:
            try:
                if container.startswith('.') or container.startswith('#'):
                    selector_type = 'class' if container.startswith('.') else 'id'
                    selector_value = container[1:]
                    if selector_type == 'class':
                        content = self._current_page_soup.find(class_=selector_value)
                    else:
                        content = self._current_page_soup.find(id=selector_value)
                else:
                    content = self._current_page_soup.find(container)
                
                if content:
                    return content.get_text(separator='\n', strip=True)
            except Exception:
                pass
        
        # 特定のコンテナが見つからない場合はbodyのテキストを返す
        body = self._current_page_soup.body
        if body:
            content_text=body.get_text(separator='\n', strip=True)
        else: 
            content_text= self._current_page_soup.get_text(separator='\n', strip=True)

        # テキストの長さを制限
        if len(content_text) > self.max_text_length:
            content_text = content_text[:self.max_text_length] + "...[テキストが切り詰められました]"
        
        return content_text


# Langchain Tool形式のWebツールを作成する関数
def create_web_navigation_tools(max_text_length=100000):
    """WebナビゲーションのためのCrewAI BaseTool群を作成
    Args:
        max_text_length: 抽出するテキストの最大長（デフォルト: 100,000文字）
    """
    
    # ヘルパーインスタンスを1つ作成して共有
    helper = WebNavigationHelper(max_text_length=max_text_length)
    
    # BaseTool派生クラスを定義
    class WebBrowserTool(BaseTool):
        name: str = "WebBrowserTool"
        description: str = "指定されたURLのウェブページを閲覧し、そのコンテンツを抽出します。"
        
        def _run(self, url: str) -> str:
            return helper.browse(url)
    
    class ExtractLinksTool(BaseTool):
        name: str = "ExtractLinksTool"
        description: str = "現在閲覧中のページからすべてのリンクを抽出します。"
        
        def _run(self) -> str:
            return helper.extract_links()
    
    class FollowLinkTool(BaseTool):
        name: str = "FollowLinkTool"
        description: str = "現在のページで、指定されたテキストを含むリンクをたどります。"
        
        def _run(self, link_text: str) -> str:
            return helper.follow_link_by_text(link_text)
    
    class BrowsingHistoryTool(BaseTool):
        name: str = "BrowsingHistoryTool"
        description: str = "これまでのブラウジング履歴を取得します。"
        
        def _run(self) -> str:
            return helper.get_history()
    
    # 各ツールのインスタンスを作成して返す
    return [
        WebBrowserTool(),
        ExtractLinksTool(),
        FollowLinkTool(),
        BrowsingHistoryTool()
    ]



class CSVWriterTool(BaseTool):
    """助成金候補をCSVファイルに書き込むツール"""
    
    name: str = "CSVWriterTool"
    description: str = "助成金候補情報をCSVファイルに書き込みます。"
    
    def _run(self, grants_data: List[Dict[str, Any]]) -> str:
        """助成金候補情報をCSVファイルに書き込みます"""
        try:
            output_path = "/workspace/crewai/dev_grant/result_grants/grants_data/grants_candidates.csv"
            
            # 出力ディレクトリが存在することを確認
            output_dir = os.path.dirname(output_path)
            os.makedirs(output_dir, exist_ok=True)
            
            # ヘッダーを取得（すべての可能なフィールドを含める）
            all_fields = set()
            for grant in grants_data:
                all_fields.update(grant.keys())
            
            headers = sorted(list(all_fields))
            
            with open(output_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(grants_data)
            
            return f"助成金候補が{output_path}に保存されました"
        except Exception as e:
            logger.error(f"CSV書き込みエラー: {str(e)}")
            return f"助成金候補のCSVへの保存エラー: {str(e)}"

class CSVReaderTool(BaseTool):
    """CSVファイルから助成金候補を読み込むツール"""
    
    name: str = "CSVReaderTool"
    description: str = "CSVファイルから助成金候補情報を読み込みます。"
    
    def _run(self, input_path: None) -> List[Dict[str, Any]]:
        """CSVファイルから助成金候補情報を読み込みます"""
        input_path="/workspace/crewai/dev_grant/result_grants/grants_data/grants_candidates.csv"
        try:
            if not os.path.exists(input_path):
                logger.warning(f"CSVファイルが存在しません: {input_path}")
                return []
            
            with open(input_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                grants_data = list(reader)
            
            logger.info(f"{len(grants_data)}件の助成金データを読み込みました: {input_path}")
            return grants_data
        except Exception as e:
            logger.error(f"CSV読み込みエラー: {str(e)}")
            return []

class CSVUpdaterTool(BaseTool):
    """CSVファイルの助成金情報を更新するツール"""
    
    name: str = "CSVUpdaterTool"
    description: str = "CSVファイルの助成金情報を更新します。"

    def _run(self, grant_id: str, updated_data: Dict[str, Any]) -> str:
        """CSVファイルの特定の助成金情報を更新します（効率的なバックアップ機能付き）"""
        csv_path="/workspace/crewai/dev_grant/result_grants/grants_data/grants_candidates.csv"
        try:
            # 現在のデータを読み込む
            if not os.path.exists(csv_path):
                return f"更新できません: ファイルが存在しません: {csv_path}"
                
            with open(csv_path, 'r', encoding='utf-8', newline='') as f:
                reader = csv.DictReader(f)
                grants_data = list(reader)
                headers = reader.fieldnames or []
            
            # 行数を記録
            original_count = len(grants_data)
            
            # 新しいフィールドがあれば追加
            for key in updated_data.keys():
                if key not in headers:
                    headers.append(key)
            
            # 指定されたIDの助成金を更新 (他の行は変更しない)
            updated = False
            for i, grant in enumerate(grants_data):
                if grant.get('id') == grant_id:
                    # ディープコピーして新しいデータで更新
                    updated_grant = grant.copy()
                    updated_grant.update(updated_data)
                    grants_data[i] = updated_grant
                    updated = True
                    break
            
            if not updated:
                return f"ID '{grant_id}' の助成金が見つかりませんでした。"
            
            # 更新したデータを保存（すべての行を保持）
            with open(csv_path, 'w', encoding='utf-8', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                writer.writerows(grants_data)
    
            
            return f"ID '{grant_id}' の助成金情報が正常に更新されました。({len(grants_data)}行のデータを保持)"
        except Exception as e:
            logger.error(f"CSV更新エラー: {str(e)}")
            return f"助成金情報の更新エラー: {str(e)}"