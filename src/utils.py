"""
Universal Discord AI - Utilities
共通ユーティリティ関数とクラス
"""

import json
import logging
import os
import sys
from typing import Any, Dict, Optional
import coloredlogs


class ConfigManager:
    """設定ファイル管理クラス"""
    
    def __init__(self, config_path: str = "config/config.json"):
        self.config_path = config_path
        self.config: Dict = {}
        self.logger = logging.getLogger(__name__)
        self.load_config()
        
    def load_config(self) -> bool:
        """設定ファイルを読み込み"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                self.logger.info(f"設定ファイルを読み込みました: {self.config_path}")
                return True
            else:
                self.logger.warning(f"設定ファイルが見つかりません: {self.config_path}")
                self.config = self._get_default_config()
                return False
        except Exception as e:
            self.logger.error(f"設定ファイルの読み込みエラー: {e}")
            self.config = self._get_default_config()
            return False
            
    def _get_default_config(self) -> Dict:
        """デフォルト設定を取得"""
        return {
            "bot_settings": {
                "chat_history_limit": 100,
                "context_token_limit": 125000,
                "rate_limit_adjustment": True,
                "typing_indicator_enabled": True,
                "max_response_length": 2000,
                "stream_update_interval": 0.5
            },
            "openai_settings": {
                "model": "gpt-5",
                "max_tokens": 2000,
                "temperature": 0.7,
                "stream": True,
                "timeout": 30
            },
            "discord_settings": {
                "command_prefix": "!ai",
                "activity_type": "watching",
                "status": "online"
            },
            "character_settings": {
                "default_character": "friendly",
                "characters_directory": "characters",
                "parallel_characters": True
            },
            "logging": {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                "file_enabled": True,
                "file_path": "logs/discord_ai.log"
            }
        }
        
    def get(self, key_path: str, default: Any = None) -> Any:
        """ドット記法で設定値を取得"""
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
            
    def set(self, key_path: str, value: Any) -> bool:
        """ドット記法で設定値を設定"""
        keys = key_path.split('.')
        config = self.config
        
        try:
            for key in keys[:-1]:
                if key not in config:
                    config[key] = {}
                config = config[key]
            config[keys[-1]] = value
            return True
        except Exception as e:
            self.logger.error(f"設定値の設定エラー: {e}")
            return False
            
    def save_config(self) -> bool:
        """設定ファイルを保存"""
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            self.logger.info(f"設定ファイルを保存しました: {self.config_path}")
            return True
        except Exception as e:
            self.logger.error(f"設定ファイルの保存エラー: {e}")
            return False


class TokenCounter:
    """トークン数カウント・管理クラス"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
    def estimate_tokens(self, text: str) -> int:
        """テキストのトークン数を推定"""
        if not text:
            return 0
            
        # GPT-5用の簡易トークン推定
        # 日本語: 約1文字 = 1.5トークン
        # 英語: 約4文字 = 1トークン
        # 記号・空白: 約1文字 = 0.5トークン
        
        japanese_chars = 0
        english_chars = 0
        other_chars = 0
        
        for char in text:
            if ord(char) > 127:  # 日本語・中国語・その他非ASCII
                japanese_chars += 1
            elif char.isalpha():  # 英語アルファベット
                english_chars += 1
            else:  # 数字・記号・空白
                other_chars += 1
                
        estimated_tokens = int(
            japanese_chars * 1.5 + 
            english_chars * 0.25 + 
            other_chars * 0.5
        )
        
        return max(1, estimated_tokens)
        
    def check_context_limit(self, context: str, limit: int = 125000) -> bool:
        """コンテキストがトークン制限内かチェック"""
        token_count = self.estimate_tokens(context)
        
        if token_count > limit:
            self.logger.warning(f"コンテキストがトークン制限を超過: {token_count} > {limit}")
            return False
            
        self.logger.debug(f"コンテキストトークン数: {token_count}/{limit}")
        return True
        
    def truncate_to_limit(self, text: str, limit: int = 125000) -> str:
        """テキストをトークン制限内に切り詰め"""
        if self.check_context_limit(text, limit):
            return text
            
        # バイナリサーチで適切な長さを見つける
        left, right = 0, len(text)
        result = text
        
        while left < right:
            mid = (left + right + 1) // 2
            truncated = text[:mid]
            
            if self.estimate_tokens(truncated) <= limit:
                result = truncated
                left = mid
            else:
                right = mid - 1
                
        self.logger.info(f"テキストを切り詰めました: {len(text)} -> {len(result)} 文字")
        return result


