#!/usr/bin/env python3
"""grantsearch CLI

非技術ユーザーでも「grantsearch」コマンド 1 つで Streamlit UI を起動できるようにするためのラッパースクリプト。
・初回実行時に仮想環境と依存関係を自動セットアップ
・既に UI が起動中のときは再起動を防止し、URL を表示して終了
・起動失敗時はエラーコードをそのまま返し、自動リトライはしない（無限増殖防止）
"""
from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path
import socket

PROJECT_DIR = Path(__file__).resolve().parent
VENV_DIR = PROJECT_DIR / ".venv"
RUN_SCRIPT = PROJECT_DIR / "run_ui.sh"
DEFAULT_PORT = int(os.getenv("PORT", "8501"))


def ensure_venv() -> None:
    """仮想環境と依存パッケージを準備する。

    ・.venv ディレクトリが存在しなければ python -m venv で作成
    ・pip が古い場合はアップグレード
    ・pyproject.toml / requirements.txt があればインストール
    """
    if VENV_DIR.exists():
        return  # 既に存在

    print("[grantsearch] 初回セットアップ: 仮想環境を作成します…")
    venv.create(VENV_DIR, with_pip=True, clear=False, symlinks=True, system_site_packages=False)

    # venv 内の pip
    pip_path = VENV_DIR / "bin" / "pip"
    python_path = VENV_DIR / "bin" / "python"

    # pip をアップグレード
    subprocess.run([str(pip_path), "install", "--upgrade", "pip"], check=True)

    # 依存関係インストール: pyproject.toml 優先, なければ requirements.txt
    if (PROJECT_DIR / "requirements.txt").exists():
        subprocess.run([str(pip_path), "install", "-r", str(PROJECT_DIR / "requirements.txt")], check=True)
    elif (PROJECT_DIR / "pyproject.toml").exists():
        # fallback: editable install。構造上ハイフン入りパスがあると失敗する可能性があるため注意
        subprocess.run([str(pip_path), "install", ".", "--config-settings=--editable"], check=True)

    print("[grantsearch] セットアップ完了")


def is_port_in_use(port: int) -> bool:
    """指定ポートが LISTEN 状態かを確認"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:  # noqa: C901
    # 重複起動チェック
    if is_port_in_use(DEFAULT_PORT):
        url = f"http://localhost:{DEFAULT_PORT}"
        print(f"Grant Search UI はすでに起動しています → {url}")
        sys.exit(0)

    # 仮想環境準備
    ensure_venv()

    # venv の python を使用して run_ui.sh を実行
    # run_ui.sh 内で再度 .venv をアクティベートするため、ここでは system python で実行しても問題ないが
    # 実行権限が無い場合に備え chmod
    RUN_SCRIPT.chmod(RUN_SCRIPT.stat().st_mode | 0o111)

    print("[grantsearch] Streamlit UI を起動します…")
    try:
        subprocess.run(["bash", str(RUN_SCRIPT)], check=True)
    except subprocess.CalledProcessError as exc:
        print("[grantsearch] UI の起動に失敗しました (自動再起動は行いません)\n", file=sys.stderr)
        sys.exit(exc.returncode)


if __name__ == "__main__":
    main() 