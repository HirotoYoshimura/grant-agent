import os
import streamlit as st
import subprocess
import sys
import json
import shutil
import traceback
import pymupdf4llm
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from pathlib import Path
import tempfile
import time
import requests
import pandas as pd
import streamlit.components.v1 as components
from dotenv import load_dotenv

# 特定の.envファイルから環境変数を読み込む
def setup_environment():
    """特定の.envファイルから環境変数を設定する"""
    # 最優先の.envパス
    primary_env_path = os.path.join(os.getcwd(),"src/dev_grant/.env")
    
    if os.path.exists(primary_env_path):
        print(f"優先環境変数ファイルをロード: {primary_env_path}")
        load_dotenv(dotenv_path=primary_env_path, override=True)
        return True
    
    # バックアップの.envパス（primary_env_pathが存在しない場合）
    backup_paths = [
        Path.cwd() / "src" / "dev_grant" / ".env",
        Path.cwd() / ".env",
        Path.cwd().parent / "dev_grant" / ".env",
        Path("crewai/dev_grant/.env")
    ]
    
    for path in backup_paths:
        if path.exists():
            print(f"代替環境変数ファイルをロード: {path}")
            load_dotenv(dotenv_path=path, override=True)
            return True
    
    print("警告: 有効な.envファイルが見つかりませんでした")
    return False

# ディレクトリの存在確認と作成
def ensure_directory_exists(dir_path):
    """再帰エラーを避けながら階層的にディレクトリを作成"""
    if not os.path.exists(dir_path):
        parent = os.path.dirname(dir_path)
        if parent and parent != dir_path:  # 無限ループ防止
            if ensure_directory_exists(parent):
                try:
                    os.mkdir(dir_path)
                except:
                    pass  # エラーを無視
    return os.path.exists(dir_path)

# プロジェクト構造を検出
def detect_project_structure():
    """実行環境を検査してプロジェクト構造を動的に検出"""
    paths = {}
    found_root = False
    
    # 方法1: 特定のパスを優先的に確認
    preferred_path = Path(os.getcwd())
    if preferred_path.exists():
        paths["project_root"] = str(preferred_path)
        found_root = True
    
    # 見つからない場合はカレントディレクトリを使用
    if not found_root:
        current_dir = Path.cwd()
        paths["project_root"] = str(current_dir)
    
    # プロジェクトルートからの相対パスで他のディレクトリを設定
    project_root = Path(paths["project_root"])
    
    # ディレクトリ構造を整理 - プロジェクトルート直下にのみディレクトリを作成
    try:
        # knowledge ディレクトリの作成
        knowledge_dir = project_root / "knowledge"
        ensure_directory_exists(str(knowledge_dir))
        paths["knowledge_dir"] = str(knowledge_dir)
        
        # result_grants ディレクトリの作成
        result_dir = project_root / "result_grants"
        ensure_directory_exists(str(result_dir))
        paths["result_dir"] = str(result_dir)
        
        # grants_data ディレクトリの作成
        grants_data_dir = project_root / "grants_data"
        ensure_directory_exists(str(grants_data_dir))
        paths["grants_data_dir"] = str(grants_data_dir)
        
        # config ディレクトリの作成
        config_dir = project_root / "config"
        ensure_directory_exists(str(config_dir))
        paths["config_dir"] = str(config_dir)
        
        # uploads ディレクトリの作成
        uploads_dir = knowledge_dir / "user_info_pdfs"
        ensure_directory_exists(str(uploads_dir))
        paths["uploads_dir"] = str(uploads_dir)
    
    except Exception as e:
        # ディレクトリ作成に失敗した場合は一時ディレクトリを使用
        print(f"ディレクトリ作成エラー: {str(e)}")
        temp_dirs = {}
        for dir_name in ["knowledge", "result_grants", "uploads", "config", "grants_data"]:
            temp_dir = tempfile.mkdtemp(prefix=f"crewai_{dir_name}_")
            key_name = f"{dir_name}_dir" if dir_name != "uploads" else "uploads_dir"
            temp_dirs[key_name] = temp_dir
            paths[key_name] = temp_dir
    
    return paths

# セッション状態の初期化
def initialize_session_state():
    """セッション状態変数を初期化"""
    # ページナビゲーション用の変数
    if 'page' not in st.session_state:
        st.session_state.page = "フローチャート"
    
    # 基本的なセッション状態
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
        st.session_state.direct_paths = None
        st.session_state.api_keys = {}
        st.session_state.profile_path = None
        st.session_state.run_completed = False
        st.session_state.run_results = None
        st.session_state.use_ai = True
        
        # ログ関連の状態
        st.session_state.log_text = "Execution Log:\n"
        st.session_state.log_visible = True
        
        # エージェント別モデル情報
        if 'agent_models' not in st.session_state:
            st.session_state.agent_models = {
                "profile_analyzer": "gemini-2.0-flash-thinking-exp-01-21",
                "hypotheses_generator": "gemini-2.0-flash-thinking-exp-01-21",
                "query_generator": "gemini-2.0-flash-thinking-exp-01-21",
                "search_expert": "gemini-2.0-flash",
                "report_generator": "gemini-2.0-flash-thinking-exp-01-21",
                "user_proxy": "gemini-2.0-flash-thinking-exp-01-21",
                "investigation_evaluator": "gemini-2.5-pro-exp-03-25"
            }
        
        # 環境変数から初期APIキーを取得
        api_keys = {
            "GOOGLE_API_KEY": os.environ.get("GOOGLE_API_KEY", ""),
            "GOOGLE_CSE_ID": os.environ.get("GOOGLE_CSE_ID", ""),
            "GEMINI_API_KEY": os.environ.get("GEMINI_API_KEY", "")
        }
        st.session_state.api_keys = api_keys
    
    # ディレクトリパスの初期化
    if st.session_state.direct_paths is None:
        st.session_state.direct_paths = detect_project_structure()

