"""
agents/definitions.py
---------------------
Google-ADK 用エージェント生成ユーティリティ  
UI で指定したモデル設定（環境変数 MODEL_<AGENT>）が最優先で反映されます。
"""
from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, AsyncGenerator, Optional

import yaml
 # Gemini SDK (optional). Absent when running in Ollama‑only mode.
try:
    from google.genai.types import GenerateContentConfig           # type: ignore
except ImportError:                                                # pragma: no cover
    GenerateContentConfig = None

from google.adk.models.lite_llm import LiteLlm
# USE_OLLAMA=1 にするとローカル Ollama モード
USE_OLLAMA = os.getenv("USE_OLLAMA", "0") == "1"
from google.adk.agents import LlmAgent, Agent as _AgentAlias, BaseAgent, SequentialAgent, LoopAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

# ---------------------------------------------------------------------------
# 設定ファイル読み込み
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
AGENTS_CFG = CONFIG_DIR / "agents_config.yaml"
TASKS_CFG  = CONFIG_DIR / "tasks_config.yaml"

logger = logging.getLogger(__name__)

def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        logger.warning("Config not found: %s", path)
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

AGENTS_CONF = _load_yaml(AGENTS_CFG)
TASKS_CONF  = _load_yaml(TASKS_CFG)

def _task_desc(key: str) -> str:
    return TASKS_CONF.get(f"{key}_task", {}).get("description", "")

# ---------------------------------------------------------------------------
# tools import
# ---------------------------------------------------------------------------
from tools.common_tools import analyze_profile_tool, custom_google_search_tool, generate_hypotheses_tool
from tools.web_tools    import web_scraper_tool, adk_extract_links_tool
from tools.pdf_tools    import pdf_downloader_tool, pdf_reader_tool
from tools.csv_tools    import csv_reader_tool, csv_writer_tool, csv_updater_tool

# ---------------------------------------------------------------------------
# モデル名解決ヘルパー
# ---------------------------------------------------------------------------
_SUFFIXES = {s.lower() for s in ["Initial", "Investigate", "Loop", "Agent"]}
def _base(agent_name: str) -> str:
   """
   * search_expert_Initial  → search_expert
   * search_expert          → search_expert
   * profile_analyzer       → profile_analyzer
   """
   parts = agent_name.split("_")
   # 末尾から複数のサフィックス(Initial, Investigate, Loop, Agent) をすべて取り除く
   while len(parts) > 1 and parts[-1].lower() in _SUFFIXES:
       parts = parts[:-1]
   return "_".join(parts)

# Gemini to Ollama model mapping
_GEMINI_TO_OLLAMA: Dict[str, str] = {
    "gemini-2.0-flash": "llama3.2:latest",
    "gemini-2.0-flash-thinking-exp-01-21": "llama3.2:latest",
    "gemini-2.5-flash-preview-04-17": "llama3.2:latest",
    "gemini-2.5-pro-exp-03-25": "llama3.2:latest",
    "gemini-2.5-pro-preview-03-25": "llama3.2:latest",
}

def _map_gemini_to_ollama(key: str) -> str:
    return _GEMINI_TO_OLLAMA.get(key, "llama3.2:latest")

def _resolve_model(agent_name: str, default: str) -> str:
    """
    優先度:  
    1. 環境変数  MODEL_<BASE_NAME>  
       例) search_expert → MODEL_SEARCH_EXPERT  
    2. デフォルト値
    """
    base = _base(agent_name).upper()
    if USE_OLLAMA:
        env_key = f"OLLAMA_MODEL_{base}"
        model_str = os.getenv(env_key, _map_gemini_to_ollama(default))
        # provider 接頭辞が無ければ補完
        if not model_str.startswith("ollama"):
            model_str = f"ollama_chat/{model_str}"
        logger.info("ENV %s=%s", env_key, os.getenv(env_key))
        return LiteLlm(model=model_str)

    env_key = f"MODEL_{base}"
    logger.info("ENV %s=%s", env_key, os.getenv(env_key))
    return os.getenv(env_key, default)

