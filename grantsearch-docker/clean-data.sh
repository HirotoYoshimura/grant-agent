#!/bin/bash
# イメージ内のデータをクリーンアップし、マウントしたデータを使用するスクリプト

# デフォルトの.envファイルを削除（あれば）
if [ -f "/app/google-adk/.env" ]; then
  echo "イメージ内の.envファイルを削除しています..."
  rm -f /app/google-adk/.env
fi

# デフォルトのプロファイルファイルを削除（あれば）
if [ -f "/app/google-adk/knowledge/user_preference.txt" ]; then
  echo "イメージ内のプロファイルファイルを削除しています..."
  rm -f /app/google-adk/knowledge/user_preference.txt
fi

echo "クリーンアップ完了。マウントされたデータのみが使用されます。"

# 元のコマンドを実行
exec bash run_ui.sh 