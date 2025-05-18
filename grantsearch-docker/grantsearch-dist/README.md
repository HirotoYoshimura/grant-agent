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
