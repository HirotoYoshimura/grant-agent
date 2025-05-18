#!/bin/bash
# Grant Search 配布用ZIPパッケージ作成スクリプト

DIST_DIR="./grantsearch-dist"
ZIP_NAME="grantsearch-docker.zip"
VERSION=$(date +"%Y%m%d")

echo "====================================================="
echo "Grant Search 配布用パッケージ作成スクリプト"
echo "====================================================="
echo "作成日時: $(date)"
echo "バージョン: $VERSION"
echo

# 古いディストリビューションディレクトリを削除
if [ -d "$DIST_DIR" ]; then
  echo "既存の配布ディレクトリを削除しています..."
  rm -rf "$DIST_DIR"
fi

# 新しいディストリビューションディレクトリを作成
mkdir -p "$DIST_DIR"
mkdir -p "$DIST_DIR/data"

# 必要なファイルをコピー
echo "必要なファイルをコピーしています..."
cp Dockerfile "$DIST_DIR/"
cp docker-compose.yml "$DIST_DIR/"
cp start-grantsearch.sh "$DIST_DIR/"
chmod +x "$DIST_DIR/start-grantsearch.sh"

# データディレクトリのプレースホルダーを作成
mkdir -p "$DIST_DIR/data/results"
mkdir -p "$DIST_DIR/data/logs"
mkdir -p "$DIST_DIR/data/knowledge"
touch "$DIST_DIR/data/.env"

# .envファイルのテンプレートを作成
echo "# APIキー設定 (.envファイル)" > "$DIST_DIR/data/.env"
echo "# Gemini APIキーを設定してください" >> "$DIST_DIR/data/.env"
echo "GOOGLE_API_KEY=" >> "$DIST_DIR/data/.env"

# READMEファイルを作成
echo "READMEファイルを作成しています..."
cat > "$DIST_DIR/README.md" << 'EOF'
# Grant Search Docker

## セットアップ手順

1. このzipファイルを展開します
2. 展開したディレクトリに移動します: `cd grantsearch-dist`
3. APIキーを設定します: `data/.env` ファイルを編集して、あなたのGemini APIキーを設定してください
4. アプリケーションを起動します: `./start-grantsearch.sh`
5. ブラウザで http://localhost:8501 にアクセスしてください

## ファイル構造

- `start-grantsearch.sh` - 起動スクリプト
- `docker-compose.yml` - Dockerコンポーズ設定ファイル
- `data/` - アプリケーションデータディレクトリ
  - `.env` - APIキー設定ファイル
  - `results/` - 結果保存ディレクトリ
  - `logs/` - ログディレクトリ
  - `knowledge/` - ナレッジベースディレクトリ

## 注意事項

- 初回実行時はDockerイメージのダウンロードに時間がかかる場合があります
- APIキーを設定しないとアプリケーションは正常に動作しません
EOF

# ZIPファイルを作成
echo "ZIPファイルを作成しています..."
cd "$DIST_DIR/.." && zip -r "$ZIP_NAME" "$(basename $DIST_DIR)"

if [ $? -eq 0 ]; then
  echo "配布パッケージが正常に作成されました: $(pwd)/$ZIP_NAME"
  echo "サイズ: $(du -h $ZIP_NAME | cut -f1)"
else
  echo "エラー: ZIPファイルの作成に失敗しました。"
  exit 1
fi

echo "処理が完了しました。" 