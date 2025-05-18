#!/bin/bash
# Docker イメージビルド時のクリーンアップスクリプト
# 機密情報や個人設定ファイルを完全に削除します

echo "イメージクリーンアップを実行しています..."

# 基本的な機密ファイルを削除
find /workspace -name "*.env" -type f -delete
find /workspace -name ".env" -type f -delete
find /workspace -name "user_preference.txt" -type f -delete
find /workspace -name "*.key" -type f -delete
find /workspace -name "api_key*.txt" -type f -delete
find /workspace -name "credentials*.json" -type f -delete

# Google ADKディレクトリをクリーンアップ
if [ -d "/workspace/google-adk" ]; then
  cd /workspace/google-adk
  
  # キャッシュや一時ファイルを削除
  find . -name "__pycache__" -type d -exec rm -rf {} +
  find . -name "*.pyc" -type f -delete
  find . -name ".DS_Store" -type f -delete
  
  # 既存のデータディレクトリをクリア
  rm -rf results/* logs/* knowledge/*
  
  # 権限を設定
  chmod -R 777 results logs knowledge
fi

echo "クリーンアップ完了" 