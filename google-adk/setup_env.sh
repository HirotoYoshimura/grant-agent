#!/bin/bash
# Grant Search ADK プロジェクトのための環境セットアップスクリプト (uv 使用)

echo "====================================================="
echo " Grant Search ADK 環境セットアップスクリプト"
echo "====================================================="
echo "現在のディレクトリ: $(pwd)"
echo ""

# --- 1. uv のインストール確認 ---
if ! command -v uv &> /dev/null; then
    echo "---------------------------------------------------------------------"
    echo "[エラー] パッケージインストーラ 'uv' が見つかりません。"
    echo "uv をインストールしてください。詳細は以下のURLを参照してください:"
    echo "https://github.com/astral-sh/uv#installation"
    echo ""
    echo "一般的なインストールコマンドの例:"
    echo "  pip install uv"
    echo "  # または macOS (Homebrew) の場合:"
    echo "  # brew install uv"
    echo "  # または pipx の場合:"
    echo "  # pipx install uv"
    echo "  # または Cargo の場合:"
    echo "  # cargo install uv"
    echo "  # 公式のインストールスクリプト:"
    echo "  # curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "---------------------------------------------------------------------"
    exit 1
fi
echo "[情報] uv が見つかりました: $(command -v uv)"
echo ""

# --- 2. pyproject.toml の存在確認 ---
if [ ! -f "pyproject.toml" ]; then
    echo "[エラー] pyproject.toml が見つかりません。"
    echo "このスクリプトはプロジェクトのルートディレクトリで実行してください。"
    exit 1
fi
echo "[情報] pyproject.toml が見つかりました。"
echo ""

# --- 3. Python バージョン確認 (簡易版) ---
# pyproject.toml の requires-python = ">=3.10,<3.13" に合わせる
PYTHON_VERSION_OK=$(python3 -c 'import sys; print(1 if (3, 10) <= sys.version_info < (3, 13) else 0)' 2>/dev/null)
if [ "$PYTHON_VERSION_OK" -eq 0 ]; then
    echo "---------------------------------------------------------------------"
    echo "[警告] 現在の Python バージョンはプロジェクトの推奨範囲外の可能性があります。"
    echo "        プロジェクトは Python >=3.10, <3.13 を推奨しています。"
    echo "        現在のバージョン: $(python3 --version 2>&1)"
    echo "        問題が発生した場合は、推奨バージョンをご利用ください。"
    echo "---------------------------------------------------------------------"
    # 続行は許可する
fi
echo ""

# --- 4. 仮想環境の作成 ---
VENV_DIR=".venv"
echo "[情報] 仮想環境 ($VENV_DIR) を確認/作成しています..."
if ! uv venv "$VENV_DIR" -p python3 &> /dev/null; then # python3 を明示的に指定
    echo "[エラー] 仮想環境の作成に失敗しました。Python 3.10以上が 'python3' として利用可能か確認してください。"
    exit 1
fi
echo "[情報] 仮想環境 ($VENV_DIR) の準備ができました。"
echo ""

# --- 5. 依存関係のインストール ---
echo "[情報] 依存関係をインストールしています (uv.lock を使用)..."
# uv.lock が存在する場合、それに基づいて厳密に同期する
if ! uv sync; then # --strict オプションを削除
    echo "[エラー] 依存関係のインストールに失敗しました。"
    echo "        uv sync コマンドが失敗しました。エラーメッセージを確認してください。"
    exit 1
fi
echo "[情報] 依存関係のインストールが完了しました。"
echo ""

# --- 6. 完了メッセージ ---
echo "====================================================="
echo " 環境セットアップが正常に完了しました！"
echo "====================================================="
echo ""
echo "以下のコマンドでアプリケーションを起動できます:"
echo "  ./run_ui.sh"
echo ""
echo "ブラウザで http://localhost:8501 (または起動時に表示されるポート) にアクセスしてください。"
echo "====================================================="

exit 0