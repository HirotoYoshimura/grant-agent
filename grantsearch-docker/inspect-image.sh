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

# 一時ディレクトリを作成
TEMP_DIR="./image-inspection"
mkdir -p $TEMP_DIR

# アプリケーションディレクトリのファイル一覧をコピー
echo "ファイル構造を抽出しています..."
docker cp $CONTAINER_ID:/app $TEMP_DIR

# 調査後、一時コンテナを削除
docker rm $CONTAINER_ID

# ディレクトリ構造を表示
echo "ファイル構造:"
find $TEMP_DIR -type f -name ".env" -o -name "user_preference.txt" | sort

echo "アプリケーションディレクトリの内容:"
ls -la $TEMP_DIR/app/google-adk

echo "調査完了"
echo "調査結果は $TEMP_DIR ディレクトリに保存されています" 