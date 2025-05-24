#!/bin/bash
# Grant Search ADK Streamlit UI 起動スクリプト

# スクリプトのあるディレクトリを取得
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR" || exit 1 # ディレクトリ移動失敗時は終了

echo "====================================================="
echo " Grant Search ADK UI 起動"
echo "====================================================="
echo "作業ディレクトリ: $SCRIPT_DIR"
echo ""

# --- 1. 仮想環境の確認 ---
VENV_DIR=".venv"
PYTHON_EXEC="$SCRIPT_DIR/$VENV_DIR/bin/python"

if [ ! -f "$PYTHON_EXEC" ]; then
    echo "[エラー] 仮想環境内のPython実行ファイル ($PYTHON_EXEC) が見つかりません。"
    echo "        事前に ./setup_env.sh を実行して環境をセットアップしてください。"
    exit 1
fi
echo "[情報] 仮想環境 ($VENV_DIR) のPythonを使って実行します: $PYTHON_EXEC"
echo "       (./setup_env.sh でセットアップ済みであることを前提とします)"
echo ""

# --- 2. 環境変数ファイルの読み込み ---
if [ -f ".env" ]; then
    echo "[情報] .envファイルから環境変数を読み込みます..."
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
else
    echo "[警告] .envファイルが見つかりません。APIキーなどの設定がされているか確認してください。"
fi
echo ""

# --- 3. 必要なディレクトリの作成 ---
echo "[情報] 必要なディレクトリを作成/確認します..."
mkdir -p knowledge
mkdir -p results/grants_data
mkdir -p logs

# ログディレクトリのパーミッション確認と修正 (所有者による書き込み権限があれば十分)
if [ -d "logs" ] && [ ! -w "logs" ]; then
    echo "[情報] logsディレクトリの書き込み権限を修正します..."
    chmod u+w logs # 所有者に書き込み権限を付与
fi
echo ""

# --- 4. PYTHONPATHの設定 ---
export PYTHONPATH="$SCRIPT_DIR:$PYTHONPATH"
echo "[情報] PYTHONPATHを設定しました: $PYTHONPATH"
echo ""

# --- 5. Streamlit アプリケーションの起動 ---
echo "[情報] Streamlit アプリケーションを起動します..."
# PORT 環境変数が設定されていればそれを使用し、なければデフォルトの 8501 を使用
PORT=${PORT:-8501}
echo "       URL: http://localhost:${PORT}"
echo "       (終了するには Ctrl+C を押してください)"
echo ""

# 仮想環境内のPythonを使ってStreamlitを実行
"$PYTHON_EXEC" -m streamlit run streamlit_app.py --server.port "${PORT}" --server.headless true

EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo "[エラー] Streamlit アプリケーションの起動に失敗しました (終了コード: $EXIT_CODE)。"
    echo "        エラーメッセージを確認してください。"
    echo "        仮想環境が正しくセットアップされているか、ポートが使用中でないかなども確認してください。"
fi

exit $EXIT_CODE