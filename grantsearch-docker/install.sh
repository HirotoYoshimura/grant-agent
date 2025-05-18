#!/bin/bash
# Grant Search Docker インストーラー

echo "======================================================================"
echo "             Grant Search Docker インストーラー"
echo "======================================================================"
echo ""
echo "このスクリプトは必要なファイルを展開し、実行準備を行います。"
echo ""

# 必要なディレクトリを作成
echo "データディレクトリを作成しています..."
mkdir -p ./data/results
mkdir -p ./data/logs
mkdir -p ./data/knowledge
touch ./data/.env

# 権限を設定
echo "ディレクトリの権限を設定しています..."
chmod -R 777 ./data

# 実行権限を付与
chmod +x start-grantsearch.sh
chmod +x debug.sh

echo "インストールが完了しました！"
echo ""
echo "作成されたディレクトリ構造:"
ls -la ./data/
echo ""
echo "使用方法："
echo "1. ./start-grantsearch.sh コマンドでアプリケーションを起動"
echo "2. ブラウザで http://localhost:8501 にアクセス"
echo ""
echo "詳細は README.md ファイルをご覧ください。"
echo ""
echo "今すぐアプリケーションを起動しますか？ [y/N]"
read -r confirm

if [[ "$confirm" =~ ^[Yy]$ ]]; then
  ./start-grantsearch.sh
else
  echo "後で ./start-grantsearch.sh を実行して起動してください。"
fi 