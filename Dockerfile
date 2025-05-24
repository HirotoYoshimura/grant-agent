#############################################
# Grant Search ADK – Docker イメージ
#
#   $ docker build -t grantsearch:latest .
#   $ docker run -p 8501:8501 grantsearch:latest
#
# イメージ内で直接 python パッケージをインストールするため、
# ランタイムで .venv は使用しません。
#############################################

FROM python:3.11-slim AS base

# lsof は run_ui.sh の重複起動チェックで必要
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        lsof && \
    rm -rf /var/lib/apt/lists/*

#========== アプリケーション層 ==========
WORKDIR /app

# ソースをコピー
COPY . /app

# 依存インストール（pyproject.toml 内の deps）
# google-adk ディレクトリを editable で入れておくとライブデバッグも容易
RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt

#========== 実行 ==========
EXPOSE 8501

WORKDIR /app/google-adk
ENTRYPOINT ["bash", "run_ui.sh"]
