# create_user_preference.py
# PDFファイルからユーザー情報を抽出し、整理してファイルに出力するスクリプト。

import os
import glob
import dotenv
import pymupdf4llm  # pymupdf4llm をPDF読み取り用にインポート
from langchain.chains import LLMChain
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

dotenv.load_dotenv()

# --- 基本設定 ---
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
USER_PDF_DIR = "knowledge"   # PDFが格納されているディレクトリ
OUTPUT_FILE = "knowledge/user_preference.txt"  # 整理済みユーザー情報の出力先

# --- LLMの初期化 ---
chat = ChatGoogleGenerativeAI(
    api_key=GEMINI_API_KEY,
    model="gemini-2.0-flash"
)

# (1) PDFからの生テキスト抽出
def get_raw_text_from_pdfs(directory: str) -> str:
    pdf_files = glob.glob(os.path.join(directory, "*.pdf"))
    all_text = ""
    for pdf_path in pdf_files:
        try:
            text = pymupdf4llm.to_markdown(pdf_path)  # ファイルパスからテキスト抽出
            all_text += text + "\n"
        except Exception as e:
            print(f"Error reading {pdf_path}: {e}")
    return all_text.strip()

# (2) 整理用LLMChainの準備
def organize_user_preferences(raw_text: str) -> str:
    organize_template = """
以下は複数のPDFから抽出したユーザー情報の生テキストです:
{raw_text}

上記テキストから、ユーザーの興味・関心、重要なスキルや希望、その他の関連情報を
整理し、箇条書きで要点のみ抽出してください。
この情報はユーザーが応募すべき公募・助成金情報を特定するために利用されます。
下記の情報について整理してください。
**研究内容・興味:**
**過去の公募・助成金獲得情報:**
**研究実績**
**研究拠点:**
**その他関連情報:**

"""
    organize_prompt = PromptTemplate(template=organize_template, input_variables=["raw_text"])
    organize_chain = LLMChain(llm=chat, prompt=organize_prompt)
    organized_text = organize_chain.run(raw_text=raw_text)
    return organized_text.strip()

# (3) PDF情報の整理とファイル出力
def create_user_preference_file(pdf_directory: str, output_file: str) -> None:
    print("PDFから生テキストを抽出中...")
    raw_text = get_raw_text_from_pdfs(pdf_directory)
    print("抽出完了。整理中...")
    organized_text = organize_user_preferences(raw_text)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(organized_text)
    print(f"整理済みユーザー情報を {output_file} に出力しました。")

if __name__ == "__main__":
    create_user_preference_file(USER_PDF_DIR, OUTPUT_FILE)