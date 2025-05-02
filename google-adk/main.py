# main.py
import os
import yaml
import asyncio
import pandas as pd
from pathlib import Path
from typing import List, Dict, Any
import datetime
import logging
import csv 
# ADK Imports
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

# Agent Imports
from agents import build_agents

# Tool Imports
try:
    from tools.common_tools import profile_reader_tool, custom_google_search_tool, json_saver_tool
    from tools.web_tools import web_scraper_tool, adk_extract_links_tool
    from tools.pdf_tools import pdf_downloader_tool, pdf_reader_tool
    # Import headers list from csv_tools
    from tools.csv_tools import csv_reader_tool, csv_writer_tool, csv_updater_tool, CANDIDATE_CSV_HEADERS
    print("Successfully imported ADK tools and headers (using custom search).")
except ImportError as e:
    print(f"Error importing from tools: {e}. Check 'tools' directory and __init__.py.")
    exit()
except NameError as e:
     print(f"Error importing name (likely CANDIDATE_CSV_HEADERS): {e}. Check tools/csv_tools.py.")
     exit()


# Environment and Logging Setup
from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# Suppress noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("googleapiclient").setLevel(logging.ERROR)
logging.getLogger("google.api_core").setLevel(logging.WARNING)
logging.getLogger("google.auth").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)


# --- Configuration Loading ---
CONFIG_DIR = Path(__file__).parent / "config"
AGENTS_CONFIG_PATH = CONFIG_DIR / "agents_config.yaml"
TASKS_CONFIG_PATH = CONFIG_DIR / "tasks_config.yaml"

def load_yaml_config(path: Path) -> Dict:
    """Loads YAML configuration file safely."""
    if not path.exists():
        logger.warning(f"Config file not found: {path}")
        return {}
    try:
        with open(path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            return config if config else {}
    except Exception as e:
        logger.error(f"Error loading config file ({path}): {e}", exc_info=True)
        return {}

agents_config = load_yaml_config(AGENTS_CONFIG_PATH)
tasks_config = load_yaml_config(TASKS_CONFIG_PATH)
print(f"Loaded agents config: {'Yes' if agents_config else 'No'}")
print(f"Loaded tasks config: {'Yes' if tasks_config else 'No'}")

# --- Helper Functions ---
def get_config_value(config_dict: Dict, key: str, default: Any = "") -> Any:
    keys = key.split('.')
    val = config_dict
    try:
        for k in keys:
            if isinstance(val, dict):
                val = val.get(k)
            else:
                return default
        return val if val is not None else default
    except Exception:
        return default

# ----------------------------------------------------------------------
# Agents are created in agents.definitions
# ----------------------------------------------------------------------


ag = build_agents()
# ワークフロー複合エージェントを取り出して使う
initial_loop_agent                = ag["initial_loop_agent"]
initial_phase_agent                = ag["initial_phase_agent"]
detailed_investigation_loop_agent  = ag["detailed_investigation_loop_agent"]
second_phase_agent                 = ag["second_phase_agent"]



# --- Function to create empty CSV with headers ---
def create_empty_csv_if_not_exists(file_path: Path, headers: List[str]):
    """Creates an empty CSV with specified headers if it doesn't exist."""
    if not file_path.is_file():
        logger.warning(f"CSV file not found at {file_path}, creating empty file with headers.")
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)
            df = pd.DataFrame(columns=headers)
            df.to_csv(file_path, index=False, encoding='utf-8-sig', quoting=csv.QUOTE_MINIMAL)
            logger.info(f"Created empty CSV: {file_path}")
        except Exception as e:
            logger.error(f"Failed to create empty CSV file at {file_path}: {e}")

# --- Define FINAL_CSV_HEADERS based on CANDIDATE_CSV_HEADERS ---
FINAL_CSV_HEADERS = CANDIDATE_CSV_HEADERS


