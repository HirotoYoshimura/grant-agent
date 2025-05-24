"""
Streamlit UI for Grant-Search ADK
"""
from __future__ import annotations

import asyncio
import re
import html
import json
import logging
import os
import queue
import subprocess
import sys
import threading
import time
import csv
import signal
import yaml
from pathlib import Path
from typing import Dict, List, Optional
from tools.csv_tools import CANDIDATE_CSV_HEADERS
from agents.definitions import _get_ollama_models

import pandas as pd
import streamlit as st
import dotenv
from streamlit_autorefresh import st_autorefresh
import streamlit.components.v1 as components

# ---------------------------------------------------------------------------
# Constants & paths
# ---------------------------------------------------------------------------
ROOT = Path.cwd()
KNOWLEDGE_DIR = ROOT / "knowledge"
RESULTS_DIR = ROOT / "results"
GRANTS_DIR = RESULTS_DIR / "grants_data"
csv_path = GRANTS_DIR / "grants_candidates.csv"
LOGS_DIR = ROOT / "logs"
DEFAULT_PROFILE = KNOWLEDGE_DIR / "user_preference.txt"
BACKEND = ROOT / "main.py"
ENV_STORE = ROOT / ".env"
MODEL_CFG_FILE = ROOT / "agents/models.yaml"

with MODEL_CFG_FILE.open(encoding="utf-8") as f:
    _model_cfg = yaml.safe_load(f)

MODEL_CANDIDATES: list[str] = _model_cfg["candidates"]
MODEL_INFO: dict[str, str] = _model_cfg["info"]

# Ollamaモデルの動的読み込み
ollama_models = _get_ollama_models()
if ollama_models:
    MODEL_CANDIDATES.extend(ollama_models)
    for model_name in ollama_models:
        if model_name not in MODEL_INFO:
            MODEL_INFO[model_name] = "ローカル Ollama モデル"

for p in [KNOWLEDGE_DIR, RESULTS_DIR, GRANTS_DIR, LOGS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Logging & env
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def load_env_dict() -> dict[str, str]:
    """KEY=VALUE 形式の .env を dict に読み込む（無いなら空 dict）"""
    if ENV_STORE.exists():
        return {k: v for k, v in dotenv.dotenv_values(str(ENV_STORE)).items() if v}
    return {}

def save_env_dict(cfg: dict[str, str]) -> None:
    """dict を .env に保存し、同時に os.environ へ反映"""
    with ENV_STORE.open("w", encoding="utf-8") as f:
        for k, v in cfg.items():
            if v:                          # 空文字は書かない
                f.write(f"{k}={v}\n")
    os.environ.update({k: v for k, v in cfg.items() if v})
# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------

def _load_env() -> Dict[str, str]:
    if ENV_STORE.exists():
        try:
            return json.loads(ENV_STORE.read_text())
        except Exception:
            pass
    return {}

def _save_env(data: Dict[str, str]):
    ENV_STORE.write_text(json.dumps(data, ensure_ascii=False, indent=2))

# ---------------------------------------------------------------------------
# Mermaid rendering helper (uses Mermaid 10.6.1 via CDN)
# ---------------------------------------------------------------------------

def render_mermaid(code: str, height: int = 600):
    escaped = (
        code.replace("\\", "\\\\")
        .replace("`", "\`")
        .replace("$", "\$")
        .replace("</", "<\/")
    )
    html_code = f"""
    <script src='https://cdn.jsdelivr.net/npm/mermaid@10.6.1/dist/mermaid.min.js'></script>
    <div class='mermaid'>{escaped}</div>
    <script>mermaid.initialize({{startOnLoad:true, securityLevel:'loose', theme:'default'}});</script>
    """
    components.html(html_code, height=height, scrolling=True)

# ---------------------------------------------------------------------------
# LogTailer for backend stdout
# ---------------------------------------------------------------------------
class LogTailer(threading.Thread):
    def __init__(self, cmd: List[str], logfile: Path):
        super().__init__(daemon=True)
        self.cmd = cmd
        self.logfile = logfile
        self.queue: "queue.Queue[str]" = queue.Queue()
        self.proc: Optional[subprocess.Popen[str]] = None

    def run(self):
        self.proc = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=os.environ.copy(),
        )
        assert self.proc.stdout is not None
        with self.logfile.open("w", encoding="utf-8") as f:
            for line in self.proc.stdout:
                line = line.rstrip("\n")
                self.queue.put(line)
                f.write(line + "\n")
        self.proc.wait()
        self.queue.put(f"===== BACKEND FINISHED (exit {self.proc.returncode}) =====")

    def poll(self) -> List[str]:
        lines: List[str] = []
        while not self.queue.empty():
            lines.append(self.queue.get())
        return lines

