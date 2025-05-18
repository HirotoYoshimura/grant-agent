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
from google.genai.types import GenerateContentConfig
from google.adk.agents import LlmAgent, BaseAgent, SequentialAgent, LoopAgent
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
from tools.common_tools import profile_reader_tool, web_search_tool
from tools.web_tools    import web_scraper_tool, adk_extract_links_tool
from tools.pdf_tools    import pdf_downloader_tool, pdf_reader_tool
from tools.csv_tools    import csv_reader_tool, csv_writer_tool, csv_updater_tool

# ---------------------------------------------------------------------------
# モデル名解決ヘルパー
# ---------------------------------------------------------------------------
_SUFFIXES = {"Initial", "Investigate", "Loop", "Agent"}
def _base(agent_name: str) -> str:
   """
   * search_expert_Initial  → search_expert
   * search_expert          → search_expert
   * profile_analyzer       → profile_analyzer
   """
   parts = agent_name.split("_")
   if len(parts) > 1 and parts[-1] in _SUFFIXES:
       return "_".join(parts[:-1])
   return agent_name

def _resolve_model(agent_name: str, default: str) -> str:
    """
    優先度:  
    1. 環境変数  MODEL_<BASE_NAME>  
       例) search_expert → MODEL_SEARCH_EXPERT  
    2. デフォルト値
    """
    env_key = f"MODEL_{_base(agent_name).upper()}"
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
# LlmAgent 生成ヘルパー
# ---------------------------------------------------------------------------
def _llm(name: str,
         default_model: str,
         goal_key: str,         
         task_key: str,
         *,
         tools: List = (),
         output_key: str | None = None,
         temp: float = 0.3) -> LlmAgent:
    cfg  = AGENTS_CONF.get(goal_key, {})         
    goal = cfg.get("goal", "")
    inst = f"goal: {goal}\n\n{_task_desc(task_key)}"
    return LlmAgent(
        name=name,
        model=_resolve_model(name, default_model),
        description=cfg.get("backstory", ""),
        instruction=inst,
        generate_content_config=GenerateContentConfig(temperature=temp),
        tools=list(tools),
        output_key=output_key,
    )

# ---------------------------------------------------------------------------
# build_agents: UI 反映済みのエージェント一式を返す
# ---------------------------------------------------------------------------
def build_agents() -> Dict[str, Any]:
    profile_analyzer         = _llm("profile_analyzer", "gemini-2.0-flash",
                                    "profile_analyzer", "profile_analyzer",
                                    tools=[profile_reader_tool])

    hypotheses_generator     = _llm("hypotheses_generator", "gemini-2.0-flash",
                                    "hypotheses_generator", "hypotheses_generator",
                                    tools=[profile_reader_tool], temp=0.6)

    query_generator          = _llm("query_generator",
                                    "gemini-2.0-flash-thinking-exp-01-21",
                                    "query_generator", "query_generator",
                                    temp=0.6)

    search_expert_init    = _llm("search_expert_Initial", "gemini-2.0-flash",
                                    "search_expert", "generate_initial_grants_list",
                                    tools=[web_search_tool, csv_writer_tool],
                                    output_key="initial_list_generation_result")
    
    list_checker = LlmAgent(
        name="list_checker",
        model=_resolve_model("list_checker", "gemini-2.0-flash"),
        instruction="['initial_list_generation_result']を確認し '再度csvに書き込んでください' か 'csv作成完了' だけ返答してください。",
        generate_content_config=GenerateContentConfig(temperature=0.3),
        output_key="quality_status_init"
    )

    search_expert_invest   = _llm("search_expert_Investigate", "gemini-2.0-flash",
                                    "search_expert", "investigate_grant",
                                    tools=[web_search_tool, web_scraper_tool,
                                           adk_extract_links_tool, pdf_downloader_tool,
                                           pdf_reader_tool, csv_reader_tool],
                                    output_key="last_investigation_json_str")

    investigation_eval  = _llm("investigation_evaluator", "gemini-2.0-flash",
                                    "investigation_evaluator", "investigation_evaluator",
                                    output_key="last_evaluation_result")

    quality_checker = LlmAgent(
        name="quality_checker",
        model=_resolve_model("quality_checker", "gemini-2.0-flash"),
        instruction="['last_evaluation_result']を確認し 'finish' か 'continue' だけ返答してください。",
        generate_content_config=GenerateContentConfig(temperature=0.3),
        output_key="quality_status"
    )

    report_generator         = _llm("report_generator", "gemini-2.0-flash",
                                    "report_generator", "report_generator",
                                    tools=[csv_reader_tool, csv_updater_tool],
                                    output_key="last_report_generator_output", temp=0.6)

    user_proxy               = _llm("user_proxy", "gemini-2.0-flash",
                                    "user_proxy", "select_grant_to_investigate",
                                    tools=[profile_reader_tool, csv_reader_tool],
                                    output_key="current_grant_id_selected_raw", temp=0.6)

    # --- workflow agents ---
    initial_loop = LoopAgent(name="InitialInvestigationLoop",
        sub_agents=[search_expert_init, list_checker, 
                    CheckStatusAndEscalate_init(name="StopChecker_init")],
        max_iterations=10)

    initial_phase = SequentialAgent(name="InitialGathering",
        sub_agents=[profile_analyzer, hypotheses_generator,
                    query_generator,  initial_loop])

    detailed_loop = LoopAgent(name="DetailedInvestigationLoop",
        sub_agents=[search_expert_invest, investigation_eval,
                    quality_checker, CheckStatusAndEscalate(name="StopChecker")],
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