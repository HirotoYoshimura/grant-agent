# Grant Search - Docker版

## 概要

研究者向け助成金検索支援AIエージェントのDockerコンテナ版です。
このツールは、研究者のプロファイルを分析し、適切な研究助成金を見つけるのを支援します。

## インストール方法

### 1. ファイルの展開

1. ダウンロードした `grantsearch-docker.zip` を任意のディレクトリに展開してください
2. 展開したディレクトリに移動します

### 2. セットアップ

ターミナルで以下のコマンドを実行して、セットアップを開始します：

```bash
./install.sh
```

## 前提条件

以下のソフトウェアがインストールされている必要があります：

### Docker
- macOS/Windows: [Docker Desktop](https://www.docker.com/products/docker-desktop/)をインストールしてください（Docker Composeは自動的に含まれます）
- Linux: 
  1. [Docker Engine](https://docs.docker.com/engine/install/)をインストール
  2. [Docker Compose](https://docs.docker.com/compose/install/)を別途インストール

### 動作確認方法
以下のコマンドでDockerとDocker Composeが正しくインストールされているか確認できます：

```bash
docker --version
docker compose version
```

## インストールと実行方法

### 1. ファイルの準備

配布されたファイルを任意のディレクトリに配置してください：
- `docker-compose.yml`
- `start-grantsearch.sh`
- `README.md` (このファイル)

### 2. 実行権限の付与

ターミナルで以下のコマンドを実行して、起動スクリプトに実行権限を付与します：

```bash
chmod +x start-grantsearch.sh
```

### 3. アプリケーションの起動

以下のコマンドでアプリケーションを起動します：

```bash
./start-grantsearch.sh
```

起動後、ブラウザで以下のURLにアクセスしてください：
http://localhost:8501

### 4. API設定

初回起動時は以下の設定が必要です：

1. サイドバーの「API設定」をクリックします
2. Google AI Studioから取得したGemini APIキーを入力します  
   https://makersuite.google.com/app/apikey
3. 「設定を保存」ボタンをクリックします

## データの永続化

アプリケーションのデータは `./data` ディレクトリに保存されます：

- `./data/results`: 検索結果
- `./data/logs`: 実行ログ
- `./data/knowledge`: ユーザープロファイル
- `./data/.env`: API設定

これらのデータはDockerコンテナを停止・再起動しても保持されます。

## アプリケーションの停止方法

ターミナルで `Ctrl+C` を押すと、アプリケーションが停止します。

## トラブルシューティング

### API設定の問題

- **Gemini APIキーエラー**: API設定ページで正しいGemini APIキーを入力しているか確認してください
- **"500 エラー"**: APIキーのレート制限に達している可能性があります。しばらく待つか、より小型のモデルを使用してください
- **"503 エラー"**: サーバーが過負荷状態です。数分待ってから再度お試しください

### その他の問題

- **コンテナが起動しない**: Docker と Docker Compose が正しくインストールされているか確認してください
- **UIが応答しない**: アプリケーションを再起動してください
- **「ポートが既に使用されています」エラー**: 他のアプリケーションが8501ポートを使用している可能性があります。`docker-compose.yml`ファイルを編集して別のポートを指定してください 