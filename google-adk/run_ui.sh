#!/bin/bash
# Grant Search ADK Streamlit UI 起動スクリプト

# スクリプトのあるディレクトリを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 環境変数ファイルを読み込み（存在する場合）
if [ -f ".env" ]; then
    echo ".envファイルから環境変数を読み込みます"
    set -a
    source .env
    set +a
fi

# 仮想環境の存在確認と有効化
VENV_PATH="$SCRIPT_DIR/.venv"
if [ -d "$VENV_PATH" ]; then
    echo "仮想環境をアクティベートします: $VENV_PATH"
    source "$VENV_PATH/bin/activate"
fi

# 必要なディレクトリの作成
mkdir -p knowledge
mkdir -p results/grants_data
mkdir -p logs

# ログディレクトリのパーミッション確認と修正
if [ ! -w "logs" ]; then
    echo "logsディレクトリの書き込み権限を設定します"
    chmod 755 logs
fi

# PYTHONPATHの設定
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"

# ホスト側 IP を自動取得して環境変数に
if ip route | grep -q "default via 172.17.0.1"; then
  export OLLAMA_API_BASE="http://172.17.0.1:11434"
fi

# Ollama が動いていなければ自動で起動
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "Starting local Ollama server..."
  nohup ollama serve > logs/ollama.log 2>&1 &
  sleep 2
fi

# Streamlitアプリの起動（より頻繁な更新とキャッシュなしで実行）
echo "Streamlitアプリを起動します..."
streamlit run --server.runOnSave=true --server.maxUploadSize=50 --client.showErrorDetails=true streamlit_app.py "$@"