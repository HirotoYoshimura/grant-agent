#!/bin/bash
# Grant Search ADK プロジェクトのための環境セットアップスクリプト (pyproject.toml使用)

echo "Grant Search ADK 環境セットアップスクリプト"
echo "現在のディレクトリ: $(pwd)"

# uvがインストールされているか確認
if ! command -v uv &> /dev/null; then
    echo "uvがインストールされていません。インストールします..."
    pip install uv
fi

# pyproject.tomlが存在するか確認
if [ ! -f "pyproject.toml" ]; then
    echo "エラー: pyproject.tomlが見つかりません。"
    echo "正しいディレクトリにいることを確認してください。"
    exit 1
fi

# 仮想環境の作成（必要な場合）
if [ ! -d ".venv" ]; then
    echo "仮想環境を作成しています..."
    uv sync
fi

# 仮想環境をアクティベート
source .venv/bin/activate

# ロックファイルの作成（または更新）
echo "環境セットアップが完了しました！"
echo "- 仮想環境: .venv"
echo "- ロックファイル: uv.lock"
echo ""
echo "Streamlit UIを起動するには:"
echo "  ./run_ui.sh"