# ---------------------------------------------------------------------------
# Quality-Checker 補助クラス
# ---------------------------------------------------------------------------
class CheckStatusAndEscalate_init(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        status = ctx.session.state.get("quality_status_init", "再度csvに書き込んでください")
        yield Event(author=self.name,
                    actions=EventActions(escalate=(status == "csv作成完了")))
        
class CheckStatusAndEscalate(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        status = ctx.session.state.get("quality_status", "continue")
        yield Event(author=self.name,
                    actions=EventActions(escalate=(status == "finish")))
# ---------------------------------------------------------------------------
# Agent / LlmAgent 生成ヘルパー
# USE_OLLAMA=1 の場合は Agent クラス（=LlmAgent エイリアス）を使用する
# ---------------------------------------------------------------------------

# USE_OLLAMA に応じた Agent クラスの切り替え
_AGENT_CLASS = _AgentAlias if USE_OLLAMA else LlmAgent

def _llm(name: str,
         default_model: str,
         goal_key: str,
         task_key: str,
         *,
         tools: List = (),
         output_key: str | None = None,
         temp: float = 0.3):
    cfg  = AGENTS_CONF.get(goal_key, {})         
    goal = cfg.get("goal", "")
    inst = f"goal: {goal}\n\n{_task_desc(task_key)}"

    gen_cfg = None
    if not USE_OLLAMA and GenerateContentConfig is not None:
        gen_cfg = GenerateContentConfig(temperature=temp)

    return _AGENT_CLASS(
        name=name,
        model=_resolve_model(name, default_model),
        description=cfg.get("backstory", ""),
        instruction=inst,
        generate_content_config=gen_cfg,
        tools=list(tools),
        output_key=output_key,
    )

# ---------------------------------------------------------------------------
# build_agents: UI 反映済みのエージェント一式を返す
# ---------------------------------------------------------------------------
def build_agents() -> Dict[str, Any]:
    profile_analyzer         = _llm("profile_analyzer_agent", "gemini-2.0-flash",
                                    "profile_analyzer", "profile_analyzer",
                                    tools=[analyze_profile_tool])

    hypotheses_generator     = _llm("hypotheses_generator_agent", "gemini-2.0-flash",
                                    "hypotheses_generator", "hypotheses_generator",
                                    tools=[generate_hypotheses_tool], temp=0.6)

    query_generator          = _llm("query_generator_agent",
                                    "gemini-2.0-flash-thinking-exp-01-21",
                                    "query_generator", "query_generator",
                                    temp=0.6)

    search_expert_init    = _llm("search_expert_initial_agent", "gemini-2.0-flash",
                                    "search_expert", "generate_initial_grants_list",
                                    tools=[custom_google_search_tool, csv_writer_tool],
                                    output_key="initial_list_generation_result")
    
    list_checker = _AGENT_CLASS(
        name="list_checker_agent",
        model=_resolve_model("list_checker_agent", "gemini-2.0-flash"),
        instruction="['initial_list_generation_result']を確認し '再度csvに書き込んでください' か 'csv作成完了' だけ返答してください。",
        generate_content_config=None if USE_OLLAMA else GenerateContentConfig(temperature=0.3),
        output_key="quality_status_init"
    )

    search_expert_invest   = _llm("search_expert_investigate_agent", "gemini-2.0-flash",
                                    "search_expert", "investigate_grant",
                                    tools=[custom_google_search_tool, web_scraper_tool,
                                           adk_extract_links_tool, pdf_downloader_tool,
                                           pdf_reader_tool, csv_reader_tool],
                                    output_key="last_investigation_json_str")

    investigation_eval  = _llm("investigation_evaluator_agent", "gemini-2.0-flash",
                                    "investigation_evaluator", "investigation_evaluator",
                                    output_key="last_evaluation_result")

    quality_checker = _AGENT_CLASS(
        name="quality_checker_agent",
        model=_resolve_model("quality_checker_agent", "gemini-2.0-flash"),
        instruction="['last_evaluation_result']を確認し 'finish' か 'continue' だけ返答してください。",
        generate_content_config=None if USE_OLLAMA else GenerateContentConfig(temperature=0.3),
        output_key="quality_status"
    )

    report_generator         = _llm("report_generator_agent", "gemini-2.0-flash",
                                    "report_generator", "report_generator",
                                    tools=[csv_reader_tool, csv_updater_tool],
                                    output_key="last_report_generator_output", temp=0.6)

    user_proxy               = _llm("user_proxy_agent", "gemini-2.0-flash",
                                    "user_proxy", "select_grant_to_investigate",
                                    tools=[analyze_profile_tool, csv_reader_tool],
                                    output_key="current_grant_id_selected_raw", temp=0.6)

    # --- workflow agents ---
    initial_loop = LoopAgent(name="InitialInvestigationLoop",
        sub_agents=[search_expert_init, list_checker, 
                    CheckStatusAndEscalate_init(name="stop_checker_init_agent")],
        max_iterations=10)

    initial_phase = SequentialAgent(name="InitialGathering",
        sub_agents=[profile_analyzer, hypotheses_generator,
                    query_generator,  initial_loop])

    detailed_loop = LoopAgent(name="DetailedInvestigationLoop",
        sub_agents=[search_expert_invest, investigation_eval,
                    quality_checker, CheckStatusAndEscalate(name="stop_checker_agent")],
        max_iterations=10)

    second_phase  = SequentialAgent(name="SecondPhase",
        sub_agents=[user_proxy, detailed_loop, report_generator])

    return {
        # 単体
        "profile_analyzer": profile_analyzer,
        "hypotheses_generator": hypotheses_generator,
        "query_generator": query_generator,
        "search_expert_initial": search_expert_init,
        "search_expert_investigation": search_expert_invest,
        "investigation_evaluator": investigation_eval,
        "quality_checker": quality_checker,
        "report_generator": report_generator,
        "user_proxy": user_proxy,
        "stop_checker": CheckStatusAndEscalate(name="StopChecker"),
        "stop_checker_init": CheckStatusAndEscalate_init(name="StopChecker_init"),
        # ワークフロー
        "initial_loop_agent": initial_loop,
        "initial_phase_agent": initial_phase,
        "detailed_investigation_loop_agent": detailed_loop,
        "second_phase_agent": second_phase,
    }