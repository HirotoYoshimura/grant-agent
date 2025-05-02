"""
ログ出力をStreamlit UI上に表示するためのユーティリティ
"""

import sys
import os
import logging
import threading
import time
from contextlib import contextmanager
import datetime
import queue

# スレッド間通信用キュー
log_queue = queue.Queue()

class FileLogHandler(logging.Handler):
    """ファイルにログを出力するハンドラー"""
    
    def __init__(self, log_file_path):
        super().__init__()
        self.log_file_path = log_file_path
        self.formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # ログディレクトリを作成
        log_dir = os.path.dirname(log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
            
        # 空のログファイルを作成
        with open(log_file_path, 'w', encoding='utf-8') as f:
            f.write(f"=== ログセッション開始: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    
    def emit(self, record):
        """ログレコードをファイルに出力"""
        try:
            msg = self.formatter.format(record)
            with open(self.log_file_path, 'a', encoding='utf-8') as f:
                f.write(msg + '\n')
        except Exception:
            self.handleError(record)


class TeeStreamHandler:
    """標準出力/標準エラー出力をファイルと元のストリームに同時に出力"""
    
    def __init__(self, log_file, original_stream):
        self.log_file = log_file
        self.terminal = original_stream
    
    def write(self, message):
        """テキストを書き込み"""
        if self.terminal:
            self.terminal.write(message)
        if self.log_file and message:
            self.log_file.write(message)
            self.log_file.flush()
            # テキストをキューに追加（UI表示用）
            if message.strip():
                log_queue.put(message)
        return len(message)
    
    def flush(self):
        """バッファをフラッシュ"""
        if self.terminal:
            self.terminal.flush()
        if self.log_file:
            self.log_file.flush()


class LogFileReader:
    """ログファイルを定期的に読み込み、キューに追加するクラス"""
    
    def __init__(self, log_file_path, container=None, update_interval=0.5):
        self.log_file_path = log_file_path
        self.container = container
        self.update_interval = update_interval
        self._stop_event = threading.Event()
        self._thread = None
        self._last_position = 0
    
    def start(self):
        """ログ読み込みスレッドを開始"""
        if self._thread is not None and self._thread.is_alive():
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._read_log_loop, daemon=True)
        self._thread.start()
    
    def stop(self):
        """ログ読み込みスレッドを停止"""
        if self._thread is not None:
            self._stop_event.set()
            self._thread.join(timeout=2.0)
            self._thread = None
    
    def _read_log_loop(self):
        """ログファイルを定期的に読み込むループ"""
        while not self._stop_event.is_set():
            try:
                self._read_log_file()
            except Exception as e:
                print(f"ログ読み込みエラー: {e}")
            
            # 指定した間隔だけ待機
            self._stop_event.wait(self.update_interval)
    
    def _read_log_file(self):
        """ログファイルの内容を読み込み、キューに追加"""
        if not os.path.exists(self.log_file_path):
            return
        
        try:
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                # 前回の位置に移動
                f.seek(self._last_position)
                
                # 新しいデータを読み込み
                new_data = f.read()
                if new_data:
                    # キューに追加
                    log_queue.put(new_data)
                
                # 現在のファイル位置を記録
                self._last_position = f.tell()
        except Exception as e:
            print(f"ログファイル読み込みエラー: {e}")


@contextmanager
def capture_output_to_file_and_ui(log_file_path, log_container=None):
    """
    標準出力と標準エラー出力をファイルとStreamlit UIの両方にリダイレクト
    
    Args:
        log_file_path: ログファイルのパス
        log_container: Streamlitのログ表示コンテナ（互換性のために残すが使用しない）
    """
    # 元のストリームを保存
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    
    # ログファイルを開く
    log_dir = os.path.dirname(log_file_path)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    log_file = open(log_file_path, 'a', encoding='utf-8')
    log_file.write(f"=== ログセッション開始: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    
    # ファイルと標準出力の両方に書き込むハンドラー
    stdout_handler = TeeStreamHandler(log_file, original_stdout)
    stderr_handler = TeeStreamHandler(log_file, original_stderr)
    
    # 標準出力と標準エラー出力をリダイレクト
    sys.stdout = stdout_handler
    sys.stderr = stderr_handler
    
    # ロガーの設定
    file_log_handler = FileLogHandler(log_file_path)
    
    root_logger = logging.getLogger()
    root_logger.addHandler(file_log_handler)
    previous_level = root_logger.level
    root_logger.setLevel(logging.INFO)
    
    try:
        # コンテキスト内のコードを実行
        yield
    finally:
        # 標準出力をフラッシュ
        stdout_handler.flush()
        stderr_handler.flush()
        
        # 元のストリームに戻す
        sys.stdout = original_stdout
        sys.stderr = original_stderr
        
        # ロガーを元に戻す
        root_logger.removeHandler(file_log_handler)
        root_logger.setLevel(previous_level)
        
        # ログファイルを閉じる
        log_file.write(f"=== ログセッション終了: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        log_file.close()


def run_with_file_and_ui_log_capture(func, log_file_path, *args, **kwargs):
    """
    関数の出力をファイルとUIの両方にキャプチャ
    """
    with capture_output_to_file_and_ui(log_file_path):
        return func(*args, **kwargs)


# キューからログを取得する関数
def get_new_logs(max_lines=1000):
    """キューから新しいログを取得"""
    logs = []
    try:
        while not log_queue.empty():
            log = log_queue.get_nowait()
            logs.append(log)
            log_queue.task_done()
    except Exception:
        pass
    
    return ''.join(logs)