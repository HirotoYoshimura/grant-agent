#!/bin/bash
# Dockerイメージのビルドとプッシュスクリプト

# スクリプトが置かれているディレクトリに移動
cd "$(dirname "$0")"

IMAGE_NAME="hirotoyo/grantsearch"
TAG="latest"

echo "====================================================="
echo "Dockerイメージのビルドとプッシュスクリプト"
echo "====================================================="
echo "イメージ名: $IMAGE_NAME:$TAG"
echo

# イメージをビルド
echo "Dockerイメージをビルドしています..."
docker build -t $IMAGE_NAME:$TAG .

# ビルドが成功したか確認
if [ $? -ne 0 ]; then
  echo "エラー: Dockerイメージのビルドに失敗しました。"
  exit 1
fi

echo "ビルド完了: $IMAGE_NAME:$TAG"

# Docker Hubにプッシュするか確認
read -p "Docker Hubにイメージをプッシュしますか？ (y/n): " PUSH_CONFIRM

if [[ $PUSH_CONFIRM =~ ^[Yy]$ ]]; then
  echo "Docker Hubにイメージをプッシュしています..."
  docker push $IMAGE_NAME:$TAG
  
  if [ $? -ne 0 ]; then
    echo "エラー: イメージのプッシュに失敗しました。"
    echo "Docker Hubにログインしていることを確認してください。"
    echo "  $ docker login"
    exit 1
  fi
  
  echo "プッシュ完了: $IMAGE_NAME:$TAG"
else
  echo "プッシュはキャンセルされました。"
fi

echo "処理が完了しました。" 