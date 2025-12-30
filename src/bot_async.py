"""
Universal Discord AI - Main Bot Module (非同期処理最適化版)
メインのDiscord BOT実装 - 同時処理対応
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from datetime import datetime, timedelta

import discord
from discord.ext import commands
from dotenv import load_dotenv

from character_manager import CharacterManager
from openai_handler import OpenAIHandler
from utils import ConfigManager, setup_logging, TokenCounter, DetailedLogger, UsageAggregator

# 環境変数を読み込み
load_dotenv('env.local')

@dataclass
class MessageTask:
    """メッセージ処理タスクの情報"""
    message_id: int
    channel_id: int
    guild_id: Optional[int]
    task: asyncio.Task
    start_time: datetime
    character_name: str
    status: str = "processing"  # processing, completed, failed, cancelled

class UniversalDiscordAI(commands.Bot):
    """Universal Discord AI Bot クラス（非同期処理最適化版）"""
    
    def __init__(self):
        # Discord BOTの基本設定
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        
        super().__init__(
            command_prefix='!ai',
            intents=intents,
            help_command=None
        )
        
        # 設定とマネージャーの初期化
        self.config = ConfigManager()
        self.character_manager = CharacterManager()
        self.openai_handler = OpenAIHandler(self.config)
        self.token_counter = TokenCounter()
        
        # BOTインスタンスの管理
        self.character_bots: Dict[str, 'CharacterBot'] = {}
        
        # 非同期処理制御
        self.max_concurrent_messages = self.config.get('bot_settings.max_concurrent_messages', 15)
        self.message_semaphore = asyncio.Semaphore(self.max_concurrent_messages)
        self.active_message_tasks: Dict[int, MessageTask] = {}
        self.task_cleanup_interval = self.config.get('bot_settings.cleanup_interval_seconds', 300)
        
        # ログ設定
        self.logger = setup_logging()
        self.detailed_logger = DetailedLogger(self.config)
        self.usage_aggregator = UsageAggregator()
        
        # 統計情報
        self.stats = {
            'total_messages_processed': 0,
            'concurrent_messages_peak': 0,
            'average_response_time': 0.0,
            'failed_messages': 0,
            'server_message_counts': {},
            'channel_message_counts': {}
        }
        
    async def setup_hook(self):
        """BOT起動時の初期設定"""
        self.logger.info("Universal Discord AI を初期化中...")
        
        # 人格設定を読み込み
        characters = await self.character_manager.load_all_characters()
        self.logger.info(f"人格設定を読み込みました: {list(characters.keys())}")
        
        # 各人格に対応するBOTインスタンスを作成
        for character_name, character_data in characters.items():
            bot_instance = CharacterBot(
                character_name=character_name,
                character_data=character_data,
                parent_bot=self
            )
            self.character_bots[character_name] = bot_instance
            
        self.logger.info(f"BOTインスタンスを作成しました: {len(self.character_bots)}個")
        self.logger.info(f"最大同時処理数: {self.max_concurrent_messages}")
        
        # タスククリーンアップタスクを開始
        if self.config.get('bot_settings.enable_task_cleanup', True):
            asyncio.create_task(self._start_task_cleanup())
        
    async def _start_task_cleanup(self):
        """定期的なタスククリーンアップを実行"""
        while True:
            try:
                await asyncio.sleep(self.task_cleanup_interval)
                await self._cleanup_completed_tasks()
            except Exception as e:
                self.logger.error(f"タスククリーンアップ中にエラー: {e}")
                
    async def _cleanup_completed_tasks(self):
        """完了したタスクをクリーンアップ"""
        current_time = datetime.now()
        tasks_to_remove = []
        
        for message_id, task_info in self.active_message_tasks.items():
            # 完了または失敗したタスクを特定
            if task_info.status in ["completed", "failed"]:
                tasks_to_remove.append(message_id)
            # 長時間実行中のタスクをチェック（設定されたタイムアウト時間以上）
            elif (current_time - task_info.start_time) > timedelta(seconds=self.config.get('bot_settings.message_timeout_seconds', 300)):
                self.logger.warning(f"タイムアウトしたタスクをキャンセル: {message_id}")
                task_info.task.cancel()
                tasks_to_remove.append(message_id)
                
        # 完了したタスクを削除
        for message_id in tasks_to_remove:
            del self.active_message_tasks[message_id]
            
        self.logger.debug(f"タスククリーンアップ完了: {len(tasks_to_remove)}個のタスクを削除")
        
    async def on_ready(self):
        """BOT接続完了時の処理"""
        self.logger.info(f'{self.user} として Discord に接続しました')
        self.logger.info(f'サーバー数: {len(self.guilds)}')
        self.logger.info(f'最大同時処理数: {self.max_concurrent_messages}')
        
        # 各サーバーの詳細ログ出力
        for guild in self.guilds:
            self.detailed_logger.log_server_activity(
                server_name=guild.name,
                server_id=str(guild.id),
                action="BOT接続完了",
                details=f"メンバー数: {guild.member_count}, チャンネル数: {len(guild.channels)}"
            )
        
        # BOTステータスをオンラインに設定
        activity = discord.Activity(
            type=discord.ActivityType.competing,
                            name=self.config.get('discord_settings.status', 'みんなの会話')
        )
        await self.change_presence(
            status=discord.Status.online,
            activity=activity
        )
        self.logger.info(self.config.get('logging_settings.log_messages.bot_status_online', 'BOTステータスをオンラインに設定しました'))
        
        # 料金体系のサマリーを表示
        cost_summary = self.detailed_logger.cost_calculator.get_cost_summary()
        self.logger.info(cost_summary)
        
        # OpenAI API接続状態のヘルスモニタリングを開始
        asyncio.create_task(self.openai_handler.start_health_monitoring())
        self.logger.info(self.config.get('logging_settings.log_messages.openai_health_monitoring_started', 'OpenAI API接続状態のヘルスモニタリングを開始しました'))
    
    async def on_disconnect(self):
        """Discord切断時の処理"""
        self.logger.warning(self.config.get('logging_settings.log_messages.discord_disconnected', 'Discordから切断されました'))
    
    async def on_resumed(self):
        """Discord再接続時の処理"""
        self.logger.info(self.config.get('logging_settings.log_messages.discord_reconnected', 'Discordに再接続しました'))
        # 再接続時にステータスを再設定
        try:
            activity = discord.Activity(
                type=discord.ActivityType.competing,
                name=self.config.get('discord_settings.status', 'みんなの会話')
            )
            await self.change_presence(
                status=discord.Status.online,
                activity=activity
            )
            self.logger.info(self.config.get('logging_settings.log_messages.bot_status_reconnect', '再接続時にBOTステータスをオンラインに再設定しました'))
        except Exception as e:
            self.logger.warning(f"再接続時のステータス設定エラー: {e}")
    
    async def close(self):
        """BOT終了時の処理"""
        self.logger.info(self.config.get('logging_settings.log_messages.bot_shutdown', 'BOTを終了中...'))
        
        # 実行中のタスクをキャンセル
        for task_info in self.active_message_tasks.values():
            if not task_info.task.done():
                task_info.task.cancel()
                self.logger.debug(self.config.get('logging_settings.log_messages.task_cancelled', 'タスクをキャンセル: {message_id}').format(message_id=task_info.message_id))
        
        # ステータスをオフラインに設定（複数回試行）
        for attempt in range(3):
            try:
                await self.change_presence(
                    status=discord.Status.offline,
                    activity=None
                )
                self.logger.info(self.config.get('logging_settings.log_messages.bot_status_offline', 'BOTステータスをオフラインに設定しました'))
                break
            except discord.ConnectionClosed:
                self.logger.info(self.config.get('logging_settings.log_messages.connection_closed', 'Discord接続が既に閉じられています'))
                break
            except Exception as e:
                self.logger.warning(self.config.get('logging_settings.log_messages.status_change_error', 'ステータス変更エラー (試行 {attempt}/3): {error}').format(attempt=attempt + 1, error=e))
                if attempt < 2:
                    await asyncio.sleep(0.5)
        
        # 親クラスの終了処理を呼び出し
        try:
            await super().close()
        except Exception as e:
            self.logger.warning(self.config.get('logging_settings.log_messages.parent_class_error', '親クラスの終了処理でエラー: {error}').format(error=e))
        
        # aiohttpセッションの適切な終了処理
        try:
            if hasattr(self, 'http') and hasattr(self.http, '_HTTPClient__session'):
                session = self.http._HTTPClient__session
                if not session.closed:
                    await session.close()
                    self.logger.info(self.config.get('logging_settings.log_messages.session_closed', 'aiohttpセッションを適切に終了しました'))
        except Exception as e:
            self.logger.warning(self.config.get('logging_settings.log_messages.session_cleanup_error', 'aiohttpセッション終了処理でエラー: {error}').format(error=e))
        
    async def on_message(self, message: discord.Message):
        """メッセージ受信時の処理（非同期最適化版）"""
        # 自分のメッセージは無視
        if message.author == self.user:
            return
            
        # BOTメッセージは無視
        if message.author.bot:
            return
            
        # メンションチェック（個人メンションまたはBOTロールメンション）
        is_mentioned = self.user.mentioned_in(message)
        mention_type = "個人メンション"
        
        # ロールメンションもチェック
        if not is_mentioned and message.guild:
            bot_member = message.guild.get_member(self.user.id)
            if bot_member:
                for role in bot_member.roles:
                    if role.id in message.raw_role_mentions:
                        is_mentioned = True
                        mention_type = f"ロールメンション ({role.name})"
                        self.logger.debug(f"ロールメンション検知: {role.name}")
                        break
        
        # 現在のメッセージに他ユーザー/ロール/全体(@everyone/@here)へのメンションが含まれる場合、
        # 自分がメンションされていない限りは自動発火（連続会話）を抑止する
        has_other_mentions_in_current = (
            (len(message.mentions) > 0) or
            (len(message.role_mentions) > 0) or
            getattr(message, "mention_everyone", False)
        )

        # 前のメッセージがBOTかどうかをチェック（設定で有効化されている場合のみ）
        is_previous_bot = False
        if self.config.get('bot_settings.continuous_conversation_enabled', True) and not has_other_mentions_in_current:
            is_previous_bot = await self.is_previous_message_from_bot(message)
            if is_previous_bot:
                mention_type = "連続会話（前のメッセージがBOT）"
                is_mentioned = True
        
        # 詳細ログ出力
        if message.guild:
            self.detailed_logger.log_mention_detection(
                server_name=message.guild.name,
                channel_name=message.channel.name,
                user_name=message.author.display_name,
                mention_type=mention_type,
                message_content=message.content
            )
        
        # デバッグ用ログ
        self.logger.debug(f"メッセージ受信: {message.author} -> {message.content}")
        self.logger.debug(f"メンション検知: {is_mentioned} (タイプ: {mention_type})")
        
        if not is_mentioned:
            # コマンド処理をチェック
            await self.handle_commands(message)
            return
            
        # 非同期で返答処理を開始（同時処理対応）
        asyncio.create_task(self._handle_mention_async(message))
        
    async def _handle_mention_async(self, message: discord.Message):
        """メンション時の返答処理（非同期版）"""
        # セマフォで同時実行数を制御
        async with self.message_semaphore:
            try:
                # 現在の同時実行数を更新
                current_concurrent = len(self.active_message_tasks)
                if current_concurrent > self.stats['concurrent_messages_peak']:
                    self.stats['concurrent_messages_peak'] = current_concurrent
                
                # 統計情報を更新
                if message.guild:
                    server_name = message.guild.name
                    channel_name = message.channel.name
                    
                    # サーバー別メッセージ数
                    if server_name not in self.stats['server_message_counts']:
                        self.stats['server_message_counts'][server_name] = 0
                    self.stats['server_message_counts'][server_name] += 1
                    
                    # チャンネル別メッセージ数
                    channel_key = f"{server_name}#{channel_name}"
                    if channel_key not in self.stats['channel_message_counts']:
                        self.stats['channel_message_counts'][channel_key] = 0
                    self.stats['channel_message_counts'][channel_key] += 1
                
                # 使用する人格を決定
                character_name = self.config.get('character_settings.default_character', 'friendly')
                character_bot = self.character_bots.get(character_name)
                
                if not character_bot:
                    await message.reply("申し訳ございません。人格設定の読み込みに失敗しました。")
                    return
                
                # メッセージ処理タスクを作成
                task = asyncio.create_task(
                    self._process_message_with_character(message, character_bot, character_name)
                )
                
                # タスク情報を記録
                task_info = MessageTask(
                    message_id=message.id,
                    channel_id=message.channel.id,
                    guild_id=message.guild.id if message.guild else None,
                    task=task,
                    start_time=datetime.now(),
                    character_name=character_name
                )
                
                self.active_message_tasks[message.id] = task_info
                
                # タスク完了まで待機
                await task
                
                # 成功時の統計更新
                self.stats['total_messages_processed'] += 1
                task_info.status = "completed"
                
            except asyncio.CancelledError:
                # タスクがキャンセルされた場合
                if message.id in self.active_message_tasks:
                    self.active_message_tasks[message.id].status = "cancelled"
                self.logger.info(f"メッセージ処理がキャンセルされました: {message.id}")
                
            except Exception as e:
                # エラー時の統計更新
                self.stats['failed_messages'] += 1
                if message.id in self.active_message_tasks:
                    self.active_message_tasks[message.id].status = "failed"
                
                # エラーログ
                if message.guild:
                    self.detailed_logger.log_error_detail(
                        error=e,
                        context=f"メンション処理 - サーバー: {message.guild.name}, チャンネル: #{message.channel.name}",
                        additional_info=f"ユーザー: {message.author.display_name}"
                    )
                else:
                    self.detailed_logger.log_error_detail(
                        error=e,
                        context="メンション処理 - DM",
                        additional_info=f"ユーザー: {message.author.display_name}"
                    )
                
                try:
                    await message.reply(f"エラーが発生しました: {str(e)}")
                except:
                    pass
                    
            finally:
                # セマフォの解放は自動的に行われる
                pass
                
    async def _process_message_with_character(self, message: discord.Message, character_bot: 'CharacterBot', character_name: str):
        """キャラクターを使用してメッセージを処理"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            # typing indicator開始（入力中ステータスを表示）
            async with message.channel.typing():
                # チャンネル情報を取得
                channel_info = await self.get_channel_info(message.channel)
                
                # チャット履歴を取得
                chat_history = await self.get_chat_history(message.channel)
                
                # キャラクター選択の詳細ログ
                if message.guild:
                    available_characters = list(self.character_bots.keys())
                    self.detailed_logger.log_character_selection(
                        server_name=message.guild.name,
                        channel_name=message.channel.name,
                        selected_character=character_name,
                        available_characters=available_characters
                    )
                
                # 返答生成
                await character_bot.generate_response(
                    message=message,
                    channel_info=channel_info,
                    chat_history=chat_history
                )
                
                # 成功時のレスポンス時間ログ
                response_time = asyncio.get_event_loop().time() - start_time
                if message.guild:
                    self.detailed_logger.log_response_time(
                        operation="メンション処理",
                        response_time=response_time,
                        success=True
                    )
                
                # 統計情報の更新
                if self.stats['total_messages_processed'] > 0:
                    current_avg = self.stats['average_response_time']
                    new_avg = (current_avg * (self.stats['total_messages_processed'] - 1) + response_time) / self.stats['total_messages_processed']
                    self.stats['average_response_time'] = new_avg
                
        except Exception as e:
            # エラー時の詳細ログ
            response_time = asyncio.get_event_loop().time() - start_time
            if message.guild:
                self.detailed_logger.log_error_detail(
                    error=e,
                    context=f"返答生成 - サーバー: {message.guild.name}, チャンネル: #{message.channel.name}",
                    additional_info=f"ユーザー: {message.author.display_name}, キャラクター: {character_name}, レスポンス時間: {response_time:.2f}秒"
                )
            else:
                self.detailed_logger.log_error_detail(
                    error=e,
                    context="返答生成 - DM",
                    additional_info=f"ユーザー: {message.author.display_name}, キャラクター: {character_name}, レスポンス時間: {response_time:.2f}秒"
                )
            
            try:
                await message.reply(f"エラーが発生しました: {str(e)}")
            except:
                pass
                
    async def get_channel_info(self, channel) -> Dict:
        """チャンネル情報を取得"""
        info = {
            'name': channel.name,
            'type': str(channel.type),
            'topic': getattr(channel, 'topic', None) or '設定されていません',
            'id': channel.id
        }
        
        # スレッドの場合は親チャンネル情報も取得
        if isinstance(channel, discord.Thread):
            info['parent_channel'] = channel.parent.name
            info['thread_starter'] = channel.owner.display_name if channel.owner else '不明'
            
        return info
        
    async def get_chat_history(self, channel) -> List[Dict]:
        """チャット履歴を取得"""
        history_limit = self.config.get('general_settings.chat_history_limit', 100)
        history = []
        
        try:
            async for message in channel.history(limit=history_limit):
                # BOTメッセージは履歴から除外
                if message.author.bot:
                    continue
                    
                history_item = {
                    'author': message.author.display_name,
                    'content': message.content,
                    'timestamp': message.created_at.isoformat(),
                    'attachments': len(message.attachments) > 0,
                    'id': message.id,
                    'is_reply': message.reference is not None
                }
                history.append(history_item)
                
            # 時系列順に並び替え（古い順）
            history.reverse()
            
        except Exception as e:
            self.logger.error(f"チャット履歴取得中にエラー: {e}")
            
        return history
    
    async def get_reply_context(self, message: discord.Message) -> Dict:
        """返信先のメッセージコンテキストを取得"""
        if not message.reference:
            return None
            
        try:
            # 返信先のメッセージを取得
            referenced_message = await message.channel.fetch_message(message.reference.message_id)
            
            if referenced_message:
                # 返信先のメッセージがBOTの場合は除外
                if referenced_message.author.bot:
                    self.logger.debug(f"返信先メッセージはBOTのため除外: {referenced_message.author}")
                    return None
                    
                return {
                    'author': referenced_message.author.display_name,
                    'content': referenced_message.content,
                    'timestamp': referenced_message.created_at.isoformat(),
                    'attachments': len(referenced_message.attachments) > 0,
                    'id': referenced_message.id
                }
        except discord.NotFound:
            self.logger.warning(f"返信先メッセージが見つかりません: {message.reference.message_id}")
        except discord.Forbidden:
            self.logger.warning(f"返信先メッセージへのアクセス権限がありません: {message.reference.message_id}")
        except Exception as e:
            self.logger.error(f"返信先メッセージ取得中にエラー: {e}")
            
        return None
    
    async def handle_commands(self, message: discord.Message):
        """コマンド処理"""
        if not self.config.get('discord_settings.admin_commands_enabled', True):
            return
            
        content = message.content.strip()
        command_prefix = self.config.get('discord_settings.command_prefix', '!ai')
        status_command = self.config.get('discord_settings.status_check_command', '!status')
        
        # ステータス確認コマンド
        if content == status_command:
            await self.handle_status_command(message)
    
    async def handle_status_command(self, message: discord.Message):
        """ステータス確認コマンドの処理（非同期処理情報追加）"""
        try:
            # OpenAI API接続状態を取得
            openai_status = self.openai_handler.get_connection_status()
            rate_limit_status = self.openai_handler.get_rate_limit_status()
            
            # 現在の同時処理状況
            current_concurrent = len(self.active_message_tasks)
            processing_tasks = [t for t in self.active_message_tasks.values() if t.status == "processing"]
            
            # サーバー別統計
            server_stats = ""
            if self.stats['server_message_counts']:
                server_stats = "\n📊 **サーバー別統計**\n"
                for server, count in sorted(self.stats['server_message_counts'].items(), key=lambda x: x[1], reverse=True)[:5]:
                    server_stats += f"• {server}: {count}件\n"
            
            # チャンネル別統計
            channel_stats = ""
            if self.stats['channel_message_counts']:
                channel_stats = "\n📈 **チャンネル別統計**\n"
                for channel, count in sorted(self.stats['channel_message_counts'].items(), key=lambda x: x[1], reverse=True)[:5]:
                    channel_stats += f"• {channel}: {count}件\n"
            
            # ステータス情報を構築
            status_info = f"""🤖 **Universal Discord AI ステータス**

📡 **OpenAI API接続状態**
• 状態: {openai_status['status']}
• 連続失敗回数: {openai_status['consecutive_failures']}
• 自動復元: {'有効' if openai_status['auto_recovery_enabled'] else '無効'}
• 最終成功: {openai_status.get('last_successful_call', 'なし')}

⚡ **レート制限状況**
• 現在の制限: {rate_limit_status['current_limit']}/分
• 利用可能: {rate_limit_status['available']}/分

🔄 **BOT状態**
• Discord接続: オンライン
• 人格数: {len(self.character_bots)}
• 利用可能人格: {', '.join(self.character_bots.keys())}

🚀 **非同期処理状況**
• 最大同時処理数: {self.max_concurrent_messages}
• 現在の同時処理数: {current_concurrent}
• 処理中タスク: {len(processing_tasks)}
• 総処理メッセージ数: {self.stats['total_messages_processed']}
• 平均応答時間: {self.stats['average_response_time']:.2f}秒
• ピーク同時処理数: {self.stats['concurrent_messages_peak']}
• 失敗メッセージ数: {self.stats['failed_messages']}{server_stats}{channel_stats}"""
            
            await message.reply(status_info)
            
        except Exception as e:
            self.logger.error(f"ステータスコマンド処理エラー: {e}")
            await message.reply("申し訳ございません。ステータス情報の取得に失敗しました。")
    
    async def is_previous_message_from_bot(self, message: discord.Message) -> bool:
        """前のメッセージがBOTかどうかを判定"""
        try:
            # チャンネルの最新メッセージを取得（制限: 2件）
            async for msg in message.channel.history(limit=2, before=message):
                # 最初のメッセージ（現在のメッセージの直前）がBOTかチェック
                if msg.author == self.user:
                    self.logger.debug(f"前のメッセージがBOT: {msg.content[:50]}...")
                    return True
                break  # 最初のメッセージのみチェック
            
            return False
        except Exception as e:
            self.logger.error(f"前のメッセージ判定エラー: {e}")
            return False


