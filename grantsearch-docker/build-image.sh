#!/bin/bash
# Dockerイメージをビルドしてプッシュするスクリプト

echo "======================================================================"
echo "             Grant Search Docker イメージビルド"
echo "======================================================================"
echo ""

# イメージ名の設定
IMAGE_NAME="grantsearch"
TAG="clean"

# ビルド
echo "Dockerイメージをビルドしています..."
docker build -t ${IMAGE_NAME}:${TAG} -f Dockerfile .

echo ""
echo "ビルド完了しました！"
echo "イメージ名: ${IMAGE_NAME}:${TAG}"
echo ""

# docker-compose.ymlの更新
echo "docker-compose.ymlを更新しています..."
sed -i '' "s|image:.*|image: ${IMAGE_NAME}:${TAG}|g" docker-compose.yml

echo ""
echo "テスト実行する場合は ./start-grantsearch.sh を実行してください"
echo ""

# プッシュするかどうかの確認
echo "DockerHubにプッシュしますか？ [y/N]"
read -r confirm

if [[ "$confirm" =~ ^[Yy]$ ]]; then
  echo "DockerHubのユーザー名を入力してください:"
  read -r username
  
  echo "イメージにタグ付けしています..."
  docker tag ${IMAGE_NAME}:${TAG} ${username}/${IMAGE_NAME}:${TAG}
  
  echo "DockerHubにログインします..."
  docker login
  
  echo "イメージをプッシュしています..."
  docker push ${username}/${IMAGE_NAME}:${TAG}
  
  echo "プッシュ完了！DockerHubで確認できます"
  echo "イメージ名: ${username}/${IMAGE_NAME}:${TAG}"
  
  # docker-compose.ymlの更新
  echo "docker-compose.ymlを更新しています..."
  sed -i '' "s|image:.*|image: ${username}/${IMAGE_NAME}:${TAG}|g" docker-compose.yml
else
  echo "プッシュをスキップしました。ローカルイメージを使用します。"
fi

echo ""
echo "すべての処理が完了しました！" 