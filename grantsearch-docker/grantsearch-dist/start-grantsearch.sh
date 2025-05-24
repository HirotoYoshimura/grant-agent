#!/bin/bash
# Grant Search 起動スクリプト

echo "=========================================="
echo "Grant Search 起動スクリプト"
echo "=========================================="

# 必要なディレクトリを作成
echo "データディレクトリを作成しています..."
mkdir -p ./data/results
mkdir -p ./data/logs
mkdir -p ./data/knowledge

# 権限を設定
echo "ディレクトリの権限を設定しています..."
chmod -R 777 ./data

# 環境変数ファイルが存在しない場合、テンプレートを作成
if [ ! -f ./data/.env ]; then
  echo "環境変数ファイルを作成しています..."
  echo "# Gemini APIキー (必須)" > ./data/.env
  echo "GOOGLE_API_KEY=" >> ./data/.env
  echo ""
  echo "※注意: APIキーを設定する前に Grant Search は機能しません"
  echo "data/.env ファイルを編集して、あなたの API キーを追加してください"
  echo "APIキーは https://makersuite.google.com/app/apikey から取得できます"
fi

# 作成されたディレクトリの確認
echo "作成されたディレクトリ構造:"
ls -la ./data/

# Docker イメージを最新にアップデート
echo "Dockerイメージを最新版に更新しています..."
docker pull hirotoyo/grantsearch:latest

# Dockerコンテナを起動
echo "Grant Search を起動しています..."
echo "ブラウザで http://localhost:8501 にアクセスしてください"
docker compose up 