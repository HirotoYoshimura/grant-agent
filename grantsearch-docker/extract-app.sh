#!/bin/bash
# 既存のDockerイメージからアプリケーションファイルを抽出するスクリプト

IMAGE_NAME="hirotoyo/grantsearch:latest"
APP_DIR="./app-source"

echo "================================================="
echo "アプリケーションファイル抽出スクリプト"
echo "================================================="
echo "対象イメージ: $IMAGE_NAME"
echo "出力先: $APP_DIR"
echo

# イメージをプル
echo "イメージをプルしています..."
docker pull $IMAGE_NAME

# 古い抽出ディレクトリがあれば削除
if [ -d "$APP_DIR" ]; then
  echo "既存の抽出ディレクトリを削除しています..."
  rm -rf "$APP_DIR"
fi

# 抽出先ディレクトリを作成
mkdir -p "$APP_DIR"

# コンテナを一時的に作成
echo "一時コンテナを作成しています..."
CONTAINER_ID=$(docker create $IMAGE_NAME)

# アプリケーションファイルをコピー
echo "アプリケーションファイルをコピーしています..."
docker cp $CONTAINER_ID:/workspace/google-adk/. "$APP_DIR/"

# 不要なファイルを削除
echo "不要なファイルを削除しています..."
rm -f "$APP_DIR/.env" "$APP_DIR/user_preference.txt"
rm -rf "$APP_DIR/results" "$APP_DIR/logs" "$APP_DIR/knowledge"

# 一時コンテナを削除
docker rm $CONTAINER_ID

echo "抽出完了しました。"
echo "次のステップ:"
echo "1. $APP_DIR ディレクトリに必要なファイルが抽出されています"
echo "2. 新しいDockerfileではこれらのファイルを使用してください"
echo "3. 機密情報が含まれていないか確認してください" 