def setup_logging() -> logging.Logger:
    """ログ設定を初期化"""
    config_manager = ConfigManager()
    
    # ログレベルを取得
    log_level = config_manager.get('logging.level', 'INFO')
    log_format = config_manager.get(
        'logging.format', 
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # ルートロガーを設定
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # コンソール出力を設定（coloredlogs使用）
    coloredlogs.install(
        level=log_level.upper(),
        fmt=log_format,
        logger=logger
    )
    
    # ファイル出力を設定
    if config_manager.get('logging.file_enabled', True):
        log_file_path = config_manager.get('logging.file_path', 'logs/discord_ai.log')
        
        # ログディレクトリを作成
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        
        file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        file_handler.setFormatter(logging.Formatter(log_format))
        logger.addHandler(file_handler)
        
    # Discord.pyのログレベルを調整
    logging.getLogger('discord').setLevel(logging.WARNING)
    logging.getLogger('discord.http').setLevel(logging.WARNING)
    
    return logger


def validate_environment() -> bool:
    """環境変数の妥当性をチェック"""
    logger = logging.getLogger(__name__)
    required_vars = ['DISCORD_BOT_TOKEN', 'OPENAI_API_KEY']
    
    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
            
    if missing_vars:
        logger.error(f"必要な環境変数が設定されていません: {', '.join(missing_vars)}")
        return False
        
    logger.info("環境変数の検証が完了しました")
    return True


def format_file_size(size_bytes: int) -> str:
    """ファイルサイズを人間が読みやすい形式でフォーマット"""
    if size_bytes == 0:
        return "0B"
        
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
        
    return f"{size_bytes:.1f}{size_names[i]}"


def sanitize_filename(filename: str) -> str:
    """ファイル名を安全な形式にサニタイズ"""
    import re
    
    # 危険な文字を除去
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # 連続するアンダースコアを1つに
    sanitized = re.sub(r'_+', '_', sanitized)
    
    # 先頭・末尾のアンダースコアを除去
    sanitized = sanitized.strip('_')
    
    # 空文字の場合はデフォルト名
    if not sanitized:
        sanitized = "unnamed_file"
        
    return sanitized


class RateLimitManager:
    """レート制限管理クラス"""
    
    def __init__(self, initial_rate: int = 50, time_period: int = 60):
        self.initial_rate = initial_rate
        self.current_rate = initial_rate
        self.time_period = time_period
        self.logger = logging.getLogger(__name__)
        
    def adjust_rate_limit(self, success: bool, response_time: float = 0.0):
        """レスポンス結果に基づいてレート制限を調整"""
        if success:
            # 成功時は徐々にレートを上げる
            if response_time < 1.0:  # 1秒未満の場合
                self.current_rate = min(self.initial_rate, int(self.current_rate * 1.1))
        else:
            # 失敗時はレートを下げる
            self.current_rate = max(10, int(self.current_rate * 0.7))
            
        self.logger.debug(f"レート制限を調整: {self.current_rate}/{self.time_period}秒")
        
    def get_current_rate(self) -> int:
        """現在のレート制限を取得"""
        return self.current_rate
        
    def reset_rate_limit(self):
        """レート制限を初期値にリセット"""
        self.current_rate = self.initial_rate
        self.logger.info("レート制限を初期値にリセットしました")
