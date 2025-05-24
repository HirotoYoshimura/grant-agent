# Grant Search Docker

## セットアップ手順

1. このzipファイルを展開します
2. 展開したディレクトリに移動します: `cd grantsearch-dist`
3. APIキーを設定します: `data/.env` ファイルを編集して、あなたのGemini APIキーを設定してください
   ```
   # Gemini APIキー (必須)
   GOOGLE_API_KEY=あなたのAPIキーをここに入力してください
   ```
4. アプリケーションを起動します: `./start-grantsearch.sh`
5. ブラウザで http://localhost:8501 にアクセスしてください

## ファイル構造

- `start-grantsearch.sh` - 起動スクリプト
- `docker-compose.yml` - Dockerコンポーズ設定ファイル
- `data/` - アプリケーションデータディレクトリ
  - `.env` - APIキー設定ファイル (Gemini APIキーのみが必要です)
  - `results/` - 結果保存ディレクトリ
  - `logs/` - ログディレクトリ
  - `knowledge/` - ナレッジベースディレクトリ

## 注意事項

- 初回実行時はDockerイメージのダウンロードに時間がかかる場合があります
- APIキーを設定しないとアプリケーションは正常に動作しません
- Gemini APIキーは [Google AI Studio](https://makersuite.google.com/app/apikey) から取得できます

## 最新の更新内容

- 検索機能が改善され、外部APIを使わなくても動作するようになりました
- APIキー設定が簡素化され、Gemini APIキーのみが必要になりました
- インターフェースが改善され、より使いやすくなりました
