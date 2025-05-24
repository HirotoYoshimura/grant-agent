#!/bin/bash
# 既存のGrant Search Dockerイメージを調査するスクリプト

IMAGE_NAME="hirotoyo/grantsearch:latest"

echo "================================================="
echo "Grant Search Dockerイメージ調査スクリプト"
echo "================================================="
echo "イメージ: $IMAGE_NAME"
echo

# イメージをプル
echo "イメージをプルしています..."
docker pull $IMAGE_NAME

# イメージの履歴を確認
echo "イメージの構築履歴:"
docker history $IMAGE_NAME

# 一時コンテナを作成
echo "イメージの内部構造を調査しています..."
CONTAINER_ID=$(docker create $IMAGE_NAME)

# 一時コンテナを起動して内部を調査
echo "コンテナを起動して内部を調査しています..."
docker start $CONTAINER_ID

# 機密ファイルの有無を確認
echo "================================================="
echo "機密ファイルのチェック:"
echo "================================================="
echo "1. .envファイルを検索..."
docker exec $CONTAINER_ID find /workspace -name ".env" -type f

echo "2. user_preference.txtファイルを検索..."
docker exec $CONTAINER_ID find /workspace -name "user_preference.txt" -type f

echo "3. credentialsファイルを検索..."
docker exec $CONTAINER_ID find /workspace -name "credentials*.json" -type f -o -name "*.key" -type f

echo "4. /workspace/google-adk ディレクトリの内容:"
docker exec $CONTAINER_ID ls -la /workspace/google-adk

# 調査後、一時コンテナを停止して削除
docker stop $CONTAINER_ID
docker rm $CONTAINER_ID

echo "調査完了" 