# ----------------------------------------------------------------------------
# profile regestration
# ----------------------------------------------------------------------------

def page_profile() -> None:
    """ユーザープロファイルの編集＋PDF アップロード"""
    st.markdown("## 📝 ユーザープロファイル")

    # ── テキストファイルの読み書き ──
    profile_path = DEFAULT_PROFILE
    profile_path.parent.mkdir(parents=True, exist_ok=True)

    default_text = profile_path.read_text(encoding="utf-8") if profile_path.exists() else ""
    txt = st.text_area(
        "研究内容・経歴・キーワードなどを自由に入力してください",
        value=default_text,
        height=350,
        placeholder="例）\n- 研究対象: ○○菌\n- 研究分野: 応用微生物学 / 発酵工学\n- 希望助成金: 若手・挑戦的… 等",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 保存 / 更新", use_container_width=True):
            profile_path.write_text(txt, encoding="utf-8")
            st.success("プロファイルを保存しました")
    with col2:
        if st.button("↩️ 変更を破棄して再読込", use_container_width=True):
            st.experimental_rerun()

    st.markdown("---")

    # ── PDF アップローダ ──
    st.markdown("### 📄 研究計画書・業績リスト等の PDF をアップロード")
    pdfs = st.file_uploader("PDF を選択（複数可）", type="pdf", accept_multiple_files=True)

    if pdfs:
        for up in pdfs:
            save_to = KNOWLEDGE_DIR / up.name
            save_to.write_bytes(up.getbuffer())
        st.success(f"{len(pdfs)} 件の PDF を保存しました")

        if st.button("PDF からプロファイルを自動生成", use_container_width=True):
            try:
                import importlib, sys
                cup = importlib.reload(sys.modules["create_user_preference"]) \
                    if "create_user_preference" in sys.modules \
                    else importlib.import_module("create_user_preference")

                cup.create_user_preference_file(str(KNOWLEDGE_DIR), str(profile_path))
                st.success("user_preference.txt を更新しました。ページを再読み込みしてください。")

            except RuntimeError as e:
                st.error(f"❌ {e}\n\n左メニュー『API設定』で GOOGLE_API_KEY を入力してから再実行してください。")


# ---------------------------------------------------------------------------
# CSS & log window helper
# ---------------------------------------------------------------------------
_PAGE_STYLE = """
<style>
.log-window {height:400px;overflow-y:auto;background:#111;padding:8px;border-radius:4px;}
.log-text   {margin:0;white-space:pre-wrap;font-family:monospace;font-size:12px;color:#eee;line-height:1.4;}
</style>
"""

def show_log():
    escaped = html.escape(st.session_state.log_text)
    components.html(_PAGE_STYLE + f'<div class="log-window"><pre class="log-text">{escaped}</pre></div>', height=420, scrolling=False)

# ---------------------------------------------------------------------------
# Initial session state
# ---------------------------------------------------------------------------
if "init" not in st.session_state:
    st.session_state.init = True
    st.session_state.env_cfg = load_env_dict()
    API_KEYS = ["GOOGLE_API_KEY"]
    for _k in API_KEYS:
        if not st.session_state.env_cfg.get(_k):
            st.session_state.env_cfg[_k] = os.environ.get(_k, "")
    st.session_state.agent_models = {
        "profile_analyzer": "gemini-2.0-flash",
        "hypotheses_generator": "gemini-2.0-flash",
        "query_generator": "gemini-2.0-flash-thinking-exp-01-21",
        "search_expert": "gemini-2.0-flash-lite",
        "report_generator": "gemini-2.0-flash",
        "user_proxy": "gemini-2.0-flash-thinking-exp-01-21",
        "investigation_evaluator": "gemini-2.0-flash",
    }
    st.session_state.page = "workflow"
    st.session_state.job: Optional[LogTailer] = None
    st.session_state.log_text = "実行ログ:\n"
    st.session_state.log_file: Optional[Path] = None
    st.session_state.total_grants = 0
    st.session_state.current_progress = 0

# ---------------------------------------------------------------------------
# Streamlit layout & navigation
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Grant Search UI", layout="wide")

with st.sidebar:
    st.title("Grant Search ADK")
    if st.button("ワークフロー図", use_container_width=True):
        st.session_state.page = "workflow"
    if st.button("API設定", use_container_width=True):
        st.session_state.page = "api"
    if st.button("LLMモデル設定", use_container_width=True):
        st.session_state.page = "models"
    if st.button("ユーザープロファイル", use_container_width=True):
        st.session_state.page = "profile" 
    if st.button("助成金検索実行", use_container_width=True):
        st.session_state.page = "search"
    if st.button("結果確認", use_container_width=True):
        st.session_state.page = "results"
    if st.button("アプリを終了", use_container_width=True, type="primary"):
        st.info("アプリを終了します。ブラウザを閉じてください。")
        time.sleep(1)
        os.kill(os.getpid(), signal.SIGTERM)

# ---------------------------------------------------------------------------
# Workflow page
# ---------------------------------------------------------------------------
MERMAID_CODE = """
  graph TD
    subgraph Phase1[フェーズ1: 初期収集]
      A[プロファイル分析] --> B[仮説生成]
      B --> C[クエリ生成]
      C --> D[候補リスト生成]
    end
    subgraph Phase2[フェーズ2: 詳細調査]
      E[ユーザー代理選択] --> F[助成金詳細調査]
      F --> G[調査評価]
      G --> H{完了?}
      H -->|No| F
      H -->|Yes| I[レポート生成]
    end
    Phase1 --> Phase2
"""

if st.session_state.page == "workflow":
    st.markdown("## ワークフロー図")
    try:
        render_mermaid(MERMAID_CODE)
    except Exception as e:
        st.error(f"Mermaid 描画に失敗: {e}")
        st.markdown(f"```mermaid{MERMAID_CODE}```")

    st.markdown("---")
    st.markdown("### エージェントの役割")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown(
            """
* **🤓 プロファイル分析者**  
  研究者プロファイルから研究興味・キーワード・キャリア段階などを抽出

* **🧠 仮説生成者**  
  プロファイルを基に関連助成金カテゴリの仮説を立案

* **🔍 クエリ生成者**  
  カテゴリとプロファイル情報を検索クエリに変換
"""
        )

    with col2:
        st.markdown(
            """
* **🌐 検索専門家**  
  Web/PDF をクロールし助成金情報を収集

* **👤 ユーザー代理**  
  研究者視点で最適な助成金を選定

* **🔎 調査評価者**  
  情報の欠落をチェックし追加調査を指示

* **📊 レポート生成者**  
  完全な助成金レコードを CSV に反映
"""
        )

elif st.session_state.page == "api":
    st.markdown("## APIキー設定")
    cfg = st.session_state.env_cfg
    
    # 必要なAPI設定に関する説明を追加
    st.markdown("""
    #### APIキー：
    - **GOOGLE_API_KEY**: Gemini APIキー（LLMモデルを使用するために必要）
    """)
    
    with st.form("api_form"):
        # GeminiのAPIキーを必須として強調
        cfg["GOOGLE_API_KEY"] = st.text_input("GOOGLE_API_KEY（必須）", cfg.get("GOOGLE_API_KEY", ""), type="password")
        
        if st.form_submit_button("保存"):
            save_env_dict(cfg)
            st.session_state.env_cfg = cfg
            st.success(".env を保存しました")

# ---------------------------------------------------------------------------
# Model settings page
# ---------------------------------------------------------------------------
elif st.session_state.page == "models":
    st.markdown("## LLMモデル設定")
    am = st.session_state.agent_models

    # モデルタイプ選択
    model_type = st.radio(
        "モデルタイプを選択",
        ("Gemini API", "Ollama Local"),
        key="model_type_selection"
    )
    st.markdown("---")

    if model_type == "Ollama Local":
        st.info(
            """
            Ollamaモデルを選択すると、以下の環境変数が自動的に設定されます。
            - `OPENAI_API_BASE=http://localhost:11434/v1`
            - `OPENAI_API_KEY=anything`
            Ollamaサーバーがローカルで実行されていることを確認してください。
            """
        )
        # 自動設定されるため、入力フィールドは削除
        # st.text_input("OPENAI_API_BASE (現在の設定)", value=os.getenv("OPENAI_API_BASE", "未設定"), disabled=True)
        # st.text_input("OPENAI_API_KEY (現在の設定)", value=os.getenv("OPENAI_API_KEY", "未設定"), disabled=True)

    # 表示するモデル候補をフィルタリング
    if model_type == "Gemini API":
        current_model_candidates = [m for m in MODEL_CANDIDATES if not m.startswith("ollama/")]
    else: # Ollama Local
        current_model_candidates = [m for m in MODEL_CANDIDATES if m.startswith("ollama/")]
        if not current_model_candidates:
            st.warning("利用可能なOllamaモデルが見つかりません。Ollamaサーバーが起動しているか、モデルがインストールされているか確認してください。")


    for agent_name in am:
        st.markdown(f"#### {agent_name}")
        
        # 現在選択されているモデルがフィルタリング後の候補に存在するか確認
        current_agent_model = am.get(agent_name)
        if current_agent_model not in current_model_candidates:
            # 存在しない場合は、候補リストの先頭のモデルを選択する（もしくはNoneなど）
            # ここでは、エラーを防ぐために、利用可能な候補がない場合は選択肢を空にする
            selected_model_index = 0
            if not current_model_candidates:
                 # 利用可能なモデルがない場合、selectboxを無効化またはメッセージ表示
                 st.warning(f"{model_type} で利用可能なモデルがありません。")
                 # am[agent_name] = None # またはデフォルトのGeminiモデルに戻すなど
                 # continue
            elif current_model_candidates : # current_model_candidatesが空でないことを確認
                 am[agent_name] = current_model_candidates[0] # リストの最初のモデルをデフォルトに
            else: # 候補がない場合
                 # 適切なデフォルト値や処理を設定
                 # 例えば、Geminiのデフォルトモデルにフォールバックするなど
                 # この例では何もしない（UI上でエラーになる可能性あり）
                 pass


        # selectboxのindexを安全に取得
        try:
            model_index = current_model_candidates.index(am[agent_name]) if am.get(agent_name) in current_model_candidates else 0
        except ValueError:
            model_index = 0 # current_model_candidates が空の場合や、am[agent_name] が存在しない場合に発生しうる

        if not current_model_candidates:
            st.selectbox(
                "モデルを選択",
                [],
                key=f"{agent_name}_sel",
                disabled=True
            )
        else:
            sel = st.selectbox(
                "モデルを選択",
                current_model_candidates,
                index=model_index,
                key=f"{agent_name}_sel",
                format_func=lambda m: f"{m}: {MODEL_INFO.get(m, MODEL_INFO.get('ollama', ''))}" # Ollamaモデル用の汎用情報
            )
            am[agent_name] = sel
        st.markdown("---")

    if st.button("保存"):
        st.success("更新しました")
            
# ---------------------------------------------------------------------------
# profile stteings page
# ---------------------------------------------------------------------------
elif st.session_state.page == "profile":
    page_profile()    

# ---------------------------------------------------------------------------
# Search execution page
# ---------------------------------------------------------------------------
elif st.session_state.page == "search":
    st.markdown("## 助成金検索を実行")

    grants_cnt = st.number_input("詳細調査する助成金数", 1, 10, 1)
    min_cand = st.number_input("候補助成金の最低件数", 5, 100, 10)
    append_mode = st.radio("検索モード", ("新規検索", "既存結果に追記")) == "既存結果に追記"
    progress_ph = st.empty()

    def _launch():
        ts = time.strftime("%Y%m%d_%H%M%S")
        log_file = LOGS_DIR / f"run_{ts}.log"
        cmd = [
            sys.executable, str(BACKEND),
            "--profile", str(DEFAULT_PROFILE),
            "--output", str(RESULTS_DIR),
            "--grants", str(grants_cnt),
            "--min-candidates", str(min_cand),
        ]
        if not append_mode:
            # 既存ファイルをリセット
            if csv_path.exists():
                csv_path.unlink()

            # 空の DataFrame でヘッダーだけ作成
            pd.DataFrame(columns=CANDIDATE_CSV_HEADERS).to_csv(
                csv_path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL
            )

        # env overrides
        os.environ.update({k: v for k, v in st.session_state.env_cfg.items() if v})
        for ag, model in st.session_state.agent_models.items():
            os.environ[f"MODEL_{ag.upper()}"] = model
        os.environ["APPEND_MODE"] = "true"
        os.environ["MIN_CANDIDATES"] = str(min_cand)
        st.session_state.job = LogTailer(cmd, log_file)
        st.session_state.job.start()
        st.session_state.log_file = log_file
        st.session_state.log_text = "実行ログ:\ncmd: " + " ".join(cmd) + "\n\n"
        st.session_state.total_grants = int(grants_cnt)
        st.session_state.current_progress = 0
        progress_ph.progress(0.0, text="0/"+str(grants_cnt))

    if st.button("検索開始", disabled=st.session_state.job is not None):
        _launch()

    if st.session_state.job is None:
        st.info("検索を開始するとログが表示され進捗バーが動きます。")
    else:
        new_lines = st.session_state.job.poll()
        if new_lines:
            st.session_state.log_text += "\n".join(new_lines)+"\n"
            for ln in new_lines:
                m=re.search(r"Processing grant candidate (\d+)/(\d+)", ln)
                if m:
                    st.session_state.current_progress=int(m.group(1))
        # update progress bar
        tot = int(st.session_state.total_grants or 1)
        cur = int(st.session_state.current_progress or 0)
        progress_fraction=min(cur/tot,1.0)
        progress_ph.progress(progress_fraction, text=f"{cur}/{tot}")
        show_log()
        if st.session_state.job.is_alive():
            st_autorefresh(interval=1000, key="_log_rf")
        else:
            progress_ph.progress(1.0, text="完了")
            st.success("検索が完了しました。")
            if st.session_state.log_file:
                st.download_button("ログをダウンロード", st.session_state.log_file.read_bytes(), file_name=st.session_state.log_file.name)


# ---------------------------------------------------------------------------
# Results page
# ---------------------------------------------------------------------------
elif st.session_state.page == "results":
    st.markdown("## 検索結果")
    csv_path = GRANTS_DIR / "grants_candidates.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        tab1, tab2 = st.tabs(["候補", "調査済み"])
        with tab1:
            st.dataframe(df, use_container_width=True, hide_index=True)
        with tab2:
            done = df[df.get("investigated", 0).astype(str).isin(["1", "True", "true"])]
            st.dataframe(done, use_container_width=True, hide_index=True)
        st.download_button("CSVダウンロード", df.to_csv(index=False).encode("utf-8-sig"), file_name="grants_candidates.csv", mime="text/csv")
    else:
        st.warning("まだ結果がありません。検索を実行してください。")