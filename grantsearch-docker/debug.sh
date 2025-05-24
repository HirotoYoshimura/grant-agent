#!/bin/bash
# Grant Search デバッグスクリプト

echo "======================================================================"
echo "             Grant Search デバッグツール"
echo "======================================================================"
echo ""

# Dockerコンテナに入って内部パスを確認
echo "コンテナ内のパス構造を確認します..."
docker run --rm -it hirotoyo/grantsearch:latest /bin/bash -c '
echo "コンテナ内部の情報:";
echo "----------------------------------------";
echo "カレントディレクトリ: $(pwd)";
echo "----------------------------------------";
echo "/app ディレクトリの内容:";
if [ -d "/app" ]; then
  ls -la /app;
  if [ -d "/app/google-adk" ]; then
    echo "/app/google-adk ディレクトリの内容:";
    ls -la /app/google-adk;
  else
    echo "/app/google-adk ディレクトリは存在しません";
  fi
else
  echo "/app ディレクトリは存在しません";
fi
echo "----------------------------------------";
echo "/workspace ディレクトリの内容:";
if [ -d "/workspace" ]; then
  ls -la /workspace;
  if [ -d "/workspace/google-adk" ]; then
    echo "/workspace/google-adk ディレクトリの内容:";
    ls -la /workspace/google-adk;
  else
    echo "/workspace/google-adk ディレクトリは存在しません";
  fi
else
  echo "/workspace ディレクトリは存在しません";
fi
echo "----------------------------------------";
'

echo ""
echo "ローカルデータディレクトリの確認:"
ls -la ./data 