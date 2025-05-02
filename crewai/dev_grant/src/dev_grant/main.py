import os
import argparse
import logging
from typing import Dict, Any
from datetime import datetime
from pathlib import Path

from dev_grant.crew import FundingSearchCrew
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_environment():
    """環境変数が正しく設定されているか確認します。"""
    required_vars = ["GOOGLE_API_KEY", "GOOGLE_CSE_ID", "GOOGLE_GENAI_API_KEY"]
    missing_vars = [var for var in required_vars if not os.environ.get(var)]
    
    if missing_vars:
        raise ValueError(f"次の必須環境変数が設定されていません: {', '.join(missing_vars)}\n"
                         f"GOOGLE_API_KEY, GOOGLE_CSE_ID, GOOGLE_GENAI_API_KEYを設定してください。")

def get_project_root():
    """プロジェクトのルートディレクトリを特定する"""
    # 方法1: スクリプトの場所から判断
    script_path = Path(__file__).resolve()
    
    # src/dev_grant/main.py の場合は2階層上がルート
    if script_path.parent.name == "dev_grant" and script_path.parent.parent.name == "src":
        return script_path.parent.parent.parent
    
    # dev_grant/main.py の場合は1階層上がルート
    if script_path.parent.name == "dev_grant":
        return script_path.parent.parent
        
    # 方法2: 環境変数から判断
    if "PROJECT_ROOT" in os.environ:
        project_root = Path(os.environ["PROJECT_ROOT"])
        if project_root.exists():
            return project_root
    
    # 方法3: カレントディレクトリ関連
    cwd = Path.cwd().resolve()
    
    # カレントディレクトリがsrcまたはdev_grantの場合
    if cwd.name == "src":
        return cwd.parent
    if cwd.name == "dev_grant":
        if cwd.parent.name == "src":
            return cwd.parent.parent
        return cwd.parent
    
    # 方法4: ルートディレクトリのマーカーを探す
    current = cwd
    for _ in range(5):  # 最大5階層まで遡る
        # ルートディレクトリの特徴があるか確認
        if (current / "crew.py").exists() or (current / "run.sh").exists():
            return current
        
        # 親ディレクトリに移動
        parent = current.parent
        if parent == current:  # ルートディレクトリに達した
            break
        current = parent
    
    # デフォルトはカレントディレクトリの親
    return cwd.parent

def run():
    """
    助成金検索を実行します。
    
    Args:
        profile_path: ユーザープロファイルファイルへのパス
        output_path: 結果の出力パス
        
    Returns:
        助成金検索の結果
    """
    try:
        # 環境変数をチェック
        # check_environment()
        
        # プロジェクトルートディレクトリを特定
        base_dir = get_project_root()
        logger.info(f"プロジェクトルートディレクトリ: {base_dir}")
        
        # 相対パスを使用してパスを構築
        knowledge_dir = base_dir / "knowledge"
        results_dir = base_dir / "result_grants"
        
        # プロファイルパスと出力パスの設定
        profile_path = knowledge_dir / "user_preference.txt"
        output_path = results_dir / "grants_result.json"
        
        # ディレクトリの存在を確認して作成
        os.makedirs(knowledge_dir, exist_ok=True)
        os.makedirs(results_dir, exist_ok=True)
        
        # 空のプロファイルファイルが存在することを確認（必要に応じて）
        if not os.path.exists(profile_path):
            logger.info(f"プロファイルファイルが存在しないため、初期ファイルを作成します: {profile_path}")
            with open(profile_path, 'w', encoding='utf-8') as f:
                f.write("# 初期プロファイル\n")

        inputs = {
            "current_date": datetime.now().strftime("%Y-%m-%d")
        }

        # パスをログに出力（デバッグ用）
        logger.info(f"Using profile path: {profile_path}")
        logger.info(f"Using output path: {output_path}")

        # クルーを作成して実行
        crew_instance = FundingSearchCrew(
            user_profile_path=str(profile_path),  # Pathオブジェクトを文字列に変換
            output_path=str(output_path),        # Pathオブジェクトを文字列に変換
            grants_to_process=1,
            max_retries=3  # エラー時のリトライ回数
        )
        
        # クルーを実行
        result = crew_instance.kickoff(inputs=inputs)
        
        logger.info(f"助成金検索が完了し、結果が{output_path}に保存されました")
        return result
    except Exception as e:
        logger.error(f"助成金検索の実行エラー: {str(e)}")
        raise


# コマンドライン引数のパース
def parse_args():
    """コマンドライン引数を解析する関数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='助成金検索を実行')
    parser.add_argument('--profile', '-p', type=str, 
                        help='ユーザープロファイルのパス（指定しない場合はデフォルトパスを使用）')
    parser.add_argument('--output', '-o', type=str,
                        help='出力ファイルのパス（指定しない場合はデフォルトパスを使用）')
    parser.add_argument('--grants', '-g', type=int, default=1,
                        help='検索する助成金の数（デフォルト: 1）')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='デバッグモードを有効にする')
    
    args = parser.parse_args()
    
    # プロファイルパスが指定されている場合のみ存在チェック
    if args.profile and not os.path.exists(args.profile):
        parser.error(f"指定されたプロファイルファイルが存在しません: {args.profile}")
    
    # 出力パスが指定されている場合のみディレクトリ作成
    if args.output:
        output_dir = os.path.dirname(args.output)
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)
            print(f"出力ディレクトリを作成しました: {output_dir}")
    
    return args


# メイン実行部分
if __name__ == "__main__":
    args = parse_args()
    
    # デバッグモードの設定
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
        logging.debug("デバッグモードが有効になりました")
    
    try:
        # 引数に基づいて実行
        if args.profile and args.output:
            # 引数で指定されたカスタムパスを使用
            print(f"ユーザープロファイル: {args.profile}")
            print(f"出力ファイル: {args.output}")
            print(f"検索する助成金数: {args.grants}")
            
            # カスタム実行
            from dev_grant.crew import FundingSearchCrew
            
            crew_instance = FundingSearchCrew(
                user_profile_path=args.profile,
                output_path=args.output,
                grants_to_process=args.grants,
                max_retries=3
            )
            
            result = crew_instance.kickoff()
        else:
            # デフォルト実行 - run()関数を使用
            result = run()
        
        print(f"助成金検索が完了しました")
        print(f"結果: {result}")
        
    except Exception as e:
        import traceback
        print(f"エラーが発生しました: {str(e)}")
        traceback.print_exc()
        
        # エラーコードで終了
        import sys
        sys.exit(1)