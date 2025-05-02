# --- START OF FILE crew.py ---

import os
import yaml
import json
import time
import datetime # datetime モジュール全体をインポート
from pathlib import Path
from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task
from crewai.llm import LLM
import litellm
import re
import traceback
from typing import List, Dict, Any
import random
import pandas as pd # Pandasをインポート
from dev_grant.tools import (
    UserProfileReaderTool, GoogleSearchTool,
    PDFReaderTool, PDFDownloaderTool, create_web_navigation_tools,
    CSVWriterTool, CSVReaderTool, CSVUpdaterTool # CSVツールをインポート
)
from dotenv import load_dotenv
load_dotenv()
#litellm._turn_on_debug()
import logging
logger = logging.getLogger(__name__)

@CrewBase
class FundingSearchCrew:
    """
    助成金検索エージェントクルー（シーケンシャル実行・評価ループ付き）

    全てのタスクを順番に実行します。
    詳細調査では、情報収集 -> 評価 -> (必要なら再調査) -> 最終報告・更新
    というステップを踏みます。
    """

    def __init__(self, user_profile_path, output_path, grants_to_process=1, max_retries=3, max_investigation_loops=2):
        self.user_profile_path = user_profile_path
        self.output_path = output_path
        self.grants_to_process = grants_to_process # 調査する助成金の最大数
        self.max_retries = max_retries
        self.max_investigation_loops = max_investigation_loops # 1つの助成金に対する最大再調査回数
        self.grants_dir = Path(output_path).parent / "grants_data"
        os.makedirs(self.grants_dir, exist_ok=True)
        os.makedirs(Path(output_path).parent, exist_ok=True)
        self.agents_config = self._load_config('agents.yaml')
        self.tasks_config = self._load_config('tasks.yaml')
        if not os.path.exists(user_profile_path):
            print(f"警告: ユーザープロファイルファイル {user_profile_path} が存在しません")
            profile_dir = os.path.dirname(user_profile_path)
            os.makedirs(profile_dir, exist_ok=True)
            with open(user_profile_path, 'w', encoding='utf-8') as f: f.write("# 自動生成された空のプロファイル")
        self.agent_llms = {}
        self.agent_models = self._load_agent_models()
        self.profile_reader_tool = UserProfileReaderTool()
        self.google_search_tool = GoogleSearchTool()
        self.webnavigation_tools = create_web_navigation_tools()
        self.pdf_reader_tool = PDFReaderTool()
        self.pdf_downloader_tool = PDFDownloaderTool()
        self.csv_writer_tool = CSVWriterTool()
        self.csv_reader_tool = CSVReaderTool()
        self.csv_updater_tool = CSVUpdaterTool()
        self.investigated_grants = [] # 調査済みIDリスト
        self.grants_list_path = os.path.join(self.grants_dir, "grants_candidates.csv")
        self.initial_task_results = {} # 初期フェーズのタスク結果
        self.current_investigation_data = {} # 詳細調査中のデータ

    def _load_agent_models(self):
        # Manager LLM を除外
        default_models = {
            "profile_analyzer": "gemini/gemini-2.0-flash-thinking-exp-01-21",
            "hypotheses_generator": "gemini/gemini-2.0-flash-thinking-exp-01-21",
            "query_generator": "gemini/gemini-2.0-flash-thinking-exp-01-21",
            "search_expert": "gemini/gemini-2.0-flash",
            "investigation_evaluator": "gemini/gemini-2.0-flash", # 評価エージェント用
            "report_generator": "gemini/gemini-2.0-flash",
            "user_proxy": "gemini/gemini-2.0-flash",
        }
        agent_models = {}
        for agent_key, default_model in default_models.items():
            # agents.yaml のキー (英語名) で環境変数を検索
            env_var_name = f"MODEL_{agent_key.upper()}"
            env_model = os.environ.get(env_var_name)
            yaml_role = self.agents_config.get(agent_key, {}).get('role', agent_key) # agents.yamlからroleを取得

            model_name = env_model if env_model else default_model
            if not model_name.startswith("gemini/"): model_name = f"gemini/{model_name}"
            agent_models[yaml_role] = model_name # YAMLのrole名をキーとして保存

        # ログ出力もYAMLのrole名で
        for role, model in agent_models.items():
             print(f"エージェント '{role}' のモデル: {model}")
        return agent_models

    def _get_agent_llm(self, agent_role, temperature=None):
        # agent_role は agents.yaml で定義された role (英語名)
        if temperature is None:
            # 役割に応じて温度を設定 (英語名で判定)
            temp_06_roles = ["ProfileAnalyzer", "HypothesesGenerator", "QueryGenerator", "InvestigationEvaluator", "UserProxy"]
            temperature = 0.6 if agent_role in temp_06_roles else 0.3

        cache_key = f"{agent_role}_{temperature}"
        if cache_key not in self.agent_llms:
            model = self.agent_models.get(agent_role) # role名でモデルを取得
            if not model: model = "gemini/gemini-2.0-flash"; print(f"警告: '{agent_role}' モデル設定なし。フォールバック '{model}' 使用。")
            try:
                 self.agent_llms[cache_key] = LLM(model=model, temperature=temperature)
                 print(f"LLMインスタンス作成: {cache_key} (Role: {agent_role}, Model: {model}, Temp: {temperature})")
            except Exception as e:
                 print(f"LLMインスタンス作成エラー ({cache_key}): {e}")
                 try: fallback_model = "gemini/gemini-2.0-flash"; self.agent_llms[cache_key] = LLM(model=fallback_model, temperature=temperature); print(f"エラーのためフォールバックLLM作成: {cache_key} (Role: {agent_role}, Model: {fallback_model}, Temp: {temperature})")
                 except Exception as fallback_e: print(f"フォールバックLLM作成失敗: {fallback_e}"); raise fallback_e
        llm_instance = self.agent_llms.get(cache_key)
        if llm_instance is None: error_msg = f"LLMインスタンスの取得に失敗しました: {cache_key}"; logger.error(error_msg); raise ValueError(error_msg)
        return llm_instance

    def _load_config(self, filename):
        # 変更なし
        possible_paths = [ Path(filename), Path(__file__).parent / filename, Path(__file__).parent / 'config' / filename, Path(__file__).parent.parent / filename, Path('/workspace/crewai/dev_grant/config') / filename, ]
        for path in possible_paths:
            try:
                print(f"設定ファイルを確認中: {path}")
                if path.exists():
                    with open(path, 'r', encoding='utf-8') as file:
                        content = file.read();
                        if content: return yaml.safe_load(content)
                        else: print(f"警告: 設定ファイル {path} は空です。"); return {}
            except yaml.YAMLError as e: print(f"設定ファイル {path} のYAML解析エラー: {e}"); return {}
            except Exception as e: print(f"設定ファイル {path} の読み込み失敗: {str(e)}"); continue
        print(f"警告: {filename} が見つかりませんでした。デフォルト設定を使用します。"); return {}

    def _get_timestamp(self):
        # ISO 8601形式のタイムスタンプを返す
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def load_processed_grants(self):
        # 変更なし
        try:
            if not os.path.exists(self.grants_list_path): print(f"助成金リストCSVが見つかりません: {self.grants_list_path}"); return False
            grants_df = pd.read_csv(self.grants_list_path)
            print(f"読み込んだCSVの列: {grants_df.columns.tolist()}"); print(f"CSVの行数: {len(grants_df)}")
            investigated_grants = []
            if 'id' not in grants_df.columns: print("警告: CSVに 'id' 列がありません。"); return False
            grants_df['id_str'] = grants_df['id'].astype(str)
            if 'investigated' in grants_df.columns:
                try:
                    investigated_mask = (grants_df['investigated'] == True) | (grants_df['investigated'].astype(str).str.lower() == 'true') | (grants_df['investigated'] == 1) | (grants_df['investigated'] == 1.0)
                    investigated_by_flag = grants_df.loc[investigated_mask, 'id_str'].tolist()
                    print(f"investigatedフラグによる検出: {len(investigated_by_flag)}件"); investigated_grants.extend(investigated_by_flag)
                except Exception as e: print(f"investigatedフラグの解析エラー: {str(e)}")
            if 'completeness_score' in grants_df.columns:
                try:
                    investigated_by_score = grants_df[grants_df['completeness_score'].notna() & (grants_df['completeness_score'] != '')]['id_str'].tolist()
                    print(f"completeness_scoreによる検出: {len(investigated_by_score)}件")
                    new_ids = [id_str for id_str in investigated_by_score if id_str not in investigated_grants]; investigated_grants.extend(new_ids)
                except Exception as e: print(f"completeness_score解析エラー: {str(e)}")
            if 'updated_at' in grants_df.columns:
                 try:
                     investigated_by_update = grants_df[grants_df['updated_at'].notna() & (grants_df['updated_at'] != '')]['id_str'].tolist()
                     print(f"updated_atによる検出: {len(investigated_by_update)}件")
                     new_ids = [id_str for id_str in investigated_by_update if id_str not in investigated_grants]; investigated_grants.extend(new_ids)
                 except Exception as e: print(f"updated_at解析エラー: {str(e)}")
            investigated_grants = list(set(investigated_grants)); self.investigated_grants = investigated_grants
            if investigated_grants:
                print(f"{len(investigated_grants)}件の調査済み助成金情報をCSVから読み込みました"); print(f"調査済みID (最大20件): {', '.join(investigated_grants[:20])}{'...' if len(investigated_grants) > 20 else ''}")
                try:
                    needs_update = False
                    for grant_id_str in investigated_grants:
                        row_index = grants_df[grants_df['id_str'] == grant_id_str].index
                        if not row_index.empty:
                            idx = row_index[0]
                            current_investigated = grants_df.loc[idx, 'investigated'] if 'investigated' in grants_df.columns else None
                            if not (current_investigated == True or str(current_investigated).lower() == 'true' or str(current_investigated) == '1' or str(current_investigated) == '1.0'):
                                if 'investigated' not in grants_df.columns: grants_df['investigated'] = 0
                                grants_df.loc[idx, 'investigated'] = 1; needs_update = True
                            current_score = grants_df.loc[idx, 'completeness_score'] if 'completeness_score' in grants_df.columns else None
                            # スコアが空またはNaNの場合に 1.0 で埋めるロジックは削除（ReportGeneratorが担当）
                            # if pd.isna(current_score) or current_score == '':
                            #     if 'completeness_score' not in grants_df.columns: grants_df['completeness_score'] = pd.NA
                            #     grants_df.loc[idx, 'completeness_score'] = 1.0; needs_update = True
                    if needs_update:
                         grants_df.drop(columns=['id_str'], errors='ignore').to_csv(self.grants_list_path, index=False); print(f"CSVの調査済みフラグを整合性を確保するために更新しました")
                except Exception as fix_err: print(f"CSVフラグ修正エラー: {str(fix_err)}")
                return True
            else: print("調査済みの助成金は見つかりませんでした"); return False
        except FileNotFoundError: print(f"助成金リストCSVが見つかりません: {self.grants_list_path}"); return False
        except Exception as e: print(f"CSVデータ読み込み中にエラーが発生: {str(e)}"); traceback.print_exc(); return False

    # --- エージェント定義 (英語名に変更、Manager削除、Evaluator追加) ---
    @agent
    def profile_analyzer(self) -> Agent:
        config = self.agents_config.get('profile_analyzer', {})
        role = config.get('role', 'ProfileAnalyzer') # 英語名を使用
        llm_instance = self._get_agent_llm(role)
        return Agent(role=role, goal=config.get('goal'), backstory=config.get('backstory'), verbose=False, llm=llm_instance, tools=[self.profile_reader_tool], allow_delegation=False)

    @agent
    def hypotheses_generator(self) -> Agent:
        config = self.agents_config.get('hypotheses_generator', {})
        role = config.get('role', 'HypothesesGenerator')
        llm_instance = self._get_agent_llm(role)
        return Agent(role=role, goal=config.get('goal'), backstory=config.get('backstory'), verbose=False, llm=llm_instance, tools=[self.profile_reader_tool], allow_delegation=False)

    @agent
    def query_generator(self) -> Agent:
        config = self.agents_config.get('query_generator', {})
        role = config.get('role', 'QueryGenerator')
        llm_instance = self._get_agent_llm(role)
        return Agent(role=role, goal=config.get('goal'), backstory=config.get('backstory'), verbose=False, llm=llm_instance, tools=[], allow_delegation=False)

    @agent
    def search_expert(self) -> Agent:
        config = self.agents_config.get('search_expert', {})
        role = config.get('role', 'SearchExpert')
        llm_instance = self._get_agent_llm(role)
        return Agent(
            role=role, goal=config.get('goal'), backstory=config.get('backstory'),
            verbose=True,
            llm=llm_instance, allow_delegation=False, memory=True,
            tools=[ self.google_search_tool, *self.webnavigation_tools, self.pdf_reader_tool, self.pdf_downloader_tool, self.csv_writer_tool , self.csv_reader_tool]
        )

    @agent
    def investigation_evaluator(self) -> Agent:
        """収集された助成金情報を評価し、再調査が必要か判断するエージェント"""
        config = self.agents_config.get('investigation_evaluator', {}) # agents.yaml に定義を追加
        role = config.get('role', 'InvestigationEvaluator')
        llm_instance = self._get_agent_llm(role)
        return Agent(
            role=role,
            goal=config.get('goal', 'Evaluate the completeness of collected grant information and identify missing critical fields.'),
            backstory=config.get('backstory', 'An meticulous analyst specializing in data validation. I check if essential grant details (like deadline, eligibility, amount) are present and generate instructions for re-investigation if needed.'),
            verbose=True,
            llm=llm_instance,
            tools=[], # 基本的にツールは不要
            allow_delegation=False # 自分で判断する
        )

    @agent
    def report_generator(self) -> Agent:
        config = self.agents_config.get('report_generator', {})
        role = config.get('role', 'ReportGenerator')
        llm_instance = self._get_agent_llm(role)
        # goal と backstory は tasks.yaml で具体的に指示
        goal = config.get('goal', 'Evaluate collected grant information, assign scores, and update the CSV file.')
        backstory = config.get('backstory', 'Expert in structuring information and providing objective evaluations. Responsible for accurately reflecting evaluated data into the persistent CSV store using CSVUpdaterTool.')
        return Agent(role=role, goal=goal, backstory=backstory, verbose=True, llm=llm_instance, memory=True, allow_delegation=False, tools=[self.csv_reader_tool, self.csv_updater_tool])

    @agent
    def user_proxy(self) -> Agent:
        config = self.agents_config.get('user_proxy', {})
        role = config.get('role', 'UserProxy')
        llm_instance = self._get_agent_llm(role)
        return Agent(role=role, goal=config.get('goal'), backstory=config.get('backstory'), verbose=False, llm=llm_instance, tools=[self.profile_reader_tool, self.csv_reader_tool], allow_delegation=False)


    # --- タスク定義 (シーケンシャル用) ---
    @task
    def analyze_profile_task(self) -> Task:
        config = self.tasks_config.get('analyze_profile_task', {})
        description = config.get('description', '').replace('{user_profile_path}', self.user_profile_path)
        return Task(description=description, expected_output=config.get('expected_output'), agent=self.profile_analyzer())

    @task
    def generate_hypotheses_task(self) -> Task:
        config = self.tasks_config.get('generate_hypotheses_task', {})
        return Task(description=config.get('description'), expected_output=config.get('expected_output'), agent=self.hypotheses_generator(), context=[self.analyze_profile_task()])

    @task
    def generate_queries_task(self) -> Task:
        config = self.tasks_config.get('generate_queries_task', {})
        return Task(description=config.get('description'), expected_output=config.get('expected_output'), agent=self.query_generator(), context=[self.analyze_profile_task(), self.generate_hypotheses_task()])

    @task
    def generate_initial_grants_list_task(self) -> Task:
        config = self.tasks_config.get('generate_initial_grants_list_task', {})
        description = config.get('description').replace("{grants_list_path}", self.grants_list_path)
        expected_output = config.get('expected_output', f"CSVファイル '{self.grants_list_path}' の作成完了を示すメッセージ。").replace("{grants_list_path}", self.grants_list_path)
        return Task(
            description=description,
            expected_output=expected_output, agent=self.search_expert(),
            tools=[self.google_search_tool, self.csv_writer_tool],
            context=[self.generate_queries_task()]
        )

    @task
    def select_grant_to_investigate_task(self) -> Task:
        """調査する助成金を選択するタスク (1件のみ選択)"""
        config = self.tasks_config.get('select_grant_to_investigate_task', {}) # YAMLファイル名修正
        # description は kickoff 時に動的にフォーマットする
        return Task(
            description=config.get('description'), # プレースホルダーを含むテンプレート
            expected_output=config.get('expected_output'),
            agent=self.user_proxy(),
            tools=[self.profile_reader_tool, self.csv_reader_tool],
            context=[self.generate_initial_grants_list_task()]
        )

    @task
    def investigate_grant_task(self) -> Task:
        """選択された助成金の詳細調査タスク"""
        config = self.tasks_config.get('investigate_grant_task', {})
        # description は kickoff 時に動的にフォーマットする
        return Task(
            description=config.get('description'), # プレースホルダーを含むテンプレート
            expected_output=config.get('expected_output'),
            agent=self.search_expert(),
            tools=[self.csv_reader_tool, self.google_search_tool, *self.webnavigation_tools, self.pdf_downloader_tool, self.pdf_reader_tool],
            # context は kickoff 内で動的に設定 (select_task の結果など)
        )

    @task
    def evaluate_investigation_task(self) -> Task:
        """収集された情報を評価し、再調査が必要か判断するタスク"""
        config = self.tasks_config.get('evaluate_investigation_task', {}) # YAMLに定義を追加
        # description は kickoff 時に動的にフォーマットする (調査結果JSONを含む)
        return Task(
            description=config.get('description'), # プレースホルダーを含むテンプレート
            expected_output=config.get('expected_output'),
            agent=self.investigation_evaluator(), # 新しいエージェント
            tools=[],
            # context は kickoff 内で動的に設定 (investigate_task の結果)
        )

    @task
    def report_and_update_task(self) -> Task:
        """収集・評価された情報を最終報告し、CSVを更新するタスク"""
        config = self.tasks_config.get('report_and_update_task', {}) # YAMLファイル名修正
        # description は kickoff 時に動的にフォーマットする
        return Task(
            description=config.get('description'), # プレースホルダーを含むテンプレート
            expected_output=config.get('expected_output'),
            agent=self.report_generator(),
            tools=[self.csv_reader_tool, self.csv_updater_tool],
            # context は kickoff 内で動的に設定 (最終的な調査結果や評価結果)
        )

    # --- ヘルパーメソッド ---
    def _parse_grant_ids(self, result_text):
        # 変更なし (ただし、JSON形式の出力も考慮する方が堅牢)
        try:
            # まずJSONとしてパース試行
            try:
                data = json.loads(result_text)
                if "selected_grant_id" in data and isinstance(data["selected_grant_id"], str) and data["selected_grant_id"].startswith("grant_"):
                    return [data["selected_grant_id"]]
            except json.JSONDecodeError:
                pass # JSONでなければ次のパターンマッチへ

            import re
            patterns = [ r"ID:?\s*([a-zA-Z0-9_-]+)", r"助成金\s*ID:?\s*([a-zA-Z0-9_-]+)", r"ID\s*['\"\「]([a-zA-Z0-9_-]+)['\"\」]", r"grant_id:?\s*([a-zA-Z0-9_-]+)", r"ID\s*[#:]?\s*([a-zA-Z0-9_-]+)", r"[「\[]([a-zA-Z0-9_-]+)[」\]]", r"「ID:([a-zA-Z0-9_-]+)」", r"選択した助成金:\s*([a-zA-Z0-9_-]+)", r"\b(grant_\d+)\b"]
            ids = []
            for pattern in patterns: matches = re.findall(pattern, result_text, re.IGNORECASE); ids.extend(matches)
            filtered_ids = [id_str for id_str in ids if id_str.lower().startswith("grant_")]
            if not filtered_ids and ids:
                 potential_ids = list(set(ids))
                 validated_ids = [pid for pid in potential_ids if len(pid) > 3 and not pid.isdigit()]
                 print(f"grant_ プレフィックスなしで検出されたID候補: {potential_ids} -> 検証後: {validated_ids}")
                 return [str(validated_ids[0])] if validated_ids else [] # 最初の1件
            return [str(filtered_ids[0])] if filtered_ids else [] # 最初の1件
        except Exception as e: logger.error(f"助成金ID解析エラー: {str(e)}"); return []

    def execute_task_with_retry(self, task: Task, context_tasks: List[Task] = None):
        agent = task.agent
        if not agent:
            return f"タスク '{task.description[:50]}...' にエージェントが割り当てられていません。"

        required_tools = task.tools or []
        agent_tools = agent.tools or []
        missing_tools = [tool.name for tool in required_tools if tool not in agent_tools]
        if missing_tools:
            print(f"警告: タスク '{task.description[:50]}...' に必要なツール {missing_tools} がエージェント '{agent.role}' に設定されていません。ツールを追加します。")
            try:
                 agent.tools.extend([tool for tool in required_tools if tool not in agent_tools])
            except Exception as tool_add_err:
                 print(f"  ツール追加エラー: {tool_add_err}")

        # コンテキスト情報をタスク説明に追加
        original_description = task.description # 元の説明を保持
        if context_tasks:
            context_str = "\n\n--- Context from Previous Tasks ---\n"
            valid_context_count = 0
            for i, ctx_task in enumerate(reversed(context_tasks)): # 新しいタスクから順に参照
                if hasattr(ctx_task, 'output') and ctx_task.output: # output属性の存在を確認
                    task_output_str = self.handle_result(ctx_task.output)
                    truncated_output = self.truncate_text(task_output_str, 1000)
                    context_str += f"Context {i+1} (from {ctx_task.agent.role if ctx_task.agent else 'Unknown Task'}):\n{truncated_output}\n\n"
                    valid_context_count += 1
                    if valid_context_count >= 3:
                         break
            if valid_context_count > 0:
                 # descriptionがNoneでないことを確認
                 if task.description is None:
                     task.description = ""
                 task.description += context_str


        for attempt in range(self.max_retries):
            try:
                print(f"\nタスク '{task.description[:50]}...' を実行中（試行 {attempt + 1}/{self.max_retries}）")

                # --- 修正箇所 ---
                # execute_sync() から inputs 引数を削除
                task_output_obj = task.execute_sync()
                # --- 修正ここまで ---

                # TaskOutput オブジェクトに結果を格納
                # execute_sync は TaskOutput を返すはずなので、そのまま格納
                task.output = task_output_obj

                result = self.handle_result(task_output_obj) # 文字列結果を取得

                if result is None or result == "": raise ValueError("LLMからの応答が空です。")
                result_lower = result.lower()
                if "action 'n/a' don't exist" in result_lower: raise ValueError("エージェントが不正なアクション 'N/A' を試みました。")
                if "invalid response from llm call" in result_lower: raise ValueError(f"LLMからの応答が無効です: {result}")
                if "error executing tool" in result_lower: raise ValueError(f"ツール実行エラーが発生しました: {result}")
                if "coworker mentioned not found" in result_lower: raise ValueError(f"存在しないcoworkerへの委任試行: {result}")

                print(f"タスク実行成功（試行 {attempt + 1}）")
                task.description = original_description # 説明を元に戻す
                return result # 文字列の結果を返す
            except Exception as e:
                error_msg = str(e)
                print(f"タスク実行エラー（試行 {attempt + 1}）: {error_msg}")
                traceback.print_exc()
                task.description = original_description # リトライ前に説明を元に戻す
                wait_time = (2 ** attempt) * random.uniform(5, 10)
                if "rate limit" in error_msg.lower(): wait_time = (2 ** attempt) * random.uniform(25, 35); print(f"レート制限の可能性があるため、{wait_time:.1f}秒後に再試行...")
                elif "internal server error" in error_msg.lower() or "500" in error_msg: wait_time = (2 ** attempt) * random.uniform(15, 25); print(f"内部サーバーエラーのため、{wait_time:.1f}秒後に再試行...")
                else: print(f"{wait_time:.1f}秒後に再試行します...")
                if attempt < self.max_retries - 1: time.sleep(wait_time)
                else: print(f"最大試行回数 ({self.max_retries}回) に達しました。"); return f"タスク実行失敗 (最大リトライ回数超過): {error_msg}"

        task.description = original_description # 最終的に説明を元に戻す
        return f"タスク実行失敗 (最大リトライ回数超過): 不明なエラー"

    def _cleanup_old_backups(self, max_backups=3):
        # 変更なし
        import os, glob
        try:
            backup_dir = os.path.dirname(self.grants_list_path); base_name = os.path.basename(self.grants_list_path)
            backup_patterns = [ os.path.join(backup_dir, f"{base_name}.*.bak"), os.path.join(backup_dir, f"*backup*.csv")]
            all_backups = []; [all_backups.extend(glob.glob(pattern)) for pattern in backup_patterns]
            all_backups.sort(key=os.path.getmtime)
            if len(all_backups) > max_backups:
                for file_path in all_backups[:-max_backups]:
                    try: os.remove(file_path); print(f"古いバックアップを削除: {os.path.basename(file_path)}")
                    except Exception as delete_err: print(f"バックアップ削除エラー: {str(delete_err)}")
                print(f"バックアップクリーンアップ完了 (残り: {min(len(all_backups), max_backups)}個)")
        except Exception as e: print(f"バックアップクリーンアップエラー: {str(e)}")

    def backup_grants_csv(self, max_backups=3):
        # 変更なし
        import os, shutil, datetime, glob
        if not os.path.exists(self.grants_list_path): print(f"バックアップ不可: {self.grants_list_path} が存在しません"); return False
        backup_dir = os.path.dirname(self.grants_list_path); base_name = os.path.basename(self.grants_list_path)
        today = datetime.datetime.now().strftime("%Y%m%d")
        today_pattern = os.path.join(backup_dir, f"{base_name}.{today}_*.bak"); today_backups = glob.glob(today_pattern)
        daily_max_backups = 5
        if len(today_backups) >= daily_max_backups: print(f"本日すでに{len(today_backups)}個のバックアップ済み、スキップします"); return sorted(today_backups, key=os.path.getmtime)[-1]
        try:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S"); backup_path = os.path.join(backup_dir, f"{base_name}.{timestamp}.bak")
            shutil.copy2(self.grants_list_path, backup_path); print(f"助成金リストをバックアップ: {backup_path}")
            self._cleanup_old_backups(max_backups); return backup_path
        except Exception as e: print(f"バックアップ作成エラー: {str(e)}"); return False

    def restore_grants_csv_if_needed(self, backup_path, ignore_rows=None):
        # 変更なし
        import os, pandas as pd, shutil
        if not backup_path or not os.path.exists(backup_path): print("有効なバックアップパスがありません"); return False
        if not os.path.exists(self.grants_list_path):
            print(f"現在のCSVが見つからないため復元: {self.grants_list_path}")
            try: shutil.copy2(backup_path, self.grants_list_path); print(f"バックアップから復元完了: {backup_path} -> {self.grants_list_path}"); return True
            except Exception as e: print(f"復元エラー: {str(e)}"); return False
        try:
            backup_df = pd.read_csv(backup_path); current_df = pd.read_csv(self.grants_list_path)
            if 'id' not in backup_df.columns or 'id' not in current_df.columns: print("警告: 'id'列がないため復元スキップ。"); return False
            backup_ids = set(backup_df['id'].astype(str)); current_ids = set(current_df['id'].astype(str))
            missing_ids = backup_ids - current_ids
            if ignore_rows: missing_ids = missing_ids - set(map(str, ignore_rows))
            if missing_ids:
                print(f"CSVデータ欠落検出 ({len(missing_ids)}行): {missing_ids}")
                missing_rows = backup_df[backup_df['id'].astype(str).isin(missing_ids)]
                current_cols = set(current_df.columns); missing_cols = set(missing_rows.columns)
                for col in missing_cols - current_cols: current_df[col] = pd.NA
                for col in current_cols - missing_cols: missing_rows[col] = pd.NA
                missing_rows = missing_rows[current_df.columns]
                merged_df = pd.concat([current_df, missing_rows], ignore_index=True)
                merged_df.to_csv(self.grants_list_path, index=False)
                print(f"欠落した{len(missing_ids)}行をバックアップから復元しました"); return True
            return False
        except Exception as e: print(f"CSV整合性チェックエラー: {str(e)}"); return False

    # @crew デコレータは使用しない

    def truncate_text(self, text, max_length=1000): # コンテキスト用に短縮
        # 変更
        if text and isinstance(text, str) and len(text) > max_length:
            return text[:max_length] + f"\n...(truncated, {len(text)} chars total)"
        return text

    def handle_result(self, result):
        # 変更なし
        if result is None: return ""
        output_text = ""
        try:
            if isinstance(result, str): output_text = result
            elif hasattr(result, 'raw') and result.raw is not None: output_text = str(result.raw)
            elif hasattr(result, 'raw_output') and result.raw_output is not None: output_text = str(result.raw_output)
            elif hasattr(result, 'result') and result.result is not None: # TaskOutputの場合
                output_text = str(result.result)
            elif hasattr(result, 'outputs') and result.outputs: # CrewOutputの場合
                 if isinstance(result.outputs, list) and len(result.outputs) > 0:
                      first_output = result.outputs[0]
                      if hasattr(first_output, 'raw') and first_output.raw is not None: output_text = str(first_output.raw)
                      elif hasattr(first_output, 'result') and first_output.result is not None: output_text = str(first_output.result)
                      else: output_text = str(first_output)
                 elif isinstance(result.outputs, list): output_text = ""
                 else: output_text = str(result.outputs)
            elif hasattr(result, 'output') and result.output is not None: output_text = str(result.output)
            else: output_text = str(result)
        except Exception as e: print(f"Error handling result type {type(result)}: {e}"); output_text = str(result)
        return output_text

    def _extract_missing_fields(self, evaluation_output: str) -> List[str]:
        """評価タスクの出力から不足フィールド名を抽出する簡易ロジック (要調整)"""
        missing = []
        # 簡単なキーワード検索とフィールド名のリストで抽出を試みる
        keywords = ['amount', 'eligibility', 'deadline', 'application_process', 'required_documents', 'contact', 'duration', 'special_conditions', 'research_fields']
        output_lower = evaluation_output.lower()
        # "追加調査指示:" や "不足フィールド:" のようなマーカーを探す
        markers = ["追加調査指示", "不足フィールド", "不足している項目", "調査が必要", "missing fields", "further investigation required"]
        found_marker = any(marker in evaluation_output for marker in markers)

        if found_marker:
            for key in keywords:
                # フィールド名が評価出力に含まれているか
                if key in output_lower:
                    missing.append(key)
        # 他の抽出ロジック（正規表現など）も検討可能
        # 例: "以下のフィールドが不足: ['deadline', 'amount']" のような形式をパース
        try:
            import re
            match = re.search(r"\[\s*['\"]([^'\"]+)['\"](?:\s*,\s*['\"]([^'\"]+)['\"])*\s*\]", evaluation_output)
            if match:
                # 正規表現で見つかったフィールド名を追加
                missing.extend([g for g in match.groups() if g])
        except Exception:
            pass # 正規表現エラーは無視

        return list(set(missing)) # 重複削除

    def kickoff(self, inputs: Dict[str, Any] = None):
        """シーケンシャルな助成金検索プロセス（評価・再調査ループ付き）"""
        print("助成金検索プロセスを開始しています...")
        import pandas as pd 
        self.load_processed_grants()
        self.initial_task_results = {}
        all_detailed_results = [] # 詳細調査結果を格納するリスト
        executed_tasks_history = [] # 全実行済みタスクオブジェクト

        # 現在の日付を取得（inputs から、なければ現在の日付を使用）
        current_date = None
        if inputs and 'current_date' in inputs:
            current_date = inputs['current_date']
            print(f"検索日: {current_date}")
        else:
            import datetime
            current_date = datetime.datetime.now().strftime("%Y-%m-%d")
            print(f"検索日（自動生成）: {current_date}")

        # --- ステップ1: 初期情報収集フェーズ ---
        print("\nステップ1: 初期情報収集フェーズを実行中...")
        try:
            # タスクインスタンスを取得
            task1 = self.analyze_profile_task()
            task2 = self.generate_hypotheses_task()
            task3 = self.generate_queries_task()
            task4 = self.generate_initial_grants_list_task()

            # 1. プロファイル分析
            analyze_result = self.execute_task_with_retry(task1)
            self.initial_task_results['analyze'] = analyze_result
            executed_tasks_history.append(task1)
            if "タスク実行失敗" in analyze_result: raise Exception("プロファイル分析タスク失敗")
            print("  - プロファイル分析完了")

            # 2. 仮説生成
            hypotheses_result = self.execute_task_with_retry(task2, context_tasks=[task1])
            self.initial_task_results['hypotheses'] = hypotheses_result
            executed_tasks_history.append(task2)
            if "タスク実行失敗" in hypotheses_result: raise Exception("仮説生成タスク失敗")
            print("  - カテゴリ仮説生成完了")

            # 3. クエリ生成
            queries_result = self.execute_task_with_retry(task3, context_tasks=[task1, task2])
            self.initial_task_results['queries'] = queries_result
            executed_tasks_history.append(task3)
            if "タスク実行失敗" in queries_result: raise Exception("クエリ生成タスク失敗")
            print("  - 検索クエリ生成完了")

            # 4. 初期リスト生成
            initial_list_result = self.execute_task_with_retry(task4, context_tasks=[task3])
            self.initial_task_results['initial_list'] = initial_list_result
            executed_tasks_history.append(task4)
            if "タスク実行失敗" in initial_list_result: raise Exception("初期リスト生成タスク失敗")
            print("  - 初期助成金リスト生成・保存完了")

            if not os.path.exists(self.grants_list_path) or os.path.getsize(self.grants_list_path) < 50:
                print("警告: CSVファイルが見つからないか不完全です。空のCSVファイルを作成します。")
                try:
                    # ディレクトリの作成
                    csv_dir = os.path.dirname(self.grants_list_path)
                    if not os.path.exists(csv_dir):
                        os.makedirs(csv_dir, exist_ok=True)
                        
                    # 空のDataFrameをヘッダー付きで作成
                    import pandas as pd
                    # 必要なすべての列を含むヘッダーを定義
                    headers = [
                        'id', 'title', 'organization', 'description', 'url', 'category',
                        'investigated', 'completeness_score', 'relevance_score', 'updated_at',
                        'amount', 'eligibility', 'deadline', 'application_process',
                        'required_documents', 'research_fields', 'duration', 'contact',
                        'special_conditions'
                    ]
                    
                    # 空のDataFrameを作成して保存
                    df = pd.DataFrame(columns=headers)
                    df.to_csv(self.grants_list_path, index=False)
                    
                    print(f"ヘッダーのみのCSVファイルを作成しました: {self.grants_list_path}")
                except Exception as e:
                    print(f"CSVファイル作成エラー: {str(e)}")
                    # エラーが発生しても処理を続行

        except Exception as e:
            print(f"初期情報収集フェーズでエラーが発生: {str(e)}")
            traceback.print_exc()
            return {"status": "error", "message": f"初期情報収集エラー: {e}", "results": self.initial_task_results}

        # CSV準備
        print(f"\nCSVファイルが正常に生成/確認されました: {self.grants_list_path}")
        active_backup_path = None
        try:
            df = pd.read_csv(self.grants_list_path)
            print(f"CSVには{len(df)}件の助成金候補があります")
            required_columns = ['investigated', 'completeness_score', 'relevance_score', 'updated_at']
            needs_save = False
            for col in required_columns:
                if col not in df.columns:
                    default_value = 0 if col == 'investigated' else ''
                    df[col] = default_value
                    needs_save = True
            if needs_save:
                 df.to_csv(self.grants_list_path, index=False);
                 print("CSVに必要な列 (investigated, completeness_score, relevance_score, updated_at) を追加しました。")
            initial_backup_path = self.backup_grants_csv()
            if initial_backup_path: print(f"初期助成金リストをバックアップしました: {initial_backup_path}"); active_backup_path = initial_backup_path
        except Exception as e: print(f"CSVファイルの読み込み/更新/バックアップエラー: {str(e)}"); traceback.print_exc()

        # --- ステップ2: 詳細調査ループ ---
        print("\nステップ2: 詳細調査ループを開始...")
        try:
            grants_count_str = os.environ.get("GRANTS_COUNT", "1")
            max_investigation_grants = int(grants_count_str) if grants_count_str.isdigit() else 1
            max_investigation_grants = max(1, min(max_investigation_grants, 10))
            print(f"最大調査助成金数: {max_investigation_grants}")
        except Exception as e: max_investigation_grants = 1; print(f"助成金数の設定エラー: {str(e)}。デフォルト値({max_investigation_grants})を使用します。")

        investigated_count = 0
        while investigated_count < max_investigation_grants:
            print(f"\n--- 詳細調査 {investigated_count + 1}/{max_investigation_grants} ---")

            if active_backup_path: self.restore_grants_csv_if_needed(active_backup_path, self.investigated_grants)

            # 5. 調査対象選択
            print("調査する助成金を選択中...")
            task5 = self.select_grant_to_investigate_task()
            task5.description = task5.description.format(
                grants_list_path=self.grants_list_path,
                investigated_grants=", ".join(map(str, self.investigated_grants)) if self.investigated_grants else "なし",
                current_date=current_date
            )
            select_result_str = self.execute_task_with_retry(task5, context_tasks=executed_tasks_history)
            if "タスク実行失敗" in select_result_str:
                 print("助成金選択タスク失敗。調査ループを終了します。")
                 all_detailed_results.append({"grant_id": "N/A", "status": "selection_failed", "error": select_result_str})
                 break
            executed_tasks_history.append(task5) # 選択タスクも履歴に
            print(f"選択結果:\n{select_result_str}")

            selected_grant_ids = self._parse_grant_ids(select_result_str)
            print(f"解析された助成金ID: {selected_grant_ids}")

            if not selected_grant_ids:
                print("調査対象となる未調査の助成金が見つかりませんでした。調査を終了します。")
                break

            current_grant_id = selected_grant_ids[0]
            if current_grant_id in self.investigated_grants:
                 print(f"ID '{current_grant_id}' は既に調査済みとしてマークされています。スキップします。")
                 # 調査済みリストから削除して再調査を試みる場合
                 # self.investigated_grants.remove(current_grant_id)
                 # print(f"ID '{current_grant_id}' を調査済みリストから削除し、再調査を試みます。")
                 continue # スキップして次のループへ

            print(f"選択された助成金ID (今回処理対象): {current_grant_id}")
            round_backup_path = self.backup_grants_csv(); active_backup_path = round_backup_path or active_backup_path

            # --- 6. 詳細情報収集と評価・再調査ループ ---
            print(f"\n助成金 '{current_grant_id}' の詳細情報を収集中...")
            final_investigation_json = None # この助成金の最終的な調査結果JSON
            missing_fields_for_prompt = []
            loop_context_tasks = executed_tasks_history # ループ開始時の全体コンテキスト

            for loop in range(self.max_investigation_loops):
                print(f"  調査/評価ループ {loop + 1}/{self.max_investigation_loops}...")

                # 6a. 情報収集タスク
                task6 = self.investigate_grant_task()
                # 最新のタスク説明テンプレートを取得
                task6_config = self.tasks_config.get('investigate_grant_task', {})
                task6_description = task6_config.get('description', '')
                # プレースホルダーを置換
                task6.description = task6_description.replace('{grant_ids}', current_grant_id)
                task6.description = task6.description.replace('{grants_list_path}', self.grants_list_path)
                task6.description = task6.description.replace('{current_date}', current_date)
                # 再調査指示があれば追記
                if missing_fields_for_prompt:
                    task6.description += f"\n\n**追加調査依頼:** 前回の評価で以下の情報が不足していました。これらの情報を重点的に調査してください: {', '.join(missing_fields_for_prompt)}"

                # 実行。コンテキストはループ開始時のものを使う（ループ内で増え続けないように）
                investigation_result_str = self.execute_task_with_retry(task6, context_tasks=loop_context_tasks)
                # 実行済みリストには追加しない（ループ内で毎回実行されるため）

                if "タスク実行失敗" in investigation_result_str:
                     print(f"  情報収集タスク失敗 (ループ {loop + 1})。")
                     final_investigation_json = {"error": f"Investigation failed: {investigation_result_str}"}
                     break # この助成金の調査ループ中断

                # 結果をパースして保持
                try:
                    current_investigation_data = json.loads(investigation_result_str)
                    final_investigation_json = current_investigation_data # 最新の結果で上書き
                except json.JSONDecodeError:
                    print(f"  警告: 情報収集結果がJSON形式ではありません (ループ {loop + 1})。評価に進みます。")
                    final_investigation_json = {"raw_output": investigation_result_str, "parsing_error": "Non-JSON output"}
                except Exception as parse_err:
                    print(f"  警告: 収集結果の解析中にエラー: {parse_err}。")
                    final_investigation_json = {"raw_output": investigation_result_str, "parsing_error": f"Result parsing error: {parse_err}"}


                # 6b. 評価タスク
                print(f"  収集結果を評価中 (ループ {loop + 1})...")
                task6_5 = self.evaluate_investigation_task()
                task6_5_config = self.tasks_config.get('evaluate_investigation_task', {})
                task6_5_description = task6_5_config.get('description', '')
                # 評価タスクの説明に調査結果JSONを埋め込む
                task6_5.description = task6_5_description.replace('{investigation_result_json}', json.dumps(final_investigation_json, ensure_ascii=False, indent=2))

                # 評価タスク実行。コンテキストはループ開始時のもの＋直前の調査結果
                # execute_task_with_retry にはリストで渡す
                evaluation_context = loop_context_tasks + ([task6] if task6.output else []) # 直前の調査タスクを追加
                evaluation_result_str = self.execute_task_with_retry(task6_5, context_tasks=evaluation_context)
                # 評価タスクも実行済みリストには追加しない

                if "タスク実行失敗" in evaluation_result_str:
                    print(f"  評価タスク失敗 (ループ {loop + 1})。調査ループを終了します。")
                    if final_investigation_json and "error" not in final_investigation_json:
                         final_investigation_json["evaluation_error"] = f"Evaluation failed: {evaluation_result_str}"
                    break # ループ終了

                # 評価結果の判定
                if "調査完了" in evaluation_result_str:
                    print("  評価結果: 調査完了。")
                    # evaluation_result_str にスコアなどの情報が含まれている可能性もあるので最終結果に含める
                    if isinstance(final_investigation_json, dict):
                         final_investigation_json["evaluation_result"] = evaluation_result_str
                    break # 調査ループ終了
                else:
                    missing_fields_for_prompt = self._extract_missing_fields(evaluation_result_str)
                    if not missing_fields_for_prompt or loop == self.max_investigation_loops - 1:
                        if not missing_fields_for_prompt:
                             print("  評価結果から不足フィールドを抽出できませんでした。ループを終了します。")
                        else:
                             print(f"  最大再調査ループ回数 ({self.max_investigation_loops}) に到達しました。不足情報が残っている可能性があります。")
                        if isinstance(final_investigation_json, dict):
                            final_investigation_json["evaluation_result"] = evaluation_result_str # 最終評価結果を記録
                        break # ループ終了
                    else:
                        print(f"  評価結果: 不足情報あり ({missing_fields_for_prompt})。再調査します。")
                        # missing_fields_for_prompt は次のループのタスク説明で使用される

            # --- 詳細調査ループ終了後 ---
            if final_investigation_json is None or "error" in final_investigation_json or "evaluation_error" in final_investigation_json:
                 status = "investigation_failed"
                 error_msg = final_investigation_json.get("error", final_investigation_json.get("evaluation_error", "Unknown investigation error")) if final_investigation_json else "Investigation did not run or failed early"
                 all_detailed_results.append({"grant_id": current_grant_id, "status": status, "error": error_msg})
                 print(f"ID '{current_grant_id}' の調査/評価に失敗しました: {error_msg}")
                 # 失敗しても次の助成金へ進む
                 investigated_count += 1
                 # 調査済みリストには追加しない方が良いかもしれない
                 print(f"\n現在の調査済み助成金: {len(self.investigated_grants)}件")
                 if self.investigated_grants: print(f"調査済みID: {', '.join(self.investigated_grants)}")
                 if investigated_count < max_investigation_grants: time.sleep(10); print("\n...") # 短い待機
                 continue

            # 7. 最終レポート生成とCSV更新
            print(f"\n助成金 '{current_grant_id}' の最終レポート生成と更新中...")
            task7 = self.report_and_update_task()
            task7_config = self.tasks_config.get('report_and_update_task', {})
            task7_description = task7_config.get('description', '')
            # プレースホルダーを置換
            task7.description = task7_description.replace('{grant_id_to_investigate}', current_grant_id)
            task7.description = task7_description.replace('{collected_grant_info_json}', json.dumps(final_investigation_json, ensure_ascii=False, indent=2))
            task7.description = task7_description.replace('{csv_path}', self.grants_list_path)
            task7.description = task7_description.replace('{current_date}', current_date) 
            # ユーザープロファイル情報もコンテキストとして渡す
            # 直近の調査結果と評価結果を最優先でコンテキストに含める
            investigation_context = []

            # 調査タスクの結果をコンテキストに含める（最新の詳細情報）
            if task6 and hasattr(task6, 'output') and task6.output:
                investigation_context.append(task6)
                print("調査タスクの結果をレポート生成のコンテキストに含めました")

            # 評価タスクの結果をコンテキストに含める
            if hasattr(task6_5, 'output') and task6_5.output:
                investigation_context.append(task6_5)
                print("評価タスクの結果をレポート生成のコンテキストに含めました")

            # 全体のコンテキスト（初期タスク結果など）を優先順位を下げて含める
            task7_context = investigation_context + executed_tasks_history

            # 詳細調査JSONを明示的にプロンプトのコンテキストセクションに追加
            if final_investigation_json and isinstance(final_investigation_json, dict):
                json_context = "\n\n**調査された助成金情報:**\n```json\n"
                json_context += json.dumps(final_investigation_json, ensure_ascii=False, indent=2)
                json_context += "\n```\n"
                # 既存の説明にコンテキスト情報を追加
                if task7.description and isinstance(task7.description, str):
                    task7.description += json_context
                print("JSONデータを明示的にレポート生成タスクの説明に追加しました")

            # コンテキストの量を記録（デバッグ用）
            print(f"レポート生成タスクに渡すコンテキスト: {len(task7_context)}件のタスク結果")

            report_result_str = self.execute_task_with_retry(task7, context_tasks=task7_context)
            # レポートタスクは履歴に追加しない（ループの一部ではないため）

            if "タスク実行失敗" in report_result_str:
                print(f"ID '{current_grant_id}' のレポート生成・更新タスク失敗。")
                all_detailed_results.append({"grant_id": current_grant_id, "status": "report_update_failed", "error": report_result_str, "collected_data": final_investigation_json})
            else:
                print(f"ID '{current_grant_id}' の評価・更新完了。")
                # 成功した場合、最終的なレポート内容（JSON含む可能性）を記録
                final_report_data = report_result_str
                try: # 結果からJSONを抽出試行
                     json_match = re.search(r"```json\n(\{.*?\})\n```", report_result_str, re.DOTALL)
                     if json_match:
                          final_report_data = json.loads(json_match.group(1))
                except Exception: pass # パース失敗しても文字列のまま記録
                all_detailed_results.append({"grant_id": current_grant_id, "status": "success", "report": final_report_data, "collected_data_before_report": final_investigation_json})

                # 成功時のみ調査済みリストに追加
                if current_grant_id not in self.investigated_grants:
                     self.investigated_grants.append(current_grant_id)

            investigated_count += 1

            print(f"\n現在の調査済み助成金: {len(self.investigated_grants)}件")
            if self.investigated_grants: print(f"調査済みID: {', '.join(self.investigated_grants)}")
            # 次の調査までの待機
            if investigated_count < max_investigation_grants:
                wait_time = 10
                print(f"\nレート制限回避のため {wait_time} 秒待機します...")
                time.sleep(wait_time)

        # --- ステップ3: 最終結果生成 ---
        print("\nステップ3: 最終結果を生成中...")
        final_csv_path = os.path.join(self.grants_dir, "final_grants.csv")
        investigated_df = pd.DataFrame()
        grants_data_final = []
        try:
            if os.path.exists(self.grants_list_path):
                if active_backup_path: self.restore_grants_csv_if_needed(active_backup_path, self.investigated_grants)
                df = pd.read_csv(self.grants_list_path)
            else: print(f"警告: {self.grants_list_path} が見つかりません。"); df = pd.DataFrame()

            if not df.empty and 'id' in df.columns:
                df['id_str'] = df['id'].astype(str)
                
                # 調査済みデータの取得方法を改善
                # 1. investigated_grantsリストを最優先で使用
                if self.investigated_grants:
                    # セッション状態の調査済みリストを優先
                    print(f"セッション内の調査済みリスト {len(self.investigated_grants)}件を使用")
                    mask_by_list = df['id_str'].isin(self.investigated_grants)
                    investigated_df = df[mask_by_list].copy()
                
                # 2. 調査済みリストが空または取得できなかった場合はCSVの情報を使用
                if investigated_df.empty:
                    print("CSV内の調査済みフラグを確認")
                    # investigated列を確認（様々な形式に対応）
                    if 'investigated' in df.columns:
                        try:
                            # 様々な形式のTrue値に対応（True, 'true', 1, '1'など）
                            mask_investigated = df['investigated'].astype(str).str.lower().isin(['true', '1', 't', 'yes', 'y'])
                            investigated_by_flag = df.loc[mask_investigated, 'id_str'].tolist()
                            print(f"investigatedフラグによる検出: {len(investigated_by_flag)}件")
                            if investigated_by_flag:
                                investigated_df = df[df['id_str'].isin(investigated_by_flag)].copy()
                        except Exception as e: 
                            print(f"investigatedフラグの解析エラー: {str(e)}")
                    
                    # 3. スコア情報による検出
                    if investigated_df.empty and 'completeness_score' in df.columns:
                        try:
                            # スコアが存在する行を検出
                            mask_scored = df['completeness_score'].notna() & (df['completeness_score'] != '')
                            scored_ids = df.loc[mask_scored, 'id_str'].tolist()
                            print(f"completeness_scoreによる検出: {len(scored_ids)}件")
                            if scored_ids:
                                investigated_df = df[df['id_str'].isin(scored_ids)].copy()
                        except Exception as e:
                            print(f"スコア解析エラー: {str(e)}")
                    
                    # 4. 調査日の確認
                    if investigated_df.empty and 'updated_at' in df.columns:
                        try:
                            # 更新日時が存在する行を検出
                            mask_updated = df['updated_at'].notna() & (df['updated_at'] != '')
                            updated_ids = df.loc[mask_updated, 'id_str'].tolist()
                            print(f"updated_atによる検出: {len(updated_ids)}件")
                            if updated_ids:
                                investigated_df = df[df['id_str'].isin(updated_ids)].copy()
                        except Exception as e:
                            print(f"updated_at解析エラー: {str(e)}")
                
                # 5. 調査済み助成金リストが空かどうかの最終確認
                if investigated_df.empty and self.investigated_grants:
                    # 最終手段：強制的に調査済みとしてマーク
                    print("最終手段: 強制的に調査済みとしてマーク")
                    investigated_grants_from_list = [g for g in self.investigated_grants if g in df['id_str'].values]
                    if investigated_grants_from_list:
                        # investigated_grantsリストに含まれる行を取得
                        investigated_df = df[df['id_str'].isin(investigated_grants_from_list)].copy()
                        # 強制的にinvestigatedフラグを設定
                        if 'investigated' not in investigated_df.columns:
                            investigated_df['investigated'] = 1
                        else:
                            investigated_df['investigated'] = 1

            # 調査済み助成金リストの最終処理
            if not investigated_df.empty:
                # updated_at がない場合は追加
                if 'updated_at' not in investigated_df.columns:
                    investigated_df['updated_at'] = self._get_timestamp()
                else:
                    investigated_df['updated_at'] = investigated_df['updated_at'].fillna(self._get_timestamp())
                
                # 必須フィールドを確保
                if 'investigated' not in investigated_df.columns:
                    investigated_df['investigated'] = 1
                
                # 不要なカラムを削除
                if 'id_str' in investigated_df.columns:
                    investigated_df = investigated_df.drop(columns=['id_str'])
                
                # 最終データとして格納
                grants_data_final = investigated_df.to_dict('records')
                
                # CSV保存
                investigated_df.to_csv(final_csv_path, index=False)
                print(f"調査済み/評価済み助成金レポートを保存しました: {final_csv_path} ({len(investigated_df)} 件)")
            else: 
                print(f"調査/評価済みの助成金なし、final_grants.csv は生成されません。")
                
                # デバッグ情報の表示
                if self.investigated_grants:
                    print(f"▶ 注意: セッション内に調査済み助成金リストがあります ({len(self.investigated_grants)}件) が、CSVファイルに反映されていません")
                    print(f"▶ 調査済みID: {self.investigated_grants}")
                    
                    # 緊急対策：final_grants.csvを強制生成
                    if len(self.investigated_grants) > 0 and not df.empty:
                        emergency_df = df[df['id_str'].isin(self.investigated_grants)].copy()
                        if len(emergency_df) > 0:
                            # 必要なフィールドを追加
                            emergency_df['investigated'] = 1
                            if 'updated_at' not in emergency_df.columns:
                                emergency_df['updated_at'] = self._get_timestamp()
                            
                            # ファイル保存
                            if 'id_str' in emergency_df.columns:
                                emergency_df = emergency_df.drop(columns=['id_str'])
                            emergency_df.to_csv(final_csv_path, index=False)
                            grants_data_final = emergency_df.to_dict('records')
                            print(f"▶ 緊急対策: 強制的にfinal_grants.csvを生成しました ({len(emergency_df)}件)")
                
                final_csv_path = None

            final_status = "success"
            error_count = sum(1 for r in all_detailed_results if r['status'] != 'success')
            if error_count > 0:
                final_status = "completed_with_errors"
            elif not all_detailed_results and max_investigation_grants > 0: # 調査が1件も実行されなかった場合
                 final_status = "no_grants_investigated"


            result_data = {
                "status": final_status,
                "message": f"{len(self.investigated_grants)}件の助成金について詳細調査・評価が完了しました（{investigated_count}/{max_investigation_grants}件試行）。",
                "initial_tasks_results": self.initial_task_results,
                "detailed_investigation_results": all_detailed_results,
                "investigated_grants": self.investigated_grants,
                "final_csv_path": final_csv_path
            }
            if grants_data_final: result_data["grants_data"] = grants_data_final
            return result_data

        except Exception as e:
            print(f"最終結果の生成または保存中にエラーが発生: {str(e)}")
            traceback.print_exc()
            return { "status": "error", "message": f"最終結果の生成中にエラーが発生: {str(e)}", "investigated_grants": self.investigated_grants, "detailed_investigation_results": all_detailed_results }


