#!/bin/bash
# クリーンなDockerイメージを再ビルドするスクリプト

IMAGE_NAME="hirotoyo/grantsearch"
TAG="latest"

echo "====================================================="
echo "Grant Search クリーンビルドスクリプト"
echo "====================================================="
echo "イメージ名: $IMAGE_NAME:$TAG"
echo

# 既にアプリケーションが抽出されているか確認
if [ ! -d "./app-source" ]; then
  echo "アプリケーションソースが見つかりません。抽出を実行します..."
  chmod +x ./extract-app.sh && ./extract-app.sh
fi

# 抽出したソースから機密情報を削除
echo "抽出したソースから機密情報を削除しています..."
rm -f ./app-source/.env ./app-source/user_preference.txt
rm -rf ./app-source/results/* ./app-source/logs/* ./app-source/knowledge/*

# 依存関係を確認
echo "Pythonの依存関係を確認しています..."
if [ -f "./app-source/requirements.txt" ]; then
  echo "requirements.txtが見つかりました。依存関係を確認します..."
  if ! grep -q "pyyaml" ./app-source/requirements.txt; then
    echo "※注意: requirements.txtにpyyamlが含まれていません。"
    echo "  Dockerfileに直接追加されていることを確認してください。"
  fi
else
  echo "※警告: requirements.txtが見つかりませんでした。"
  echo "  Dockerfileに必要な依存関係が全て含まれていることを確認してください。"
fi

# 新しいイメージをビルド
echo "クリーンなDockerイメージをビルドしています..."
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