async def main(user_profile_path: str, output_dir: str, grants_to_process: int = 1, min_candidates: int = 20, append_mode: bool = False):
    """
    メイン実行関数
    
    Args:
        user_profile_path: ユーザープロファイルのパス
        output_dir: 出力ディレクトリ
        grants_to_process: 詳細調査する助成金の数
        min_candidates: 最初に収集する助成金候補の最小数
        append_mode: 既存の候補リストに追記するかどうか
    
    Returns:
        実行結果を含む辞書
    """
    logger.info("ADK Funding Search Starting...")
    logger.info(f"Config: Profile='{user_profile_path}', Grants={grants_to_process}, Min Candidates={min_candidates}, Append Mode={append_mode}")
    start_time = datetime.datetime.now()

    # --- Path Setup and Initial File Creation ---
    try:
        script_dir = Path(__file__).parent
        user_profile_path_obj = (script_dir / user_profile_path).resolve() if not Path(user_profile_path).is_absolute() else Path(user_profile_path)
        output_path_obj = (script_dir / output_dir).resolve() if not Path(output_dir).is_absolute() else Path(output_dir)
        user_profile_path = str(user_profile_path_obj)
        output_dir = str(output_path_obj)
        logger.info(f"Resolved Profile Path: {user_profile_path}")
        logger.info(f"Resolved Output Dir: {output_dir}")
        grants_dir = output_path_obj / "grants_data"
        os.makedirs(grants_dir, exist_ok=True)
        grants_list_path = grants_dir / "grants_candidates.csv"
        knowledge_dir = user_profile_path_obj.parent
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Minimum candidates to search: {min_candidates}")
        env_min_candidates = os.environ.get("MIN_CANDIDATES")

        if env_min_candidates and env_min_candidates.isdigit():
            min_candidates = max(min_candidates, int(env_min_candidates))
            logger.info(f"Using minimum candidates from environment: {min_candidates}")

        # 環境変数から追記モードを上書きできるようにする
        env_append_mode = os.environ.get("APPEND_MODE", "").lower()
        if env_append_mode in ["true", "1", "yes"]:
            append_mode = True
            logger.info("Using append mode from environment: True")
        elif env_append_mode in ["false", "0", "no"]:
            append_mode = False
            logger.info("Using append mode from environment: False")

        if not user_profile_path_obj.is_file():
            logger.warning(f"Creating empty profile: {user_profile_path}")
            with open(user_profile_path, 'w', encoding='utf-8') as f:
                f.write("# Empty Profile")
        elif user_profile_path_obj.stat().st_size == 0:
            logger.warning(f"Profile file empty: {user_profile_path}")
        else:
            logger.info(f"Profile file found: {user_profile_path}")

        # 追記モードの場合はCSVファイルがなければ新規作成
        # 新規検索モードの場合は毎回新規作成
        if not append_mode or not grants_list_path.exists():
            create_empty_csv_if_not_exists(grants_list_path, CANDIDATE_CSV_HEADERS)
            logger.info(f"{'New' if not append_mode else 'Empty'} CSV file created: {grants_list_path}")
        else:
            logger.info(f"Using existing CSV file for append mode: {grants_list_path}")

    except Exception as path_error:
         logger.error(f"Error resolving paths/creating files: {path_error}", exc_info=True)
         return { "status": "error", "message": f"Path/File setup error: {path_error}" }

    # --- Initial State ---
    investigated_grants_loaded = []

    # 追記モードの場合は既存の investigated 値を取得
    if append_mode and grants_list_path.exists():
        try:
            # CSVが存在する場合、既に調査済みのIDを読み込む
            df = pd.read_csv(grants_list_path)
            if 'id' in df.columns and 'investigated' in df.columns:
                # 調査済み（investigated=True/1）の助成金IDを抽出
                investigated_ids = df[df['investigated'].astype(str).isin(['True', '1', 'true'])]['id'].tolist()
                investigated_grants_loaded = [str(id) for id in investigated_ids if id]
                logger.info(f"Loaded {len(investigated_grants_loaded)} previously investigated grants from CSV")
        except Exception as e:
            logger.warning(f"Failed to load investigated grants from CSV: {e}")

    initial_state = {
        "config_user_profile_path": user_profile_path, 
        "config_output_dir": output_dir,
        "config_grants_list_path": str(grants_list_path), 
        "investigated_grants": investigated_grants_loaded, 
        "current_date": start_time.strftime("%Y-%m-%d"),
        "user_profile_path": user_profile_path, 
        "grants_list_path": str(grants_list_path),
        "csv_path": str(grants_list_path),
        "min_candidates": min_candidates,
        "append_mode": append_mode,  # 追記モードをセッション状態に追加
    }

    # --- Runner and Session ---
    session_service = InMemorySessionService()
    runner = Runner( agent=initial_phase_agent, app_name="adk_funding_search", session_service=session_service )
    session_id = f"funding_run_{start_time.strftime('%Y%m%d_%H%M%S')}"
    session = session_service.create_session( app_name=runner.app_name, user_id="funding_user_01", session_id=session_id, state=initial_state )
    logger.info(f"Session '{session.id}' created.")
    logger.info(f"Initial state keys: {list(initial_state.keys())}")

    # --- Execute Workflow ---
    trigger_message = Content(role="user", parts=[Part(text=f"Analyze profile: {user_profile_path}")])
    current_state = initial_state.copy()

    async for event in runner.run_async(user_id=session.user_id, session_id=session.id, new_message=trigger_message):
        if event.is_final_response() and event.author == initial_phase_agent.name:
                logger.info("initial workflow finished."); 
                break

    # except Exception as e:
    for i in range(grants_to_process):
        logger.info(f"Processing grant candidate {i+1}/{grants_to_process}...")
        session_service2 = InMemorySessionService()
        runner2 = Runner( agent=second_phase_agent, app_name="adk_funding_search_phase2", session_service=session_service2)
        session_id2 = f"funding_run_{start_time.strftime('%Y%m%d_%H%M%S')}"
        session2 = session_service2.create_session(app_name=runner2.app_name, user_id="funding_user_01", session_id=session_id2, state=initial_state)

        trigger_message = Content(role="user", parts=[Part(text=f"Investigate grant {i+1}...")])
        async for event in runner2.run_async(user_id=session2.user_id, session_id=session2.id, new_message=trigger_message):
            if event.is_final_response() and event.author == second_phase_agent.name:
                    logger.info("second workflow finished."); 
                    break

    # --- Result Aggregation ---
    logger.info("Aggregating results...")
    end_time = datetime.datetime.now(); duration = end_time - start_time
    logger.info(f"Process finished in {duration}")
    
    # 明示的に完了を記録
    logger.info("===== SEARCH COMPLETED SUCCESSFULLY =====")
    return {"status": "success", "duration": str(duration)}


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run grant search")
    parser.add_argument("--profile", dest="user_profile_path", help="Path to user profile file", 
                      default=os.getenv("USER_PROFILE_PATH", "knowledge/user_preference.txt"))
    parser.add_argument("--output", dest="output_dir", help="Output directory", 
                      default=os.getenv("OUTPUT_DIR", "results/"))
    parser.add_argument("--grants", dest="grants_to_process", type=int, help="Number of grants to process", 
                       default=int(os.getenv("GRANTS_COUNT", "1")))
    parser.add_argument("--min-candidates", dest="min_candidates", type=int, help="Minimum number of grant candidates to collect", 
                       default=int(os.getenv("MIN_CANDIDATES", "20")))
    parser.add_argument("--append", dest="append_mode", action="store_true", help="Append to existing results instead of overwriting")
    
    args = parser.parse_args()
    
    # Run main function
    import asyncio
    asyncio.run(main(
        user_profile_path=args.user_profile_path,
        output_dir=args.output_dir,
        grants_to_process=args.grants_to_process,
        min_candidates=args.min_candidates,
        append_mode=args.append_mode
    ))