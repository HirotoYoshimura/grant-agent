"""
agents/definitions.py
---------------------
Google-ADK 用エージェントを一括で生成するヘルパー。

• YAML（agents_config.yaml / tasks_config.yaml）を読み込む  
• tools パッケージを import（失敗時は明示的に例外）  
• build_agents() を呼ぶと、必要なエージェントを dict で返す
"""

from __future__ import annotations
from pathlib import Path
from typing import Dict, Any, List

import yaml
import logging
from google.adk.agents import LlmAgent, BaseAgent, SequentialAgent, LoopAgent
from google.genai.types import GenerateContentConfig

# ---------------------------------------------------------------------------
# 共通設定
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
AGENTS_CFG = CONFIG_DIR / "agents_config.yaml"
TASKS_CFG  = CONFIG_DIR / "tasks_config.yaml"

logger = logging.getLogger(__name__)

def _safe_load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        logger.warning("Config not found: %s", path)
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

AGENTS_CONF = _safe_load_yaml(AGENTS_CFG)
TASKS_CONF  = _safe_load_yaml(TASKS_CFG)

def _cfg(path: str, default: Any = "") -> Any:
    """ドット区切りキーでネスト辞書を安全に取得"""
    cur = AGENTS_CONF if path.split(".")[0] in AGENTS_CONF else TASKS_CONF
    for k in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(k, default)
        else:
            return default
    return cur or default

# ---------------------------------------------------------------------------
# tools インポート
# ---------------------------------------------------------------------------
from tools.common_tools import profile_reader_tool, custom_google_search_tool, json_saver_tool
from tools.web_tools    import web_scraper_tool, adk_extract_links_tool
from tools.pdf_tools    import pdf_downloader_tool, pdf_reader_tool
from tools.csv_tools    import (csv_reader_tool, csv_writer_tool,
                                csv_updater_tool, CANDIDATE_CSV_HEADERS)

# ---------------------------------------------------------------------------
# Quality チェッカー補助クラス
# ---------------------------------------------------------------------------
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from typing import AsyncGenerator

class CheckStatusAndEscalate(BaseAgent):
    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        status = ctx.session.state.get("quality_status", "continue")
        should_stop = (status == "finish")
        yield Event(author=self.name, actions=EventActions(escalate=(status == "finish")))

# ---------------------------------------------------------------------------
# LLM Agent を生成するヘルパー
# ---------------------------------------------------------------------------
def _llm(name: str,
         model: str,
         goal_key: str,
         task_key: str,
         tools: List = (),
         **opt) -> LlmAgent:
    cfg = AGENTS_CONF.get(name, {})
    goal  = cfg.get("goal", "")
    back  = cfg.get("backstory", "")
    task_desc = TASKS_CONF.get(f"{task_key}_task", {}).get("description", "")
    instruction = f"goal: {goal}\n\n{task_desc}"
    return LlmAgent(
        name=name,
        model=model,
        description=back,
        instruction=instruction,
        generate_content_config=GenerateContentConfig(temperature=opt.get("temp", 0.3)),
        tools=list(tools),
        output_key=opt.get("output_key"),
    )

# ---------------------------------------------------------------------------
# build_agents(): すべてのエージェントを作って dict で返す
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

    search_expert_initial    = _llm("search_expert_Initial", "gemini-2.0-flash",
                                    "search_expert", "generate_initial_grants_list",
                                    tools=[custom_google_search_tool, csv_writer_tool])

    search_expert_investig   = _llm("search_expert_Investigate", "gemini-2.0-flash",
                                    "search_expert", "investigate_grant",
                                    tools=[custom_google_search_tool, web_scraper_tool,
                                           adk_extract_links_tool, pdf_downloader_tool,
                                           pdf_reader_tool, csv_reader_tool],
                                    output_key="last_investigation_json_str")

    investigation_evaluator  = _llm("investigation_evaluator", "gemini-2.0-flash",
                                    "investigation_evaluator", "investigation_evaluator",
                                    output_key="last_evaluation_result")

    quality_checker = LlmAgent(
        name="QualityChecker",
        model="gemini-2.0-flash",
        instruction="['last_evaluation_result']を見てinvestigation_evaluatorが、調査状況をどう判断したか出力してください。 'finish' または 'continue'のみ出力してください。",
        generate_content_config=GenerateContentConfig(temperature=0.3),
        output_key="quality_status",
    )

    report_generator         = _llm("report_generator", "gemini-2.0-flash",
                                    "report_generator", "report_generator",
                                    tools=[csv_reader_tool, csv_updater_tool],
                                    output_key="last_report_generator_output", temp=0.6)

    user_proxy               = _llm("user_proxy", "gemini-2.0-flash",
                                    "user_proxy", "select_grant_to_investigate",
                                    tools=[profile_reader_tool, csv_reader_tool],
                                    output_key="current_grant_id_selected_raw", temp=0.6)

    # ---- ワークフロー用複合エージェント ----
    initial_phase = SequentialAgent(
        name="InitialGathering",
        sub_agents=[
            profile_analyzer,
            hypotheses_generator,
            query_generator,
            search_expert_initial,
        ],
    )

    detailed_loop = LoopAgent(
        name="DetailedInvestigationLoop",
        sub_agents=[
            search_expert_investig,
            investigation_evaluator,
            quality_checker,
            CheckStatusAndEscalate(name="StopChecker")
        ],
        max_iterations=10,
    )

    second_phase = SequentialAgent(
        name="SecondPhase",
        sub_agents=[user_proxy, detailed_loop, report_generator],
    )
    return dict(
        # 単体
        profile_analyzer=profile_analyzer,
        hypotheses_generator=hypotheses_generator,
        query_generator=query_generator,
        search_expert_initial=search_expert_initial,
        search_expert_investigation=search_expert_investig,
        investigation_evaluator=investigation_evaluator,
        quality_checker=quality_checker,
        report_generator=report_generator,
        user_proxy=user_proxy,
        stop_checker=CheckStatusAndEscalate(name="StopChecker"),
        # フロー
        initial_phase_agent=initial_phase,
        detailed_investigation_loop_agent=detailed_loop,
        second_phase_agent=second_phase,
    )