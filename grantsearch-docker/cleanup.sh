#!/bin/bash
# クリーンアップスクリプト - APIキーや個人情報を削除

# クローンされたリポジトリに移動
cd /workspace/google-adk

# .envファイルがあれば削除
if [ -f ".env" ]; then
  rm -f .env
  echo "APIキー設定(.env)を削除しました"
fi

# user_preference.txtがあれば削除
if [ -f "user_preference.txt" ]; then
  rm -f user_preference.txt
  echo "ユーザープロファイル設定を削除しました"
fi

# もし存在するなら、APIキーが保存されているかもしれない他のファイルを削除
find . -name "*.key" -type f -delete
find . -name "api_key*.txt" -type f -delete
find . -name "credentials*.json" -type f -delete

# デフォルトの.envテンプレートを作成
echo "# APIキー設定" > .env.template
echo "GOOGLE_API_KEY=" >> .env.template

echo "すべての機密情報をクリーンアップしました" 