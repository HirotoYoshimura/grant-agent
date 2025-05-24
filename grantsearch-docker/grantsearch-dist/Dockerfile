FROM python:3.11-slim

WORKDIR /workspace

# 必要なパッケージのインストール
RUN apt-get update && apt-get install -y \
    build-essential \
    lsof \
    && rm -rf /var/lib/apt/lists/*

# アプリケーションディレクトリを作成
RUN mkdir -p /workspace/google-adk

# まずrequirements.txtをコピー
COPY ./app-source/requirements.txt /workspace/google-adk/

# Python依存関係のインストール
WORKDIR /workspace/google-adk
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 残りのアプリケーションファイルをコンテナにコピー
COPY ./app-source /workspace/google-adk/

# 既存の設定ファイルを削除（万が一存在する場合）
RUN rm -f .env user_preference.txt \
    && find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true \
    && find . -name "*.pyc" -type f -delete

# ディレクトリの作成（空の状態で）
RUN mkdir -p /workspace/google-adk/results \
    && mkdir -p /workspace/google-adk/logs \
    && mkdir -p /workspace/google-adk/knowledge \
    && chmod -R 777 /workspace/google-adk/results \
    && chmod -R 777 /workspace/google-adk/logs \
    && chmod -R 777 /workspace/google-adk/knowledge

# PYTHONPATHを設定
ENV PYTHONPATH=/workspace/google-adk

# ポートの公開
EXPOSE 8501

# 実行コマンド（マウントされたボリュームからの設定を使用）
ENTRYPOINT ["bash", "run_ui.sh"] 