class CharacterBot:
    """個別の人格を持つBOTインスタンス（非同期処理最適化版）"""
    
    def __init__(self, character_name: str, character_data: Dict, parent_bot: UniversalDiscordAI):
        self.character_name = character_name
        self.character_data = character_data
        self.parent_bot = parent_bot
        self.logger = logging.getLogger(f"CharacterBot.{character_name}")
        
    async def generate_response(self, message: discord.Message, channel_info: Dict, chat_history: List[Dict]):
        """返答を生成して送信（非同期最適化版）"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            # 返信先のコンテキストを取得
            reply_context = await self.parent_bot.get_reply_context(message)
            
            # 返信先のコンテキスト取得状況をログ出力
            if reply_context:
                self.logger.info(f"返信先メッセージを取得: {reply_context['author']} -> {reply_context['content'][:50]}...")
            else:
                self.logger.debug("返信先メッセージなし、通常のメッセージとして処理")
            
            # コンテキストを構築
            context = self.build_context(message, channel_info, chat_history, reply_context)
            
            # トークン数チェック
            if not self.parent_bot.token_counter.check_context_limit(context):
                await message.reply("申し訳ございません。コンテキストが長すぎるため、履歴を短縮して再試行してください。")
                return
                
            # OpenAI APIで返答生成（ストリーミング）
            response_message = None
            full_response = ""
            is_first_chunk = True
            
            async for chunk in self.parent_bot.openai_handler.generate_streaming_response(
                context=context,
                character_data=self.character_data,
                model=self.parent_bot.config.get('openai_settings.model', 'google/gemini-2.5-flash-lite')
            ):
                full_response += chunk
                
                # 最初のチャンクの場合、メッセージを送信
                if is_first_chunk:
                    try:
                        response_message = await message.reply(full_response[:2000])
                        is_first_chunk = False
                        self.logger.debug(f"初回メッセージ送信完了: {len(full_response)}文字")
                    except Exception as e:
                        self.logger.error(f"初回メッセージ送信エラー: {e}")
                        # 初回送信に失敗した場合は、次のチャンクで再試行
                        continue
                
                # 2番目以降のチャンクの場合、メッセージを編集更新
                elif response_message and len(full_response) % 100 == 0:  # 100文字ごとに更新
                    try:
                        await response_message.edit(content=full_response[:2000])  # Discord制限
                    except discord.NotFound:
                        # メッセージが削除された場合
                        break
                    except discord.HTTPException:
                        # 編集制限に達した場合
                        pass
                        
            # 最終的な返答を設定（初回送信が失敗していた場合のフォールバック）
            if not response_message and full_response:
                try:
                    response_message = await message.reply(full_response[:2000])
                except Exception as e:
                    self.logger.error(f"フォールバックメッセージ送信エラー: {e}")
            elif response_message and full_response:
                try:
                    await response_message.edit(content=full_response[:2000])
                except discord.NotFound:
                    pass
            
            # 成功時の詳細ログ
            response_time = asyncio.get_event_loop().time() - start_time
            # トークン数の推定（簡易版）
            estimated_output_tokens = len(full_response.split()) if full_response else 0
            estimated_input_tokens = len(context.split()) if context else 0

            # 集計: ユーザーごとの使用量を擬似DB(JSON)に加算
            try:
                cost_data = self.parent_bot.detailed_logger.cost_calculator.calculate_cost(
                    estimated_input_tokens, estimated_output_tokens
                )
                total_cost_usd = float(cost_data.get('total_cost_usd', 0.0)) if cost_data else 0.0
                total_cost_jpy = float(cost_data.get('total_cost_jpy', 0.0)) if cost_data else 0.0
                self.parent_bot.usage_aggregator.add_usage(
                    user_id=str(message.author.id),
                    user_name=message.author.display_name,
                    input_tokens=estimated_input_tokens,
                    output_tokens=estimated_output_tokens,
                    total_cost_usd=total_cost_usd,
                    total_cost_jpy=total_cost_jpy,
                )
            except Exception as agg_err:
                self.logger.error(f"使用量集計エラー: {agg_err}")

            if message.guild:
                self.parent_bot.detailed_logger.log_message_generation(
                    server_name=message.guild.name,
                    channel_name=message.channel.name,
                    user_name=message.author.display_name,
                    character_name=self.character_name,
                    response_time=response_time,
                    token_count=estimated_output_tokens,
                    message_sent=response_message is not None,
                    input_tokens=estimated_input_tokens,
                    output_tokens=estimated_output_tokens,
                    response_content=full_response
                )
                
        except Exception as e:
            # エラー時の詳細ログ
            response_time = asyncio.get_event_loop().time() - start_time
            if message.guild:
                self.parent_bot.detailed_logger.log_error_detail(
                    error=e,
                    context=f"返答生成 - サーバー: {message.guild.name}, チャンネル: #{message.channel.name}",
                    additional_info=f"ユーザー: {message.author.display_name}, キャラクター: {self.character_name}, レスポンス時間: {response_time:.2f}秒"
                )
            else:
                self.parent_bot.detailed_logger.log_error_detail(
                    error=e,
                    context="返答生成 - DM",
                    additional_info=f"ユーザー: {message.author.display_name}, キャラクター: {self.character_name}, レスポンス時間: {response_time:.2f}秒"
                )
            
            try:
                await message.reply(f"申し訳ございません。エラーが発生しました: {str(e)}")
            except:
                pass
                
    def build_context(self, message: discord.Message, channel_info: Dict, chat_history: List[Dict], reply_context: Dict = None) -> str:
        """AIへ送信するコンテキストを構築"""
        context_parts = []
        
        # 人格設定
        context_parts.append(f"# 人格設定\n{self.character_data.get('content', '')}")
        
        # チャンネル情報
        context_parts.append(f"\n# チャンネル情報")
        context_parts.append(f"チャンネル名: {channel_info['name']}")
        context_parts.append(f"チャンネルトピック: {channel_info['topic']}")
        context_parts.append(f"チャンネルタイプ: {channel_info['type']}")
        
        # 返信先のメッセージ（存在する場合）
        if reply_context:
            context_parts.append(f"\n# 返信先のメッセージ")
            context_parts.append(f"{reply_context['author']}: {reply_context['content']}")
            if reply_context.get('attachments', False):
                context_parts.append(f"（添付ファイルあり）")
            context_parts.append(f"（このメッセージへの返信として、以下のメッセージが送信されました）")
        
        # チャット履歴
        if chat_history:
            context_parts.append(f"\n# 最近のチャット履歴")
            for item in chat_history[-20:]:  # 直近20件
                # 返信先のメッセージは履歴から除外（重複を避けるため）
                if reply_context and item['id'] == reply_context['id']:
                    continue
                context_parts.append(f"{item['author']}: {item['content']}")
                
        # 現在のメッセージ
        context_parts.append(f"\n# 現在のメッセージ")
        context_parts.append(f"{message.author.display_name}: {message.content}")
        
        # 返信の場合の指示
        if reply_context:
            context_parts.append(f"\n上記の返信先メッセージに対して、設定された人格で適切に返答してください。")
        else:
            context_parts.append(f"\n上記のメッセージに対して、設定された人格で返答してください。")
        
        return "\n".join(context_parts)


async def main():
    """メイン実行関数"""
    # 環境変数チェック
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("エラー: DISCORD_BOT_TOKEN が設定されていません")
        sys.exit(1)
        
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        print("エラー: OPENAI_API_KEY が設定されていません")
        sys.exit(1)
        
    # BOTインスタンスを作成
    bot = UniversalDiscordAI()
    
    # シグナルハンドラーを設定
    def signal_handler(signum, frame):
        """シグナル受信時の処理"""
        print(f"\nシグナル {signum} を受信しました。BOTを停止しています...")
        asyncio.create_task(shutdown_bot(bot))
    
    async def shutdown_bot(bot_instance):
        """BOTの適切な終了処理"""
        try:
            print("BOTを適切に終了中...")
            await bot_instance.close()
            print("BOTを正常に停止しました")
            
            # イベントループの停止前に少し待機（セッション終了のため）
            await asyncio.sleep(0.5)
            
            # イベントループを停止
            loop = asyncio.get_event_loop()
            if not loop.is_closed():
                loop.stop()
        except Exception as e:
            print(f"BOT停止中にエラー: {e}")
            sys.exit(1)
    
    # SIGINT (Ctrl+C) と SIGTERM のハンドラーを設定
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        await bot.start(token)
    except KeyboardInterrupt:
        print("\nキーボードインタラプトを検出しました。BOTを停止しています...")
        await shutdown_bot(bot)
    except Exception as e:
        print(f"BOT実行中にエラーが発生: {e}")
        await shutdown_bot(bot)
        sys.exit(1)


if __name__ == "__main__":
    # ログディレクトリを作成
    os.makedirs('logs', exist_ok=True)
    
    # メイン実行
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nプログラムが中断されました")
    except Exception as e:
        print(f"予期しないエラーが発生: {e}")
        sys.exit(1)