# 環境変数ファイルを作成する関数
def create_env_file(api_keys, project_root):
    """APIキーを環境変数に設定し、可能であれば.envファイルに書き込む"""
    try:  
        # 環境変数に設定 - これは常に動作する
        for key, value in api_keys.items():
            if value:  # 値が存在する場合のみ更新
                os.environ[key] = value
        
        # ファイル保存を試みる
        try:
            # 優先的に更新する.envファイルのパス
            primary_env_path = os.path.join(os.getcwd(), "src/dev_grant/.env")
            
            # ディレクトリ作成は直接パスで実行
            env_dir = os.path.dirname(primary_env_path)
            if not os.path.exists(env_dir):
                try:
                    parent = os.path.dirname(env_dir)
                    if not os.path.exists(parent):
                        os.mkdir(parent)
                    os.mkdir(env_dir)
                except Exception:
                    pass
            
            # .envファイルが存在する場合のみ更新
            if os.path.exists(primary_env_path):
                # 既存の内容を読み込む
                existing_env = {}
                with open(primary_env_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            key, value = line.split('=', 1)
                            existing_env[key.strip()] = value.strip()
                
                # 新しいAPIキーで更新
                for key, value in api_keys.items():
                    if value:  # 値が存在する場合のみ更新
                        existing_env[key] = value
                
                # 更新された内容を書き込み
                with open(primary_env_path, 'w') as f:
                    for key, value in existing_env.items():
                        f.write(f"{key}={value}\n")
                
                return True, f"APIキーを環境変数に設定し、.envファイルを更新しました: {primary_env_path}"
            else:
                # .envファイルがない場合は新規作成
                try:
                    with open(primary_env_path, 'w') as f:
                        for key, value in api_keys.items():
                            if value:  # 値が存在する場合のみ書き込み
                                f.write(f"{key}={value}\n")
                    return True, f"APIキーを環境変数に設定し、新規.envファイルを作成しました: {primary_env_path}"
                except Exception as file_error:
                    # ファイル作成エラーは報告するが、環境変数は設定済み
                    return True, f"APIキーを環境変数に設定しました（.envファイルの作成に失敗: {str(file_error)}）"
        except Exception as file_op_error:
            # ファイル操作エラーは報告するが、環境変数は設定済み
            return True, f"APIキーを環境変数に設定しました（.envファイルの操作に失敗: {str(file_op_error)}）"
            
    except Exception as e:
        # 環境変数設定にも失敗した場合
        return False, f"環境変数の設定に失敗しました: {str(e)}"

# PDFからテキストを抽出する関数
def extract_text_from_pdf(pdf_path, progress_bar=None, status_text=None):
    """PDFファイルからテキストを抽出する（進捗表示付き）"""
    try:
        if status_text:
            status_text.write("PDFからテキストを抽出中...")
        
        text = pymupdf4llm.to_markdown(pdf_path)
        
        if status_text:
            status_text.write("テキスト抽出が完了しました")
        
        return text
    except Exception as e:
        error_details = traceback.format_exc()
        if status_text:
            status_text.error(f"PDFからのテキスト抽出エラー: {str(e)}")
        st.error(f"PDFからのテキスト抽出中にエラーが発生しました: {str(e)}\n{error_details}")
        return None

# PDFからユーザープロファイルを生成する関数
def process_pdf_to_profile(pdf_path, output_path, use_ai=True, progress_bar=None, status_text=None):
    """PDFからユーザープロファイルを生成し保存する（進捗表示付き）"""
    try:
        # ステップ1: PDFからテキスト抽出
        if status_text:
            status_text.write("ステップ1/3: PDFからテキストを抽出しています...")
        
        extracted_text = extract_text_from_pdf(pdf_path, progress_bar, status_text)
        
        if not extracted_text:
            return False, "テキスト抽出に失敗しました", None
        
        if progress_bar:
            progress_bar.progress(33)
        
        # ステップ2: テキストの前処理と整形
        if status_text:
            status_text.write("ステップ2/3: テキストを処理しています...")
        
        # 長すぎる場合は切り詰め
        if len(extracted_text) > 10000:
            processed_text = extracted_text[:10000] + "...(長いため省略)"
        else:
            processed_text = extracted_text
        
        if progress_bar:
            progress_bar.progress(66)
        
        # ステップ3: プロファイル生成（AIを使用するかどうかで分岐）
        if status_text:
            status_text.write("ステップ3/3: プロファイル情報を生成しています...")
        
        if use_ai and 'api_keys' in st.session_state and st.session_state.api_keys.get("GEMINI_API_KEY"):
            # Gemini APIを使ってテキストを整理する
            try:
                # Gemini APIキーを設定
                os.environ["GOOGLE_API_KEY"] = st.session_state.api_keys.get("GEMINI_API_KEY", "")
                
                if status_text:
                    status_text.write("Gemini APIを使用してプロファイル情報を整理しています...")
                
                # LLMの初期化
                chat = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    temperature=0.3
                )
                
                # プロンプトの作成
                organize_template = """
                以下は複数のPDFから抽出したユーザー情報の生テキストです:
                {text}

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
                
                organize_prompt = PromptTemplate(template=organize_template, input_variables=["text"])
                organize_chain = LLMChain(llm=chat, prompt=organize_prompt)
                
                # テキスト整理
                result = organize_chain.invoke({"text": processed_text})
                organized_text = result.get("text", "")
                
                # 整理されたテキストを保存
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(organized_text)
                
                if status_text:
                    status_text.success("プロファイル処理が完了しました！")
                
                if progress_bar:
                    progress_bar.progress(100)
                
                return True, "PDFからプロファイルを抽出し、AIで整理しました", organized_text
                
            except Exception as e:
                error_details = traceback.format_exc()
                if status_text:
                    status_text.warning(f"AI処理エラー: {str(e)}")
                    status_text.warning("テキスト抽出のみを行います")
                
                # AIが失敗した場合は生テキストを保存
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(processed_text)
                
                if progress_bar:
                    progress_bar.progress(100)
                
                return True, f"PDFからテキストを抽出しました（AI処理なし）。エラー: {str(e)}", processed_text
        else:
            # AI処理なしでテキストを保存
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(processed_text)
            
            if status_text:
                status_text.success("テキスト抽出が完了しました！")
            
            if progress_bar:
                progress_bar.progress(100)
            
            return True, "PDFからテキストを抽出しました", processed_text
            
    except Exception as e:
        error_details = traceback.format_exc()
        if status_text:
            status_text.error(f"PDFの処理中にエラー: {str(e)}")
        
        if progress_bar:
            progress_bar.progress(0)
        
        return False, f"PDFの処理中にエラーが発生しました: {str(e)}\n{error_details}", None

# Google APIテスト関数
def test_google_api():
    """Google APIテストを実行する関数"""
    
    # 現在の環境変数から取得
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    cse_id = os.environ.get("GOOGLE_CSE_ID", "")
    
    if not api_key or not cse_id:
        return False, "APIキーまたはCSE IDが設定されていません", None
    
    try:
        # 直接APIリクエストを送信
        url = f"https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": cse_id,
            "q": "test"
        }
        
        # リクエスト情報
        request_info = {
            "url": url,
            "params": {
                "key": f"{'*' * (len(api_key)-4) + api_key[-4:] if api_key else 'なし'}",
                "cx": f"{'*' * (len(cse_id)-4) + cse_id[-4:] if cse_id else 'なし'}",
                "q": "test"
            }
        }
        
        response = requests.get(url, params=params)
        
        # レスポンス情報
        response_info = {
            "status_code": response.status_code,
            "headers": dict(response.headers)
        }
        
        # レスポンスのJSON
        try:
            response_json = response.json()
        except:
            response_json = None
        
        return True, f"APIテスト完了 (ステータス: {response.status_code})", {
            "request": request_info,
            "response": response_info,
            "data": response_json
        }
    except Exception as e:
        error_details = traceback.format_exc()
        return False, f"APIテスト中にエラーが発生: {str(e)}", {
            "error": str(e),
            "details": error_details
        }

# コマンド実行前にcrewai runコマンドが利用可能か確認する関数
def check_crewai_command():
    """crewai runコマンドが利用可能かどうかをチェック"""
    # 結果を格納する変数
    available = False
    path_info = None
    error_messages = []
    
    # 方法1: shutil.which でパスを確認
    try:
        crewai_path = shutil.which('crewai')
        if crewai_path:
            available = True
            path_info = crewai_path
            return True, path_info
    except Exception as e:
        error_messages.append(f"shutil.which('crewai')エラー: {str(e)}")
    
    # 方法2: コマンドを実行して確認
    try:
        result = subprocess.run(
            ["crewai", "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=3  # タイムアウト設定
        )
        if result.returncode == 0:
            available = True
            path_info = "crewai (コマンドが利用可能)"
            return True, path_info
    except:
        pass
    
    # すべての方法が失敗した場合
    if error_messages:
        path_info = f"crewaiコマンドが見つかりません。"
    else:
        path_info = "crewaiコマンドが見つかりません"
    
    return available, path_info

# Python実行ファイルをフォールバックとして実行
def run_python_script_fallback(project_paths, profile_path, output_path, grants_count=1, result_column=None):
    """Python スクリプトを直接実行するフォールバック関数（セッション状態問題修正版）"""
    # スクリプトを探す
    script_locations = [
        os.path.join(project_paths.get("project_root", ""), "src/dev_grant/main.py"),
        os.path.join(project_paths.get("project_root", ""), "src/dev_grant/crew.py"),
        os.path.join(project_paths.get("project_root", ""), "main.py"),
        os.path.join(project_paths.get("project_root", ""), "crew.py"),
    ]
    
    script_path = None
    working_dir = None
    
    for path in script_locations:
        if os.path.isfile(path):
            script_path = path
            working_dir = os.path.dirname(path)
            break
    
    if not script_path:
        if result_column:
            result_column.error("実行可能なスクリプトが見つかりません (main.py または crew.py)")
        return False, "実行可能なスクリプトが見つかりません (main.py または crew.py)"
    
    # 環境設定
    env = os.environ.copy()
    env["PROFILE_PATH"] = profile_path
    env["OUTPUT_PATH"] = output_path
    env["GRANTS_COUNT"] = str(grants_count)
    env["PYTHONPATH"] = f"{project_paths['project_root']}:{env.get('PYTHONPATH', '')}"
    
    # エージェント別モデル設定を環境変数に追加
    if 'agent_models' in st.session_state:
        for agent, model in st.session_state.agent_models.items():
            env[f"MODEL_{agent.upper()}"] = model

    # APIキーをセッション状態から設定
    for key, value in st.session_state.api_keys.items():
        if value:
            env[key] = value
    
    # スクリプトタイプに基づいてコマンドを作成
    command = [sys.executable, script_path]
    if script_path.endswith("main.py"):
        # main.py の場合はコマンドライン引数を使用
        command += ["--profile", profile_path, "--output", output_path, "--grants", str(grants_count)]
    elif script_path.endswith("crew.py"):
        # crew.py の場合は必要なパラメータを設定
        command += ["--grants_count", str(grants_count)]

    # 環境変数も明示的に設定（冗長性を持たせる）
    env["GRANTS_COUNT"] = str(grants_count)
    env["MAX_ROUNDS"] = str(grants_count)  # 別名でも設定しておく
    
    # コマンド情報を表示
    log_info = f"実行スクリプト: {os.path.basename(script_path)}\n- 検索する助成金数: {grants_count}\n- プロファイル: /workspace/crewai/dev_grant/knowledge/user_preference.txt"
    
    # セッション状態にログテキストを初期化/設定
    if 'log_text' not in st.session_state:
        st.session_state.log_text = "実行ログ:\n"
    
    if 'clear_logs' in st.session_state and st.session_state.clear_logs:
        st.session_state.log_text = "実行ログ:\n"
        st.session_state.clear_logs = False
    
    # 結果カラムが指定されている場合はそこに表示
    if result_column:
        # 新しいコンテナを毎回作成（セッション状態には保存しない）
        status_container = result_column.empty()
        status_container.info(log_info)
        
        # ログ表示用のコンテナ
        log_container = result_column.empty()
        log_container.code(st.session_state.log_text, language="bash", height=500)
    else:
        # 結果カラムが指定されていない場合
        st.info(log_info)
        log_container = st.empty()
        log_container.code(st.session_state.log_text, language="bash", height=500)
    
    # サブプロセスでリアルタイム出力キャプチャ
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
        cwd=working_dir,
        env=env
    )
    
    # リアルタイム出力をキャプチャして表示
    while True:
        output = process.stdout.readline()
        if output == '' and process.poll() is not None:
            break
        if output:
            # ログテキストをセッション状態に累積
            st.session_state.log_text += output
            # 各イテレーションで新しいコードブロックを表示
            log_container.code(st.session_state.log_text, language="bash", height=500)
    
    # 戻り値コードを取得して最終処理
    return_code = process.poll()
    
    if return_code == 0:
        if result_column:
            status_container.success("助成金検索が正常に完了しました")
        return True, st.session_state.log_text
    else:
        if result_column:
            status_container.error(f"プロセスが終了コード {return_code} で失敗しました")
        return False, st.session_state.log_text

def render_mermaid_v2(code):
    """
    最新のMermaid（バージョン10.x）を使用して図を描画する
    この関数はStreamlitでMermaid図を表示するための改良版です
    """
    # HTML文字列をエスケープ
    escaped_code = code.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta http-equiv="X-UA-Compatible" content="IE=edge">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        
        <!-- 最新のMermaidバージョンを使用 -->
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js"></script>
        <style>
            .mermaid {{
                text-align: center;
                width: 100%;
            }}
        </style>
    </head>
    <body>
        <div class="mermaid" id="mermaid-diagram"></div>
        
        <script>
            document.addEventListener('DOMContentLoaded', function() {{
                try {{
                    // 初期化
                    mermaid.initialize({{ 
                        startOnLoad: false,
                        theme: 'default',
                        securityLevel: 'loose',
                        logLevel: 'fatal',
                        fontFamily: 'arial'
                    }});
                    
                    // コードをレンダリング
                    const graphCode = `{escaped_code}`;
                    
                    // エラーが発生したときに備えて短い遅延を使用
                    setTimeout(() => {{
                        const element = document.getElementById('mermaid-diagram');
                        mermaid.render('mermaid-svg', graphCode).then(result => {{
                            element.innerHTML = result.svg;
                        }}).catch(error => {{
                            console.error('Mermaid rendering error:', error);
                            element.innerHTML = '<div style="color: red; text-align: center;">図の描画に失敗しました: ' + error.message + '</div>';
                        }});
                    }}, 100);
                }} catch(e) {{
                    console.error('Mermaid initialization error:', e);
                    document.getElementById('mermaid-diagram').innerHTML = 
                        '<div style="color: red; text-align: center;">Mermaidの初期化に失敗しました: ' + e.message + '</div>';
                }}
            }});
        </script>
    </body>
    </html>
    """
    
    # HTMLコンポーネントとして表示
    components.html(html, height=600, scrolling=True)

