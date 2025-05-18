#!/bin/bash
# Grant Search 起動スクリプト

# 必要なディレクトリを作成
mkdir -p ./data/results
mkdir -p ./data/logs
mkdir -p ./data/knowledge
touch ./data/.env

# 環境変数ファイルが空の場合、テンプレートを作成
if [ ! -s ./data/.env ]; then
  echo "# APIキー設定 (.envファイル)" > ./data/.env
  echo "# Gemini APIキーを設定してください" >> ./data/.env
  echo "GOOGLE_API_KEY=" >> ./data/.env
fi

# Docker イメージを最新にアップデート
echo "Dockerイメージを最新版に更新しています..."
docker pull hirotoyo/grantsearch:latest

# Dockerコンテナを起動
echo "Grant Search を起動しています..."
echo "ブラウザで http://localhost:8501 にアクセスしてください"
docker compose up 