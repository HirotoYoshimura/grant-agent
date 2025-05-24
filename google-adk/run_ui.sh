#!/bin/bash
# Grant Search ADK Streamlit UI 起動スクリプト

# スクリプトのあるディレクトリを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# ================================ 追加入力: 重複起動防止 ================================
# デフォルトポート (環境変数 PORT が設定されていればそれを利用)
PORT=${PORT:-8501}
# 既にポートが LISTEN されているか確認
if lsof -i:"${PORT}" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "Grant Search UI はすでにポート ${PORT} で起動しています。二重起動を防止するためスクリプトを終了します。"
  exit 0
fi
# ====================================================================================

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

# Streamlitアプリの起動（より頻繁な更新とキャッシュなしで実行）
echo "Streamlitアプリを起動します..."
streamlit run --server.runOnSave=true --server.maxUploadSize=50 --client.showErrorDetails=true streamlit_app.py "$@"