# フォールバック方法として静的な画像を表示する関数
def display_static_flowchart():
    """
    Mermaidが動作しない場合に備えて静的なフローチャート画像を表示
    """
    st.image("https://via.placeholder.com/800x500.png?text=助成金検索エージェントフローチャート", 
             caption="助成金検索エージェントのフロー図", 
             use_column_width=True)
    
    st.markdown("""
    ### フローの説明
    1. **研究者プロファイル** - 入力情報
    2. **プロファイル分析者** - 研究興味や優先事項を抽出
    3. **仮説生成者** - 助成金カテゴリの仮説を生成
    4. **クエリ生成者** - 検索クエリを作成
    5. **検索専門家** - 助成金情報を収集
    6. **ユーザー代理** - 最適な助成金を選択
    7. **検索専門家** - 詳細情報を収集
    8. **レポート生成者** - 情報を整理・評価
    9. **結果** - 構造化された助成金情報
    """)

# フローチャートページの表示を改善した関数
def show_improved_flowchart_page():
    st.title("📊 助成金検索エージェントのフロー")
    
    st.markdown("""
    ## 助成金検索エージェントの仕組み
    
    このアプリケーションは、複数のAIエージェントが協力して最適な助成金を見つけるシステムです。
    各エージェントは特定の役割を持ち、順番に処理を行いながら結果を改善していきます。
    """)
    
    # フローチャート表示を試みる
    st.subheader("エージェント連携の仕組み")
    
    try:
        # Mermaidでフローチャートを作成
        mermaid_code = """
        flowchart TD
            Start([研究者プロファイル]) --> InitialPhase
            
            subgraph InitialPhase["初期情報収集フェーズ"]
                A[プロファイル分析者<br>研究興味や優先事項を抽出] --> B
                B[仮説生成者<br>助成金カテゴリの仮説を生成] --> C
                C[クエリ生成者<br>効果的な検索クエリを作成] --> D
                D[検索専門家<br>助成金候補情報を収集<br>CSV形式で保存]
            end
            
            InitialPhase --> E
            
            subgraph InvestigationLoop["詳細調査ループ (指定した件数分)"]
                E[ユーザー代理<br>次に調査する助成金を選択] --> InvestProcess
                
                subgraph InvestProcess["調査プロセス"]
                    subgraph EvalLoop["評価・再調査ループ"]
                        F[検索専門家<br>選択された助成金の<br>詳細情報を収集] --> G
                        G[調査評価者<br>収集情報の完全性を評価] --> Decision{十分な情報か?}
                        Decision -->|不足情報あり| ReInvest[再調査指示]
                        ReInvest --> F
                        Decision -->|情報完成| LoopEnd[評価完了]
                    end
                    
                    LoopEnd --> I
                    I[レポート生成者<br>関連性・完全性を評価<br>CSVファイルを更新]
                end
                
                I --> NextGrant{全件数調査完了?}
                NextGrant -->|No| E
                NextGrant -->|Yes| End
            end
            
            End --> Results([最終結果<br>構造化された助成金情報])
            
            %% スタイル設定
            classDef phaseBox fill:#f5f5f5,stroke:#333,stroke-width:1px,rx:5px,ry:5px
            classDef evalLoopBox fill:#f0f8ff,stroke:#333,stroke-width:1px,rx:5px,ry:5px
            classDef analyzerAgent fill:#ffd700,stroke:#333,stroke-width:2px,rx:10px,ry:10px
            classDef searchAgent fill:#90ee90,stroke:#333,stroke-width:2px,rx:10px,ry:10px
            classDef evaluatorAgent fill:#add8e6,stroke:#333,stroke-width:2px,rx:10px,ry:10px
            classDef reportAgent fill:#ffb6c1,stroke:#333,stroke-width:2px,rx:10px,ry:10px
            classDef decision fill:#f9f9f9,stroke:#333,stroke-width:1px,rx:10px,ry:10px
            classDef startEnd fill:#e6e6e6,stroke:#333,stroke-width:2px,rx:15px,ry:15px
            
            class InitialPhase,InvestigationLoop phaseBox
            class EvalLoop evalLoopBox
            class A,B,C analyzerAgent
            class D,F searchAgent
            class G,E evaluatorAgent
            class I reportAgent
            class Decision,NextGrant decision
            class Start,Results startEnd
        """
        
        # 改良したレンダリング関数を使用
        render_mermaid_v2(mermaid_code)
        
    except Exception as e:
        st.error(f"フローチャートの表示中にエラーが発生しました: {str(e)}")
        # フォールバックとして静的な説明を表示
        display_static_flowchart()
    
    # エージェント詳細説明
    st.subheader("エージェントの役割")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        ### 👨‍🔬 プロファイル分析者
        - 研究者のプロファイルを分析し、研究興味とキーワードを抽出
        - 学術的背景やキャリアステージを理解
        - 助成金検索に役立つ重要要素を特定
        
        ### 🧠 仮説生成者
        - ユーザープロファイルに基づいて候補となる助成金カテゴリを提案
        - 研究分野や背景に適した助成金タイプを特定
        - 最も関連性の高いカテゴリを選定
        
        ### 🔍 クエリ生成者
        - ユーザープロファイルに合った検索クエリを作成
        - 最適な結果を得るための効果的な検索語を選定
        - 多様な情報源からの検索を最適化
        """)
    
    with col2:
        st.markdown("""
        ### 🌐 検索専門家
        - オンラインで助成金情報を検索収集
        - ウェブページやPDFから情報を抽出
        - 初期候補リストと詳細情報の両方を担当
        
        ### 👤 ユーザー代理
        - ユーザーの研究プロファイルを理解
        - 最適な助成金機会を選択
        - 優先順位を決定して調査対象を選定
        
        ### 🔎 評価者
        - 収集された情報の完全性を評価
        - 不足情報を特定し再調査を指示
        - 詳細調査の質を保証
        
        ### 📊 レポート生成者
        - 助成金情報を整理統合
        - 関連性と完全性スコアを付与
        - CSVファイルを更新
        """)
    
    # 検索プロセスの説明
    st.subheader("検索プロセスの流れ")
    
    st.markdown("""
    ### 1. 初期情報収集フェーズ
    1. **プロファイル解析**: 研究者の専門分野、興味、キャリアステージを特定
    2. **カテゴリ仮説**: 関連する可能性のある助成金カテゴリを生成
    3. **クエリ生成**: 効果的な検索クエリを作成
    4. **助成金検索**: インターネットから助成金候補情報を収集しCSVに保存
    
    ### 2. 詳細調査ループ（設定した助成金数分繰り返し）
    1. **候補選定**: ユーザー代理が最も関連性の高い助成金を選択
    2. **詳細調査**: 検索専門家が選択された助成金の詳細情報を収集
    3. **評価**: 収集された情報の完全性を評価
    4. **再調査**: 必要に応じて不足情報を再収集（情報が完全になるまで）
    5. **最終評価**: レポート生成者が情報を整理し、関連性・完全性スコアを付与
    6. **データ更新**: CSVファイルに最終結果を反映
    
    ### 3. 結果の提供
    - 調査が完了した助成金情報を構造化されたデータとして提供
    - ユーザーは最適な助成金を選択・応募できる
    """)
    
    # 注意事項
    st.info("""
    ⚠️ **注意**: このシステムを効果的に使用するためには、研究プロファイル情報が正確であることが重要です。
    次のページでAPIキーを設定し、その後プロファイル情報を入力してください。
    """)
    
    # 次のページへ
    st.button("次へ: 環境設定 ⚙️", on_click=lambda: setattr(st.session_state, 'page', "設定"), use_container_width=True)

# 環境設定ページの表示
def show_settings_page():
    st.title("⚙️ 環境設定")
    
    st.markdown("""
    ## API設定とシステム環境
    
    助成金検索エージェントを実行するためには、以下のAPIキーが必要です：
    1. Google API Key - Google検索に使用
    2. Google Custom Search Engine ID - カスタム検索エンジン識別子
    3. Google Gemini API Key - Gemini AIモデルを使用するため
    """)
    
    # API設定フォーム
    with st.form("api_keys_form"):
        st.subheader("API設定")
        
        google_api_key = st.text_input(
            "Google API Key", 
            type="password",
            value=st.session_state.api_keys.get("GOOGLE_API_KEY", "")
        )
        
        google_cse_id = st.text_input(
            "Google Custom Search Engine ID", 
            type="password",
            value=st.session_state.api_keys.get("GOOGLE_CSE_ID", "")
        )
        
        gemini_api_key = st.text_input(
            "Google Gemini API Key", 
            type="password",
            value=st.session_state.api_keys.get("GEMINI_API_KEY", "")
        )
        
        use_ai = st.checkbox("プロファイル処理にAIを使用", value=True)
        
        st.markdown("---")
        
        # エージェント別モデル設定
        st.subheader("エージェント別モデル設定")
        st.caption("各エージェントが使用するGeminiモデルを選択できます")
        
        # 利用可能なGeminiモデル
        gemini_models = [
            "gemini-1.5-pro",
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite", 
            "gemini-2.0-flash-thinking-exp-01-21",
            "gemini-2.5-pro-exp-03-25",
        ]

        # エージェント情報
        agents = {
            "profile_analyzer": "プロファイル分析者",
            "hypotheses_generator": "仮説生成者",
            "query_generator": "クエリ生成者",
            "search_expert": "検索専門家",
            "report_generator": "レポート生成者",
            "user_proxy": "ユーザー代理",
            "investigation_evaluator": "監督者"
        }

        # タブ形式でエージェント別に設定
        tabs = st.tabs(list(agents.values()))

        for i, (agent_key, agent_name) in enumerate(agents.items()):
            with tabs[i]:
                # エージェント説明
                descriptions = {
                    "profile_analyzer": "ユーザープロファイルを分析し、助成金に関連する研究興味と優先事項を抽出します",
                    "hypotheses_generator": "ユーザープロファイルに基づいて公募・助成金カテゴリの仮説を生成します",
                    "query_generator": "効果的な検索クエリを生成します",
                    "search_expert": "オンライン検索で助成金情報を収集・構造化します",
                    "report_generator": "助成金情報を整理して最終レポートを作成します",
                    "user_proxy": "ユーザーの研究プロファイルを理解し、最適な助成金機会を選択します",
                    "investigation_evaluator": "詳細調査結果を評価し、再調査の必要有無を判断します"
                }
                
                st.write(descriptions.get(agent_key, ""))
                
                # 現在選択されているモデルをデフォルトに
                current_model = st.session_state.agent_models.get(agent_key, gemini_models[0])
                default_index = gemini_models.index(current_model) if current_model in gemini_models else 0
                
                # モデル選択ドロップダウン
                model = st.selectbox(
                    f"{agent_name}用モデル",
                    options=gemini_models,
                    index=default_index,
                    key=f"select_{agent_key}"
                )
                
                # セッション状態に保存（リアルタイム更新）
                st.session_state.agent_models[agent_key] = model
        
        # 送信ボタン
        submit_keys = st.form_submit_button("設定を保存")
        
        if submit_keys:
            api_keys = {
                "GOOGLE_API_KEY": google_api_key,
                "GOOGLE_CSE_ID": google_cse_id,
                "GEMINI_API_KEY": gemini_api_key
            }
            
            # セッション状態に保存
            st.session_state.api_keys = api_keys
            st.session_state.use_ai = use_ai
            
            # 環境変数に設定
            for key, value in api_keys.items():
                if value:
                    os.environ[key] = value
            
            # .envファイルに保存
            success, result = create_env_file(
                api_keys, 
                st.session_state.direct_paths["project_root"]
            )
            
            if success:
                st.success(f"APIキーを保存しました")
            else:
                st.error(result)
    
    # 環境チェック
    st.subheader("環境チェック")
    
    # 認証状態チェック
    check_col1, check_col2 = st.columns(2)
    
    with check_col1:
        # Google API Check
        if st.button("Google API接続テスト", use_container_width=True):
            with st.spinner("Google APIをテスト中..."):
                success, message, details = test_google_api()
                if success:
                    st.success(message)
                    with st.expander("詳細"):
                        st.json(details)
                else:
                    st.error(message)
                    if details:
                        with st.expander("エラー詳細"):
                            st.json(details)
    
    with check_col2:
        # CrewAI Command Check
        if st.button("CrewAIコマンド確認", use_container_width=True):
            with st.spinner("CrewAIコマンドをチェック中..."):
                available, message = check_crewai_command()
                if available:
                    st.success(f"CrewAIコマンドが利用可能です: {message}")
                else:
                    st.warning(f"CrewAIコマンドが利用できません。Python実行にフォールバックします。{message}")
    
    # ディレクトリ構造チェック
    with st.expander("ディレクトリ構造確認"):
        if 'direct_paths' in st.session_state:
            for key, path in st.session_state.direct_paths.items():
                st.text(f"{key}: {path}")
                if os.path.exists(path):
                    st.success(f"✅ パスが存在します")
                else:
                    st.error(f"❌ パスが存在しません")
    
    # ナビゲーションボタン
    col1, col2 = st.columns(2)
    with col1:
        st.button("戻る: フローチャート 📊", on_click=lambda: setattr(st.session_state, 'page', "フローチャート"), use_container_width=True)
    with col2:
        st.button("次へ: 実行ページ 🚀", on_click=lambda: setattr(st.session_state, 'page', "実行"), use_container_width=True)

# 実行ページの表示
def show_execution_page():
    st.title("🚀 助成金検索実行")
    
    st.markdown("""
    ## 研究者プロファイル入力と検索実行
    
    研究者のプロファイル情報を入力して、最適な助成金の検索を実行します。
    PDFをアップロードするか、テキストで情報を直接入力してください。
    """)
    
    # 2カラムレイアウト
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("研究者プロファイル入力")
        
        # プロファイル入力オプション
        profile_option = st.radio(
            "プロファイル入力方法:",
            ["テキスト入力", "PDF アップロード"]
        )
        
        if profile_option == "PDF アップロード":
            # プロファイルパスを設定
            profile_path = os.path.join(
                st.session_state.direct_paths["knowledge_dir"], 
                "user_preference.txt"
            )
            
            # 既存のプロファイルをチェック
            profile_exists = os.path.exists(profile_path)
            file_option = "上書きする"
            
            if profile_exists:
                try:
                    with open(profile_path, "r", encoding="utf-8") as f:
                        existing_content = f.read()
                    
                    st.subheader("既存のプロファイル情報")
                    st.text_area(
                        "現在のプロファイル内容", 
                        value=existing_content[:2000] + ("..." if len(existing_content) > 2000 else ""),
                        height=150, 
                        disabled=True
                    )
                    
                    # ファイル処理オプション
                    file_option = st.radio(
                        "既存のプロファイルの処理方法:",
                        ["上書きする", "追記する", "新規ファイルを作成する"]
                    )
                except Exception as e:
                    st.warning(f"既存プロファイルの読み込みエラー: {str(e)}")
            
            # PDF アップロード
            uploaded_files = st.file_uploader("研究者プロファイルPDFをアップロード", type=["pdf"], accept_multiple_files=True)
            
            if uploaded_files and len(uploaded_files) > 0:
                # PDFファイル数表示
                st.info(f"{len(uploaded_files)}個のPDFファイルがアップロードされました")
                
                # アップロード保存
                uploads_dir = st.session_state.direct_paths["uploads_dir"]
                ensure_directory_exists(str(uploads_dir))
                pdf_paths = []
                for i, uploaded_file in enumerate(uploaded_files):
                    pdf_path = os.path.join(uploads_dir, f"user_profile_{i+1}.pdf")
                    with open(pdf_path, "wb") as f:
                        f.write(uploaded_file.getbuffer())
                    pdf_paths.append(pdf_path)
                
                # 新規ファイルの場合
                if profile_exists and file_option == "新規ファイルを作成する":
                    timestamp = int(time.time())
                    profile_path = os.path.join(
                        st.session_state.direct_paths["knowledge_dir"], 
                        f"user_preference_{timestamp}.txt"
                    )
                    st.info(f"新規ファイルを作成します: {os.path.basename(profile_path)}")
                
                # 処理状態表示
                pdf_process_status = st.empty()
                progress_bar = st.progress(0)
                
                # 処理方法選択
                processing_method = st.radio(
                    "処理方法:",
                    ["順次処理 (トークン制限対策)", "一括処理"],
                    index=0
                )
                
                # 処理ボタン
                if st.button("PDFを処理", key="process_pdf_button"):
                    with st.spinner(f"{len(uploaded_files)}個のPDFを処理中..."):
                        if processing_method == "順次処理 (トークン制限対策)":
                            # 順次処理
                            total_pdfs = len(pdf_paths)
                            current_text = ""
                            
                            # 既存ファイルの読み込み（追記モードの場合）
                            if file_option == "追記する" and os.path.exists(profile_path):
                                with open(profile_path, "r", encoding="utf-8") as f:
                                    current_text = f.read() + "\n\n=== 新規追加情報 ===\n\n"
                            
                            pdf_process_status.write(f"合計{total_pdfs}個のPDFを順次処理します")
                            
                            # Gemini API初期化
                            use_ai = st.session_state.get('use_ai', True)
                            chat = None
                            if use_ai and 'api_keys' in st.session_state and st.session_state.api_keys.get("GEMINI_API_KEY"):
                                os.environ["GOOGLE_API_KEY"] = st.session_state.api_keys.get("GEMINI_API_KEY", "")
                                from langchain_google_genai import ChatGoogleGenerativeAI
                                from langchain.chains import LLMChain
                                from langchain.prompts import PromptTemplate
                                
                                chat = ChatGoogleGenerativeAI(
                                    model="gemini-2.0-flash",
                                    temperature=0.3
                                )
                            
                            # PDFごとに処理
                            for i, pdf_path in enumerate(pdf_paths):
                                pdf_process_status.write(f"PDF {i+1}/{total_pdfs} を処理中: {os.path.basename(pdf_path)}")
                                progress_bar.progress((i+0.5) / total_pdfs)
                                
                                # PDFからテキスト抽出
                                extracted_text = extract_text_from_pdf(pdf_path)
                                if not extracted_text:
                                    pdf_process_status.warning(f"PDF {i+1}の抽出に失敗")
                                    continue
                                    
                                # 最初のPDFかつ追記モードでない場合
                                if i == 0 and not current_text:
                                    current_text = f"=== {os.path.basename(pdf_path)} ===\n\n{extracted_text}"
                                    with open(profile_path, "w", encoding="utf-8") as f:
                                        f.write(current_text)
                                    pdf_process_status.success(f"PDF {i+1}を初期プロファイルとして保存")
                                
                                # 2つ目以降のPDFまたは追記モード
                                else:
                                    new_text = f"\n\n=== {os.path.basename(pdf_path)} ===\n\n{extracted_text}"
                                    
                                    # AIで統合
                                    if use_ai and chat:
                                        try:
                                            pdf_process_status.write("AIで情報を統合中...")
                                            
                                            update_template = """
                                            これまでのプロファイル情報:
                                            {current_text}
                                            
                                            新しいドキュメントの情報:
                                            {new_text}
                                            
                                            上記の情報を統合して整理してください。新しい情報を優先し、矛盾がある場合は最新情報を採用。
                                            
                                            この情報から公募・助成金検索用のプロファイルを作成します。
                                            以下の形式で整理してください:
                                            **研究内容・興味:**
                                            **過去の助成金獲得情報:**
                                            **研究実績:**
                                            **研究拠点:**
                                            **その他情報:**
                                            """
                                            
                                            update_prompt = PromptTemplate(
                                                template=update_template, 
                                                input_variables=["current_text", "new_text"]
                                            )
                                            update_chain = LLMChain(llm=chat, prompt=update_prompt)
                                            
                                            result = update_chain.invoke({
                                                "current_text": current_text, 
                                                "new_text": new_text
                                            })
                                            current_text = result.get("text", "")
                                            
                                            with open(profile_path, "w", encoding="utf-8") as f:
                                                f.write(current_text)
                                            
                                            pdf_process_status.success(f"PDF {i+1}の情報を統合しました")
                                        except Exception as e:
                                            pdf_process_status.warning(f"AI統合エラー: {str(e)}. テキストのみ追加します")
                                            current_text += new_text
                                            with open(profile_path, "w", encoding="utf-8") as f:
                                                f.write(current_text)
                                    else:
                                        # 単純追加
                                        current_text += new_text
                                        with open(profile_path, "w", encoding="utf-8") as f:
                                            f.write(current_text)
                                        pdf_process_status.info(f"PDF {i+1}のテキストを追加しました")
                            
                            progress_bar.progress(1.0)
                            pdf_process_status.success(f"全{total_pdfs}個のPDFの処理が完了しました")
                            success = True
                            message = f"{total_pdfs}個のPDFを処理しました"
                            extracted_text = current_text
                        else:
                            # 一括処理
                            if len(pdf_paths) == 1 and (not profile_exists or file_option == "上書きする"):
                                success, message, extracted_text = process_pdf_to_profile(
                                    pdf_paths[0], 
                                    profile_path, 
                                    use_ai=st.session_state.get('use_ai', True),
                                    progress_bar=progress_bar,
                                    status_text=pdf_process_status
                                )
                            else:
                                # 複数PDFの一括処理または追記モード
                                combined_text = ""
                                
                                # 既存ファイルの読み込み（追記モードの場合）
                                if file_option == "追記する" and os.path.exists(profile_path):
                                    with open(profile_path, "r", encoding="utf-8") as f:
                                        combined_text = f.read() + "\n\n=== 新規追加情報 ===\n\n"
                                
                                # 各PDFからテキスト抽出して結合
                                for i, pdf_path in enumerate(pdf_paths):
                                    extracted = extract_text_from_pdf(pdf_path)
                                    if extracted:
                                        combined_text += f"\n\n=== {os.path.basename(pdf_path)} ===\n\n{extracted}"
                                    progress_bar.progress((i+1)/len(pdf_paths))
                                
                                # AIで整理
                                if st.session_state.get('use_ai', True) and st.session_state.api_keys.get("GEMINI_API_KEY"):
                                    try:
                                        from langchain_google_genai import ChatGoogleGenerativeAI
                                        from langchain.chains import LLMChain
                                        from langchain.prompts import PromptTemplate
                                        
                                        os.environ["GOOGLE_API_KEY"] = st.session_state.api_keys.get("GEMINI_API_KEY", "")
                                        chat = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.3)
                                        
                                        organize_template = """
                                        以下は複数のPDFドキュメントから抽出したユーザー情報の生テキストです:
                                        {text}

                                        上記テキストから、ユーザーの興味・関心、重要なスキルや希望、その他の関連情報を
                                        整理し、箇条書きで要点のみ抽出してください。
                                        
                                        **研究内容・興味:**
                                        **過去の公募・助成金獲得情報:**
                                        **研究実績:**
                                        **研究拠点:**
                                        **その他関連情報:**
                                        """
                                        
                                        organize_prompt = PromptTemplate(template=organize_template, input_variables=["text"])
                                        organize_chain = LLMChain(llm=chat, prompt=organize_prompt)
                                        
                                        result = organize_chain.invoke({"text": combined_text})
                                        organized_text = result.get("text", "")
                                        
                                        with open(profile_path, "w", encoding="utf-8") as f:
                                            f.write(organized_text)
                                        
                                        success, message, extracted_text = True, f"{len(pdf_paths)}個のPDFを処理しました", organized_text
                                    except Exception as e:
                                        success, message, extracted_text = False, f"エラー: {str(e)}", combined_text
                                else:
                                    with open(profile_path, "w", encoding="utf-8") as f:
                                        f.write(combined_text)
                                    success, message, extracted_text = True, f"{len(pdf_paths)}個のPDFを処理しました", combined_text
                        
                        # 処理結果の表示
                        if success:
                            st.session_state.profile_path = profile_path
                            pdf_process_status.success("処理完了")
                            st.success(message)
                            
                            # 抽出テキストの表示
                            with st.expander("統合されたプロファイル情報"):
                                st.text_area(
                                    "プロファイル内容", 
                                    value=extracted_text[:2000] + ("..." if len(extracted_text) > 2000 else ""), 
                                    height=200, 
                                    disabled=True
                                )
                        else:
                            pdf_process_status.error("処理失敗")
                            st.error(message)
        
        else:  # テキスト入力オプション
            # プロファイルパス定義
            profile_path = os.path.join(
                st.session_state.direct_paths["knowledge_dir"],
                "user_preference.txt"
            )
            
            # プロファイルが既存かチェック
            profile_exists = os.path.exists(profile_path)
            existing_text = ""
            
            if profile_exists:
                try:
                    with open(profile_path, "r", encoding="utf-8") as f:
                        existing_text = f.read()
                    st.info("既存のプロファイルを編集できます")
                except Exception as e:
                    st.warning(f"既存プロファイルの読み込みエラー: {str(e)}")
            
            # テキスト入力
            profile_text = st.text_area(
                "研究者プロファイル情報を入力:",
                height=300,
                value=existing_text if profile_exists else "名前: 山田太郎\n研究分野: 人工知能, 機械学習\n所属: 東京大学\n役職: 助教授\n研究キーワード: 深層学習, 自然言語処理\n国籍: 日本\n学歴: 博士（工学）"
            )
            
            # 既存ファイルの保存オプション
            if profile_exists:
                save_option = st.radio(
                    "保存オプション:",
                    ["上書き保存", "新規ファイルとして保存"]
                )
            else:
                save_option = "上書き保存"
            
            # 保存ボタン
            if st.button("プロファイルを保存"):
                try:
                    # 保存オプション処理
                    if save_option == "新規ファイルとして保存":
                        timestamp = int(time.time())
                        profile_path = os.path.join(
                            st.session_state.direct_paths["knowledge_dir"],
                            f"user_preference_{timestamp}.txt"
                        )
                    
                    # ディレクトリチェック
                    dir_path = os.path.dirname(profile_path)
                    if not os.path.exists(dir_path):
                        try:
                            parent_dir = os.path.dirname(dir_path)
                            if not os.path.exists(parent_dir):
                                try:
                                    os.mkdir(parent_dir)
                                except:
                                    pass
                            os.mkdir(dir_path)
                        except:
                            pass
                    
                    # テキストを保存
                    try:
                        with open(profile_path, "w", encoding="utf-8") as f:
                            f.write(profile_text)
                        
                        st.session_state.profile_path = profile_path
                        st.success(f"プロファイルを保存しました: {os.path.basename(profile_path)}")
                    except Exception as file_error:
                        st.error(f"ファイル書き込みエラー: {str(file_error)}")
                
                except Exception as e:
                    st.error(f"プロファイル保存エラー: {str(e)}")
        
        # 検索設定
        st.subheader("検索設定")
        
        # 助成金数設定 - 説明を詳細にして分かりやすく
        grants_count = st.number_input(
            "検索する助成金数", 
            min_value=1, 
            max_value=10, 
            value=3,
            help="詳細調査を行う助成金の数を指定します。多く設定すると検索時間が長くなります。"
        )

        # 詳細な説明を追加
        st.caption("""
        この数値は、検索結果から詳細に調査する助成金の数を指定します。
        システムは最初に多数の助成金候補を収集した後、ここで指定した数だけ詳細調査を行います。
        詳細調査には時間がかかるため、必要に応じて調整してください。
        """)
        
        # 実行ボタン
        run_button_disabled = 'profile_path' not in st.session_state or st.session_state.profile_path is None
        
        if run_button_disabled:
            st.warning("検索を実行する前にプロファイルを設定してください")
        
        # 実行ボタンクリック時の処理
        if st.button("助成金検索を実行", type="primary", disabled=run_button_disabled):
            # ログ状態リセット
            st.session_state.log_text = "実行ログ:\n"
            st.session_state.clear_logs = True
            
            with st.spinner("助成金検索を実行中..."):
                # 出力パス準備
                output_path = os.path.join(
                    st.session_state.direct_paths["result_dir"],
                    "grants_result.json"
                )
                
                # Python実行関数の呼び出し
                success, log = run_python_script_fallback(
                    st.session_state.direct_paths,
                    st.session_state.profile_path,
                    output_path,
                    grants_count=grants_count,
                    result_column=col2
                )
                
                # 結果をセッション状態に保存
                st.session_state.run_completed = True
                st.session_state.run_results = {
                    "success": success,
                    "log": log,
                    "output_path": output_path
                }
    
    with col2:
        st.subheader("処理状況と検索結果")
        
        # 結果表示
        if st.session_state.get("run_completed", False):
            results = st.session_state.run_results
            
            if results["success"]:
                # タブを作成
                result_tabs = st.tabs(["検索結果", "実行ログ"])
                
                # 検索結果タブ
                with result_tabs[0]:
                    # 助成金CSVファイルパス
                    grants_csv_path = os.path.join(st.session_state.direct_paths["project_root"], "result_grants", "grants_data", "grants_candidates.csv")
                    final_grants_csv_path = os.path.join(st.session_state.direct_paths["project_root"], "result_grants", "grants_data", "final_grants.csv")
                    
                    # タブの構成を変更 - 候補と最終結果の2つのCSVタブを追加
                    csv_tabs = st.tabs(["助成金候補一覧", "詳細表示"])

                    # 助成金候補一覧タブ
                    with csv_tabs[0]:
                        if os.path.exists(grants_csv_path):
                            try:
                                # CSVファイルの読み込み
                                grants_df = pd.read_csv(grants_csv_path)
                                
                                # 調査済み助成金IDのリスト
                                investigated_grants = []
                                if 'run_results' in st.session_state and 'investigated_grants' in st.session_state.run_results:
                                    investigated_grants = st.session_state.run_results.get('investigated_grants', [])
                                
                                # データフレームの処理
                                if len(grants_df) > 0:
                                    st.markdown("### 助成金候補一覧")
                                    st.info(f"全 {len(grants_df)} 件の助成金候補が見つかりました")
                                    
                                    # 表示カラムの選択
                                    display_columns = ['id', 'title', 'organization', 'category']
                                    
                                    # 詳細情報のカラムを特定して追加
                                    detail_columns = ['amount', 'eligibility', 'deadline', 'research_fields', 
                                                    'duration', 'relevance_score', 'completeness_score']
                                    for col in detail_columns:
                                        if col in grants_df.columns:
                                            display_columns.append(col)
                                    
                                    # 調査済みフラグ追加
                                    grants_df['詳細調査済み'] = grants_df['id'].apply(
                                        lambda x: '✅' if x in investigated_grants else ''
                                    )
                                    display_columns.append('詳細調査済み')
                                    
                                    # フィルタリングオプション
                                    filter_options = ['すべて表示', '詳細調査済みのみ', '未調査のみ']
                                    filter_choice = st.radio('表示フィルター:', filter_options, horizontal=True)

                                    filtered_df = grants_df
                                    if filter_choice == '詳細調査済みのみ':
                                        if 'investigated' in grants_df.columns:
                                            # CSV内のinvestigated列を使用
                                            # 値がTrue、'True'、または1の場合を考慮
                                            mask = grants_df['investigated'] == True
                                            mask |= grants_df['investigated'] == 'True'
                                            mask |= grants_df['investigated'] == 1
                                            filtered_df = grants_df[mask]
                                        else:
                                            # フォールバック: セッション状態のリストを使用
                                            filtered_df = grants_df[grants_df['id'].isin(investigated_grants)]
                                    elif filter_choice == '未調査のみ':
                                        if 'investigated' in grants_df.columns:
                                            # CSV内のinvestigated列を使用
                                            # 値がTrue、'True'、または1でない場合を考慮
                                            mask = (grants_df['investigated'] != True) 
                                            mask &= (grants_df['investigated'] != 'True')
                                            mask &= (grants_df['investigated'] != 1)
                                            filtered_df = grants_df[mask]
                                        else:
                                            # フォールバック: セッション状態のリストを使用
                                            filtered_df = grants_df[~grants_df['id'].isin(investigated_grants)]
                                    
                                    # データフレームの表示
                                    st.dataframe(
                                        filtered_df[display_columns], 
                                        use_container_width=True,
                                        height=400,
                                        column_config={
                                            'id': '助成金ID',
                                            'title': '助成金名',
                                            'organization': '提供機関',
                                            'category': 'カテゴリ',
                                            'amount': '助成金額',
                                            'eligibility': '応募資格',
                                            'deadline': '締切日',
                                            'research_fields': '研究分野',
                                            'duration': '期間',
                                            'relevance_score': '関連性スコア',
                                            'completeness_score': '完全性スコア',
                                            '詳細調査済み': st.column_config.CheckboxColumn(
                                                '詳細調査済み',
                                                help='詳細情報が調査済みかどうか',
                                                width='small'
                                            )
                                        }
                                    )
                                    
                                    # CSVダウンロードボタン
                                    csv = filtered_df.to_csv(index=False).encode('utf-8')
                                    st.download_button(
                                        "候補リストをCSVでダウンロード",
                                        csv,
                                        "grants_candidates.csv",
                                        "text/csv",
                                        key='download-candidates-csv'
                                    )
                                else:
                                    st.info("助成金候補情報がありません。検索を実行してください。")
                                    
                            except Exception as e:
                                st.error(f"候補CSVファイルの読み込みエラー: {str(e)}")
                                st.code(traceback.format_exc())
                        else:
                            # CSVファイルが見つからない場合
                            st.warning(f"助成金候補CSVファイルが見つかりません: {grants_csv_path}\nログを確認してください。")

                    # 詳細表示タブ
                    with csv_tabs[1]:
                        st.markdown("### 助成金詳細情報")
                        
                        # 両方のCSVをロード
                        grants_df = None
                        if os.path.exists(grants_csv_path):
                            try:
                                grants_df = pd.read_csv(grants_csv_path)
                            except:
                                pass
                        
                        final_df = None
                        if os.path.exists(final_grants_csv_path):
                            try:
                                final_df = pd.read_csv(final_grants_csv_path)
                            except:
                                pass
                        
                        # どちらのデータフレームを使用するか決定
                        if final_df is not None and len(final_df) > 0:
                            display_df = final_df
                            st.success("最終助成金リストから表示しています（調査済み情報）")
                        elif grants_df is not None and len(grants_df) > 0:
                            display_df = grants_df
                            st.info("候補助成金リストから表示しています")
                        else:
                            st.warning("表示可能な助成金情報がありません")
                            display_df = None
                        
                        # 助成金の詳細表示
                        if display_df is not None and len(display_df) > 0:
                            # ID選択用のセレクトボックス
                            selected_id = st.selectbox(
                                '助成金IDを選択:', 
                                options=display_df['id'].tolist(),
                                format_func=lambda x: f"{x} - {display_df[display_df['id']==x]['title'].values[0]}"
                            )
                            
                            if selected_id:
                                selected_grant = display_df[display_df['id'] == selected_id].iloc[0].to_dict()
                                st.subheader(f"助成金詳細: {selected_grant.get('title', '')}")
                                
                                # 2カラムレイアウト
                                detail_col1, detail_col2 = st.columns(2)
                                
                                # 基本情報
                                with detail_col1:
                                    st.markdown("#### 基本情報")
                                    st.markdown(f"**ID:** {selected_grant.get('id', '')}")
                                    st.markdown(f"**助成金名:** {selected_grant.get('title', '')}")
                                    st.markdown(f"**提供機関:** {selected_grant.get('organization', '')}")
                                    st.markdown(f"**カテゴリ:** {selected_grant.get('category', '')}")
                                    
                                    if 'url' in selected_grant and selected_grant['url']:
                                        st.markdown(f"**URL:** [{selected_grant['url']}]({selected_grant['url']})")
                                
                                # 詳細情報
                                with detail_col2:
                                    st.markdown("#### 詳細情報")
                                    if 'amount' in selected_grant and pd.notna(selected_grant['amount']):
                                        st.markdown(f"**助成金額:** {selected_grant.get('amount', '')}")
                                    if 'eligibility' in selected_grant and pd.notna(selected_grant['eligibility']):
                                        st.markdown(f"**応募資格:** {selected_grant.get('eligibility', '')}")
                                    if 'deadline' in selected_grant and pd.notna(selected_grant['deadline']):
                                        st.markdown(f"**締切日:** {selected_grant.get('deadline', '')}")
                                    if 'duration' in selected_grant and pd.notna(selected_grant['duration']):
                                        st.markdown(f"**期間:** {selected_grant.get('duration', '')}")
                                    if 'research_fields' in selected_grant and pd.notna(selected_grant['research_fields']):
                                        st.markdown(f"**研究分野:** {selected_grant.get('research_fields', '')}")
                                
                                # 追加情報
                                if 'description' in selected_grant and pd.notna(selected_grant['description']):
                                    st.markdown("#### 説明")
                                    st.markdown(selected_grant['description'])
                                
                                # 応募プロセス情報
                                if 'application_process' in selected_grant and pd.notna(selected_grant['application_process']):
                                    st.markdown("#### 応募プロセス")
                                    st.markdown(selected_grant['application_process'])
                                
                                # 必要書類
                                if 'required_documents' in selected_grant and pd.notna(selected_grant['required_documents']):
                                    st.markdown("#### 必要書類")
                                    st.markdown(selected_grant['required_documents'])
                                
                                # 特別条件
                                if 'special_conditions' in selected_grant and pd.notna(selected_grant['special_conditions']):
                                    st.markdown("#### 特別条件")
                                    st.markdown(selected_grant['special_conditions'])
                                
                                # 評価情報
                                evaluation_cols = ['relevance_score', 'completeness_score']
                                has_evaluation = any(col in selected_grant and pd.notna(selected_grant[col]) for col in evaluation_cols)
                                
                                if has_evaluation:
                                    st.markdown("#### 評価情報")
                                    if 'relevance_score' in selected_grant and pd.notna(selected_grant['relevance_score']):
                                        st.markdown(f"**関連性スコア:** {selected_grant.get('relevance_score', '')}")
                                    if 'completeness_score' in selected_grant and pd.notna(selected_grant['completeness_score']):
                                        st.markdown(f"**完全性スコア:** {selected_grant.get('completeness_score', '')}")
                                
                                # 問い合わせ先
                                if 'contact' in selected_grant and pd.notna(selected_grant['contact']):
                                    st.markdown("#### 問い合わせ先")
                                    st.markdown(selected_grant['contact'])
                                
                                # 更新情報
                                if 'updated_at' in selected_grant and pd.notna(selected_grant['updated_at']):
                                    st.markdown("#### 更新情報")
                                    st.markdown(f"**最終更新:** {selected_grant.get('updated_at', '')}")
                        else:
                            st.info("助成金を選択するにはまず検索を実行してください。")
                
                # ログ表示タブ
                with result_tabs[1]:
                    # ログ表示を改善
                    if 'log_text' in st.session_state:
                        # ログコントロール
                        log_col1, log_col2 = st.columns([1, 4])
                        with log_col1:
                            if st.button("ログをクリア", key="clear_log_button"):
                                st.session_state.clear_logs = True
                                st.session_state.log_text = "実行ログ:\n"
                                st.rerun()  # 再実行してUIを更新
                        with log_col2:
                            st.download_button(
                                "ログをダウンロード", 
                                st.session_state.log_text,
                                file_name="grant_search_log.txt",
                                mime="text/plain"
                            )
                        
                        # セッション状態のログテキストを直接表示
                        st.code(st.session_state.log_text, language="bash", height=500)
                    else:
                        st.info("実行ログはまだありません。")
            else:
                # 実行失敗時はエラーを表示
                st.error("助成金検索の実行に失敗しました。ログを確認してください。")
                st.code(results.get("log", "ログがありません"))
        else:
            # まだ実行されていない場合
            placeholder = st.empty()
            placeholder.info("助成金検索を開始するには、左側のフォームを入力して「検索を実行」ボタンをクリックしてください。")
    
    # ナビゲーションボタン
    st.button("戻る: 環境設定 ⚙️", on_click=lambda: setattr(st.session_state, 'page', "設定"), use_container_width=True)
    
# メイン関数
def main():
    # Streamlitページ設定
    st.set_page_config(
        page_title="助成金検索エージェント v0.52",
        page_icon="🔍",
        layout="wide"
    )
    
    # 環境変数を設定
    setup_environment()
    
    # セッション状態の初期化
    initialize_session_state()
    
    # サイドバーナビゲーション
    with st.sidebar:
        st.title("助成金検索エージェント v0.52")
        
        st.markdown("---")
        
        # ナビゲーションボタン
        if st.button("📊 エージェントフローチャート", use_container_width=True, 
                   type="primary" if st.session_state.page == "フローチャート" else "secondary"):
            st.session_state.page = "フローチャート"
            st.rerun()
            
        if st.button("⚙️ 環境設定", use_container_width=True,
                   type="primary" if st.session_state.page == "設定" else "secondary"):
            st.session_state.page = "設定"
            st.rerun()
            
        if st.button("🚀 実行と結果表示", use_container_width=True,
                   type="primary" if st.session_state.page == "実行" else "secondary"):
            st.session_state.page = "実行"
            st.rerun()
        
        st.markdown("---")
        
        # ステータス表示
        if 'api_keys' in st.session_state:
            api_keys = st.session_state.api_keys
            
            if api_keys.get("GOOGLE_API_KEY"):
                st.success("✅ Google API設定済み")
            else:
                st.error("❌ Google API未設定")
                
            if api_keys.get("GOOGLE_CSE_ID"):
                st.success("✅ Custom Search Engine設定済み")
            else:
                st.error("❌ Custom Search Engine未設定")
                
            if api_keys.get("GEMINI_API_KEY"):
                st.success("✅ Gemini API設定済み")
            else:
                st.error("❌ Gemini API未設定")
        
        st.markdown("---")
        st.caption("© 2025 LTS")
    
    # 現在のページを表示
    if st.session_state.page == "フローチャート":
        show_improved_flowchart_page()
    elif st.session_state.page == "設定":
        show_settings_page()
    elif st.session_state.page == "実行":
        show_execution_page()

# アプリケーション起動
if __name__ == "__main__":
    main()