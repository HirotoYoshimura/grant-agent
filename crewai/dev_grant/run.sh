#!/bin/bash

# FundingSearchCrew Streamlitアプリ起動スクリプト

# crewaiの仮想環境を特定して使用
CREWAI_VENV=".venv"

if [ ! -d "$CREWAI_VENV" ]; then
    echo "crewaiの仮想環境($CREWAI_VENV)が見つかりません。"
    echo "別の仮想環境を探します..."
    
    # 代替の仮想環境を探す
    ALTERNATIVE_PATHS=(
        "/workspace/crewai/.venv"
        "../.venv"
        "../../.venv"
        ".venv"
    )
    
    for alt_path in "${ALTERNATIVE_PATHS[@]}"; do
        if [ -d "$alt_path" ]; then
            CREWAI_VENV="$alt_path"
            echo "代替の仮想環境を見つけました: $CREWAI_VENV"
            break
        fi
    done
    
    # 仮想環境が見つからない場合は新規に作成
    if [ ! -d "$CREWAI_VENV" ]; then
        echo "使用可能な仮想環境が見つかりませんでした。新しい仮想環境を作成します。"
        CREWAI_VENV=".venv"
        uv sync
    fi
fi

# 仮想環境をアクティブにする
echo "仮想環境をアクティブにします: $CREWAI_VENV"
source "$CREWAI_VENV/bin/activate"

# 必要なパッケージがインストールされているか確認
# echo "必要なパッケージをインストールします..."

# StreamlitとCrewAIが必要
#pip install -q streamlit crewai

# # requirements.txtがあれば、そこから追加の依存関係をインストール
# if [ -f "requirements.txt" ]; then
#     pip install -q -r requirements.txt
# fi

# Playwright依存関係を確認
# if ! python -c "import playwright" &> /dev/null; then
#     echo "Playwrightをインストールします..."
#     pip install -q playwright
#     playwright install chromium
#     playwright install-deps chromium
#     echo "Playwrightのインストールが完了しました。"
# fi

# 環境変数を.envから読み込む
if [ -f .env ]; then
    echo ".envから環境変数を読み込みます"
    export $(grep -v '^#' .env | xargs)
fi

# パスを環境変数として設定（pyproject.tomlのエラー対策）
export PYTHONPATH=$PYTHONPATH:$(pwd)
export PROJECT_ROOT=$(pwd)
export CREWAI_DISABLE_TELEMETRY=true
export OTEL_SDK_DISABLED=true

# Streamlitアプリを起動
echo "Streamlitアプリを起動します..."
streamlit run streamlit_app.py