# --- (run_crew, __main__ は変更なし) ---
def run_crew():
    grants_count = os.environ.get("GRANTS_COUNT", "1")
    try:
        grants_to_process_int = int(grants_count)
        if grants_to_process_int <= 0: grants_to_process_int = 1
    except ValueError:
        grants_to_process_int = 1
        print(f"GRANTS_COUNTの値が無効です。デフォルト値 {grants_to_process_int} を使用します。")

    crew = FundingSearchCrew(
        user_profile_path="knowledge/user_preference.txt",
        output_path="result_grants/grants_result.json",
        grants_to_process=grants_to_process_int,
        max_retries=3
    )
    result = crew.kickoff()
    return result

if __name__ == "__main__":
    grants_env = os.environ.get("GRANTS_COUNT", "1")
    os.environ["GRANTS_COUNT"] = grants_env
    print(f"環境変数 GRANTS_COUNT={grants_env} で実行します。")

    result = run_crew()
    print("\n--- 最終結果 ---")
    if isinstance(result, dict):
        print(f"ステータス: {result.get('status')}")
        print(f"メッセージ: {result.get('message')}")
        print(f"調査済み助成金ID ({len(result.get('investigated_grants', []))}件): {', '.join(map(str, result.get('investigated_grants', [])))}")
        print(f"最終CSVパス: {result.get('final_csv_path', 'N/A')}")
        print("\n詳細調査結果サマリー:")
        for res in result.get('detailed_investigation_results', []):
            status_val = res.get('status', 'unknown')
            status_msg = status_val if status_val == 'success' else f"エラー/失敗 ({status_val})"
            result_preview = res.get('report', res.get('error', ''))
            if isinstance(result_preview, dict): # 辞書の場合、一部を表示
                result_preview = json.dumps(result_preview, ensure_ascii=False, indent=2)
            if len(result_preview) > 150: result_preview = result_preview[:150] + "..."
            print(f"  - ID={res.get('grant_id', 'N/A')} -> {status_msg}")
            if result_preview: print(f"    結果/エラープレビュー: {result_preview}")

        if "grants_data" in result and result["grants_data"]:
             print(f"\n最終助成金データ ({len(result['grants_data'])}件): (詳細は {result.get('final_csv_path', 'N/A')} を確認)")
    else:
        print(result)
# --- END OF FILE crew.py ---