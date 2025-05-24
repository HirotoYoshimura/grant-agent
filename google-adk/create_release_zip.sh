#!/bin/bash

# 配布用ZIPアーカイブ作成スクリプト

# --- 設定 ---
APP_NAME="grant_search_adk"
# バージョン番号は手動で設定するか、gitのタグなどから取得する (例: VERSION=$(git describe --tags --abbrev=0 2>/dev/null || echo "dev"))
VERSION="0.5.0" # pyproject.toml のバージョンと合わせるのが望ましい
RELEASE_DIR_NAME="${APP_NAME}-v${VERSION}"
ZIP_FILE_NAME="${RELEASE_DIR_NAME}.zip"
BUILD_DIR="_build_temp" # 一時的な作業ディレクトリ

# --- 事前クリーンアップ ---
echo "[情報] 古い配布物と一時ディレクトリを削除しています..."
rm -f "${ZIP_FILE_NAME}"
rm -rf "${BUILD_DIR}"
echo ""

# --- 配布用ディレクトリの作成 ---
echo "[情報] 配布用ディレクトリ (${BUILD_DIR}/${RELEASE_DIR_NAME}) を作成しています..."
mkdir -p "${BUILD_DIR}/${RELEASE_DIR_NAME}"
echo ""

# --- 必要なファイルをコピー ---
echo "[情報] 必要なファイルを配布用ディレクトリにコピーしています..."
# 個별ファイルを指定
cp pyproject.toml "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp uv.lock "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp README.md "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp setup_env.sh "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp run_ui.sh "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp streamlit_app.py "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp create_user_preference.py "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp grantsearch_cli.py "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp log_handler.py "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp main.py "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp main_adapter_ui.py "${BUILD_DIR}/${RELEASE_DIR_NAME}/"

# ディレクトリをコピー
cp -r agents "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp -r config "${BUILD_DIR}/${RELEASE_DIR_NAME}/"
cp -r tools "${BUILD_DIR}/${RELEASE_DIR_NAME}/"

# knowledge ディレクトリは空の状態で作成 (または初期ファイルを含める)
mkdir -p "${BUILD_DIR}/${RELEASE_DIR_NAME}/knowledge"
# 例: もし初期の user_preference.txt を含めるなら
# cp knowledge/user_preference.txt.template "${BUILD_DIR}/${RELEASE_DIR_NAME}/knowledge/user_preference.txt"
echo ""

# --- 不要なファイルをクリーンアップ (コピー後に行う) ---
echo "[情報] 配布用ディレクトリ内の不要なファイルを削除しています..."
find "${BUILD_DIR}/${RELEASE_DIR_NAME}" -name '__pycache__' -type d -exec rm -rf {} + \
find "${BUILD_DIR}/${RELEASE_DIR_NAME}" -name '*.pyc' -type f -delete \
find "${BUILD_DIR}/${RELEASE_DIR_NAME}" -name '.DS_Store' -type f -delete
# 必要に応じて他の不要ファイルを削除
echo ""

# --- パーミッションの設定 (実行スクリプトに実行権限を付与) ---
echo "[情報] スクリプトに実行権限を付与しています..."
chmod +x "${BUILD_DIR}/${RELEASE_DIR_NAME}/setup_env.sh"
chmod +x "${BUILD_DIR}/${RELEASE_DIR_NAME}/run_ui.sh"
echo ""

# --- ZIPアーカイブの作成 ---
echo "[情報] ZIPアーカイブ (${ZIP_FILE_NAME}) を作成しています..."
cd "${BUILD_DIR}" || exit 1
zip -r "../${ZIP_FILE_NAME}" "${RELEASE_DIR_NAME}" 
cd ..
echo ""

# --- 後片付け ---
echo "[情報] 一時ディレクトリ (${BUILD_DIR}) を削除しています..."
rm -rf "${BUILD_DIR}"
echo ""

echo "====================================================="
echo " 配布用ZIPアーカイブが正常に作成されました: ${ZIP_FILE_NAME}"
echo "====================================================="

exit 0 