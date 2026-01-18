"""
Universal Discord AI - Main Bot Module
メインのDiscord BOT実装（非同期処理最適化版）
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
from function_call_handler import FunctionCallHandler
from server_context_cache import ServerContextCache
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
        
        # サーバーコンテキストキャッシュの初期化
        self.server_context_cache = ServerContextCache(self.config)
        
        # ファンクションコールハンドラはsetup_hookで初期化
        self.function_call_handler = None
        
        # BOTインスタンスの管理
        self.character_bots: Dict[str, 'CharacterBot'] = {}
        
        # 非同期処理制御（チャンネル別対応）
        self.max_concurrent_messages = self.config.get('bot_settings.max_concurrent_messages', 10)
        self.max_concurrent_per_channel = self.config.get('bot_settings.max_concurrent_per_channel', 3)
        self.message_semaphore = asyncio.Semaphore(self.max_concurrent_messages)
        
        # チャンネル別のセマフォ制御
        self.channel_semaphores: Dict[int, asyncio.Semaphore] = {}
        self.channel_semaphore_lock = asyncio.Lock()
        
        # メッセージキューイングシステム
        self.message_queue: Dict[int, asyncio.Queue] = {}  # チャンネルID -> キュー
        self.queue_processor_tasks: Dict[int, asyncio.Task] = {}  # チャンネルID -> キュー処理タスク
        self.queue_lock = asyncio.Lock()
        
        # アクティブメッセージタスクの管理
        self.active_message_tasks: Dict[int, MessageTask] = {}
        self.task_cleanup_interval = 300  # 5分ごとにクリーンアップ
        
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
            'queued_messages': 0,
            'server_message_counts': {},
            'channel_message_counts': {},
            'dm_message_counts': 0
        }
        
    async def setup_hook(self):
        """BOT起動時の初期設定"""
        self.logger.info("Universal Discord AI を初期化中...")
        
        # ファンクションコールハンドラの初期化
        self.logger.info(f"設定ファイルの内容: {self.config.config}")
        self.function_call_handler = FunctionCallHandler(self, self.config)
        self.logger.info(f"ファンクションコールハンドラ初期化完了 - 有効: {self.function_call_handler.enabled}")
        
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
        
        # タスククリーンアップタスクを開始
        asyncio.create_task(self._start_task_cleanup())
        
    async def _start_task_cleanup(self):
        """定期的なタスククリーンアップを実行"""
        while True:
            try:
                await asyncio.sleep(self.task_cleanup_interval)
                await self._cleanup_completed_tasks()
            except Exception as e:
                self.logger.error(f"タスククリーンアップ中にエラー: {e}")
    
    async def _get_channel_semaphore(self, channel_id: int) -> asyncio.Semaphore:
        """チャンネル別のセマフォを取得または作成"""
        async with self.channel_semaphore_lock:
            if channel_id not in self.channel_semaphores:
                self.channel_semaphores[channel_id] = asyncio.Semaphore(self.max_concurrent_per_channel)
                self.logger.debug(f"チャンネル {channel_id} 用のセマフォを作成 (制限: {self.max_concurrent_per_channel})")
            return self.channel_semaphores[channel_id]
    
    async def _get_or_create_message_queue(self, channel_id: int) -> asyncio.Queue:
        """チャンネル用のメッセージキューを取得または作成"""
        async with self.queue_lock:
            if channel_id not in self.message_queue:
                self.message_queue[channel_id] = asyncio.Queue()
                self.logger.debug(f"チャンネル {channel_id} 用のメッセージキューを作成")
            return self.message_queue[channel_id]
    
    async def _start_queue_processor(self, channel_id: int):
        """チャンネル用のキュー処理タスクを開始"""
        if channel_id in self.queue_processor_tasks and not self.queue_processor_tasks[channel_id].done():
            return  # 既に実行中
        
        async def process_queue():
            """キュー内のメッセージを順次処理"""
            queue = self.message_queue[channel_id]
            self.logger.debug(f"チャンネル {channel_id} のキュー処理を開始")
            
            while True:
                try:
                    # キューからメッセージを取得（タイムアウト付き）
                    message_data = await asyncio.wait_for(queue.get(), timeout=60.0)
                    
                    if message_data is None:  # 終了シグナル
                        break
                    
                    message, character_name = message_data
                    self.logger.debug(f"キューからメッセージを取得: {message.id} (チャンネル: {channel_id})")
                    
                    # メッセージ処理を逐次実行（完了まで待機）
                    await self._process_queued_message(message, character_name)
                    
                    # キュー処理完了をマーク
                    queue.task_done()
                    
                except asyncio.TimeoutError:
                    # タイムアウト時はキューが空かチェック
                    if queue.empty():
                        self.logger.debug(f"チャンネル {channel_id} のキューが空のため処理を終了")
                        break
                    continue
                except Exception as e:
                    self.logger.error(f"キュー処理中にエラー: {e}")
                    continue
        
        # キュー処理タスクを作成
        self.queue_processor_tasks[channel_id] = asyncio.create_task(process_queue())
        self.logger.debug(f"チャンネル {channel_id} のキュー処理タスクを開始")
    
    async def _process_queued_message(self, message: discord.Message, character_name: str):
        """キューから取得したメッセージを処理"""
        try:
            # チャンネル別セマフォで同時実行数を制御
            channel_semaphore = await self._get_channel_semaphore(message.channel.id)
            
            async with channel_semaphore:
                # グローバルセマフォでも制御
                async with self.message_semaphore:
                    # 処理中タスクとして登録
                    task_info = MessageTask(
                        message_id=message.id,
                        channel_id=message.channel.id,
                        guild_id=message.guild.id if message.guild else None,
                        task=asyncio.current_task(),
                        start_time=datetime.now(),
                        character_name=character_name
                    )
                    self.active_message_tasks[message.id] = task_info
                    
                    # サーバー/チャンネル別統計
                    if message.guild:
                        server_name = message.guild.name
                        channel_name = getattr(message.channel, 'name', 'DM')
                        if server_name not in self.stats['server_message_counts']:
                            self.stats['server_message_counts'][server_name] = 0
                        self.stats['server_message_counts'][server_name] += 1
                        channel_key = f"{server_name}#{channel_name}"
                        if channel_key not in self.stats['channel_message_counts']:
                            self.stats['channel_message_counts'][channel_key] = 0
                        self.stats['channel_message_counts'][channel_key] += 1
                    
                    # メッセージ処理を実行
                    await self._process_message_with_character(message, self.character_bots[character_name], character_name)
                    
                    # 統計情報を更新
                    self.stats['total_messages_processed'] += 1
                    task_info.status = "completed"
                
        except Exception as e:
            self.logger.error(f"キュー処理メッセージの処理中にエラー: {e}")
            self.stats['failed_messages'] += 1
                
    async def _cleanup_completed_tasks(self):
        """完了したタスクをクリーンアップ"""
        current_time = datetime.now()
        tasks_to_remove = []
        
        for message_id, task_info in self.active_message_tasks.items():
            # 完了または失敗したタスクを特定
            if task_info.status in ["completed", "failed"]:
                tasks_to_remove.append(message_id)
            # 長時間実行中のタスクをチェック（30分以上）
            elif (current_time - task_info.start_time) > timedelta(minutes=30):
                self.logger.warning(f"長時間実行中のタスクをキャンセル: {message_id}")
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
        
        # サーバーコンテキストキャッシュの初期化
        if self.server_context_cache.enabled:
            self.logger.info("")
            self.logger.info("🗄️  サーバーコンテキストキャッシュの初期化を開始...")
            for guild in self.guilds:
                try:
                    await self.server_context_cache.initialize_server(guild)
                except Exception as e:
                    self.logger.error(f"❌ サーバーキャッシュ初期化エラー ({guild.name}): {e}")
            self.logger.info("✅ 全サーバーのコンテキストキャッシュ初期化完了")
        
        # BOTステータスをオンラインに設定
        activity = discord.Activity(
            type=discord.ActivityType.competing,
                            name=self.config.get('discord_settings.status', 'みんなの会話')
        )
        await self.change_presence(
            status=discord.Status.online,  # 明示的にオンライン設定
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
        
        # サーバーコンテキストキャッシュを保存
        if self.server_context_cache.enabled:
            self.logger.info("🗄️  サーバーコンテキストキャッシュを保存中...")
            await self.server_context_cache.save_all_caches()
            self.logger.info("✅ キャッシュ保存完了")
        
        # 実行中のタスクをキャンセル
        for task_info in self.active_message_tasks.values():
            if not task_info.task.done():
                task_info.task.cancel()
                self.logger.debug(self.config.get('logging_settings.log_messages.task_cancelled', 'タスクをキャンセル: {message_id}').format(message_id=task_info.message_id))
        
        # キューイングシステムのクリーンアップ
        self.logger.info("キューイングシステムのクリーンアップを開始...")
        
        # 各チャンネルのキューに終了シグナルを送信
        for channel_id, queue in self.message_queue.items():
            try:
                await queue.put(None)  # 終了シグナル
                self.logger.debug(f"チャンネル {channel_id} のキューに終了シグナルを送信")
            except Exception as e:
                self.logger.warning(f"チャンネル {channel_id} のキュー終了シグナル送信エラー: {e}")
        
        # キュー処理タスクの完了を待機
        for channel_id, task in self.queue_processor_tasks.items():
            if not task.done():
                try:
                    await asyncio.wait_for(task, timeout=5.0)
                    self.logger.debug(f"チャンネル {channel_id} のキュー処理タスク完了")
                except asyncio.TimeoutError:
                    self.logger.warning(f"チャンネル {channel_id} のキュー処理タスクがタイムアウト、キャンセル")
                    task.cancel()
                except Exception as e:
                    self.logger.warning(f"チャンネル {channel_id} のキュー処理タスク完了待機エラー: {e}")
        
        self.logger.info("キューイングシステムのクリーンアップ完了")
        
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
                if attempt < 2:  # 最後の試行でない場合は少し待機
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
            self.logger.debug(f"自分のメッセージを無視: {message.author}")
            return
            
        # BOTメッセージは無視
        if message.author.bot:
            self.logger.debug(f"BOTメッセージを無視: {message.author}")
            return
        
        # サーバーコンテキストキャッシュにメッセージを追加（リアルタイム更新）
        if message.guild and self.server_context_cache.enabled:
            self.server_context_cache.add_message(message)
        
        # DMチャットの判定
        is_dm = isinstance(message.channel, discord.DMChannel)
        
        # メンションチェック（自分がメンションされているかどうかのみ）
        is_mentioned = self.user.mentioned_in(message)
        mention_type = "個人メンション"
        
        # DMチャットの場合は常に処理対象とする
        if is_dm:
            # DMチャット機能が無効化されている場合は処理しない
            if not self.config.get('bot_settings.dm_chat_enabled', True):
                self.logger.debug(f"DMチャット機能が無効化されているため、メッセージを無視: {message.author}")
                return
                
            is_mentioned = True
            mention_type = "DMチャット"
            self.logger.debug(f"DMチャット受信: {message.author} -> {message.content}")
        
        # ロールメンションもチェック（サーバー内のみ）
        if not is_mentioned and message.guild:
            bot_member = message.guild.get_member(self.user.id)
            if bot_member:
                for role in bot_member.roles:
                    if role.id in message.raw_role_mentions:
                        is_mentioned = True
                        mention_type = f"ロールメンション ({role.name})"
                        self.logger.debug(f"ロールメンション検知: {role.name}")
                        break
        
        # 現在のメッセージに他ユーザー/ロール/全体(@everyone/@here)へのメンションが含まれるか
        # → 自分へのメンションが無い場合は、連続会話の自動発火を抑止する
        has_other_mentions_in_current = (
            (len(message.mentions) > 0) or
            (len(message.role_mentions) > 0) or
            getattr(message, "mention_everyone", False)
        )

        # 直前がBOTの連続会話発火条件（1つ前が自分=BOT・メンションなし）
        if not is_mentioned and message.guild and not has_other_mentions_in_current:
            try:
                async for prev in message.channel.history(limit=1, before=message):
                    # 直前のメッセージがBOT（自分）なら発火
                    if prev.author == self.user:
                        is_mentioned = True
                        mention_type = "連続会話（直前がBOT）"
                        self.logger.debug("直前がBOTのためトリガー")
                    break
            except Exception as e:
                self.logger.debug(f"連続会話（直前BOT）条件評価エラー: {e}")

        # 直前がBOTの連続会話発火条件（既存の設定を使用）
        if (not is_mentioned and message.guild and not has_other_mentions_in_current and 
            self.config.get('bot_settings.continuous_conversation_enabled', False)):
            try:
                async for prev in message.channel.history(limit=1, before=message):
                    # 直前のメッセージがBOT（自分）なら発火
                    if prev.author == self.user:
                        is_mentioned = True
                        mention_type = "連続会話（直前がBOT）"
                        self.logger.debug("直前がBOTのためトリガー - 既存設定continuous_conversation_enabled使用")
                    break
            except Exception as e:
                self.logger.debug(f"連続会話（直前BOT）条件評価エラー: {e}")

        # 前のメッセージがBOTかどうかをチェック（設定で有効化されている場合のみ）
        # ただし、自分がメンションされていない場合は連続会話でもトリガーしない
        is_previous_bot = False
        if self.config.get('bot_settings.continuous_conversation_enabled', True) and is_mentioned:
            is_previous_bot = await self.is_previous_message_from_bot(message)
            if is_previous_bot:
                mention_type = "連続会話（前のメッセージがBOT）"
                # is_mentionedは既にTrueなので変更不要
        
        # 詳細ログ出力（DMチャットの場合は特別処理）
        if message.guild:
            self.detailed_logger.log_mention_detection(
                server_name=message.guild.name,
                channel_name=getattr(message.channel, 'name', 'DM'),
                user_name=message.author.display_name,
                mention_type=mention_type,
                message_content=message.content
            )
        elif is_dm:
            # DMチャット用のログ出力
            self.detailed_logger.log_mention_detection(
                server_name="DMチャット",
                channel_name=f"@{message.author.display_name}",
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
        
        # すべてのメッセージをチャンネル別キューに投入して逐次処理
        asyncio.create_task(self._handle_mention_async(message))
    
    async def _handle_mention_async(self, message: discord.Message):
        """メンション時の返答処理（非同期版・チャンネル別並列処理対応）"""
        channel_id = message.channel.id
        
        try:
            # すべてのメッセージはキューに追加し、逐次処理
            queue = await self._get_or_create_message_queue(channel_id)
            
            # 使用する人格を決定（DMはDM用人格、その他はデフォルト人格）
            character_name = (
                self.config.get('bot_settings.dm_character', 'friendly')
                if isinstance(message.channel, discord.DMChannel)
                else self.config.get('character_settings.default_character', 'friendly')
            )
            
            # キューにメッセージを追加
            await queue.put((message, character_name))
            self.stats['queued_messages'] += 1
            
            # キュー処理タスクを開始（まだ開始されていない場合）
            await self._start_queue_processor(channel_id)
            
            return
            
        except Exception as e:
            self.logger.error(f"メンション処理の開始中にエラー: {e}")
            try:
                await message.reply("申し訳ございません。メッセージ処理の開始に失敗しました。")
            except:
                pass
    
    async def _handle_dm_message(self, message: discord.Message):
        """DMチャット専用の処理"""
        try:
            # DM用の人格を決定
            dm_character = self.config.get('bot_settings.dm_character', 'friendly')
            
            # 遅延設定（スパム防止）
            dm_delay = self.config.get('bot_settings.dm_response_delay', 1.0)
            if dm_delay > 0:
                await asyncio.sleep(dm_delay)
            
            # 既存の処理フローを再利用
            character_bot = self.character_bots.get(dm_character)
            if not character_bot:
                await message.reply("申し訳ございません。人格設定の読み込みに失敗しました。")
                return
            
            # メッセージ処理タスクを作成
            task = asyncio.create_task(
                self._process_message_with_character(message, character_bot, dm_character)
            )
            
            # タスク情報を記録
            task_info = MessageTask(
                message_id=message.id,
                channel_id=message.channel.id,
                guild_id=None,  # DMチャットはguild_idなし
                task=task,
                start_time=datetime.now(),
                character_name=dm_character
            )
            
            self.active_message_tasks[message.id] = task_info
            
            # タスク完了まで待機
            await task
            
            # 成功時の統計更新
            self.stats['total_messages_processed'] += 1
            self.stats['dm_message_counts'] += 1
            task_info.status = "completed"
            
            self.logger.info(f"DMチャット返答完了: {message.author} -> {dm_character}人格")
            
        except asyncio.CancelledError:
            # タスクがキャンセルされた場合
            if message.id in self.active_message_tasks:
                self.active_message_tasks[message.id].status = "cancelled"
            self.logger.info(f"DMチャットメッセージ処理がキャンセルされました: {message.id}")
            
        except Exception as e:
            # エラー時の統計更新
            self.stats['failed_messages'] += 1
            if message.id in self.active_message_tasks:
                self.active_message_tasks[message.id].status = "failed"
            
            # エラーログ
            self.detailed_logger.log_error_detail(
                error=e,
                context="DMチャットメッセージ処理",
                additional_info=f"ユーザー: {message.author.display_name}"
            )
            
            try:
                await message.reply("申し訳ございません。エラーが発生しました。")
            except:
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
                
                # 画像添付の処理
                image_attachments = []
                if message.attachments:
                    self.logger.info(f"🖼️ Discord添付ファイル検出: {len(message.attachments)}個")
                    
                    # 各添付ファイルの詳細情報をログ出力
                    for i, attachment in enumerate(message.attachments):
                        self.logger.info(f"添付ファイル {i+1}:")
                        self.logger.info(f"  - ファイル名: {attachment.filename}")
                        self.logger.info(f"  - サイズ: {attachment.size} bytes")
                        self.logger.info(f"  - URL: {attachment.url}")
                        self.logger.info(f"  - コンテンツタイプ: {getattr(attachment, 'content_type', 'unknown')}")
                        self.logger.info(f"  - プロキシURL: {attachment.proxy_url}")
                    
                    # 画像処理用のデータを生成（非同期処理）
                    image_attachments = await self.openai_handler.process_image_attachments(message.attachments)
                    
                    if image_attachments:
                        self.logger.info(f"✅ 画像処理対象: {len(image_attachments)}個の画像")
                        # 処理対象画像の詳細をログ出力
                        for i, img in enumerate(image_attachments):
                            self.logger.info(f"処理対象画像 {i+1}: {img['filename']} (URL: {img['url']})")
                    else:
                        self.logger.warning("⚠️ 画像ファイルとして認識されませんでした")
                else:
                    self.logger.info("📝 画像添付なし")

                # リプライ先メッセージの画像添付も処理
                if message.reference and getattr(message.reference, 'message_id', None):
                    try:
                        referenced_message = await message.channel.fetch_message(message.reference.message_id)
                        if referenced_message:
                            # 返信先がBOTの場合は既存方針に合わせてスキップ
                            if referenced_message.author and referenced_message.author.bot:
                                self.logger.debug(f"返信先メッセージはBOTのため画像取得をスキップ: {referenced_message.author}")
                            else:
                                if referenced_message.attachments:
                                    self.logger.info(f"🖼️ リプライ先の添付ファイル検出: {len(referenced_message.attachments)}個")
                                    reply_images = await self.openai_handler.process_image_attachments(referenced_message.attachments)
                                    if reply_images:
                                        existing_urls = {img['url'] for img in image_attachments} if image_attachments else set()
                                        new_images = [img for img in reply_images if img.get('url') not in existing_urls]
                                        if new_images:
                                            image_attachments.extend(new_images)
                                            self.logger.info(f"✅ リプライ先から {len(new_images)} 個の画像を追加（合計: {len(image_attachments)}）")
                                    else:
                                        self.logger.info("📝 リプライ先に画像として認識できる添付はありませんでした")
                                else:
                                    self.logger.debug("リプライ先に添付ファイルはありません")
                    except discord.NotFound:
                        self.logger.warning(f"返信先メッセージが見つかりません（画像取得スキップ）: {message.reference.message_id}")
                    except discord.Forbidden:
                        self.logger.warning(f"返信先メッセージへのアクセス権限がありません（画像取得スキップ）: {message.reference.message_id}")
                    except Exception as e:
                        self.logger.error(f"返信先メッセージの画像取得中にエラー: {e}")
                
                # キャラクター選択の詳細ログ
                if message.guild:
                    available_characters = list(self.character_bots.keys())
                    self.detailed_logger.log_character_selection(
                        server_name=message.guild.name,
                        channel_name=getattr(message.channel, 'name', 'DM'),
                        selected_character=character_name,
                        available_characters=available_characters
                    )
                
                # 返答生成（画像添付がある場合は画像処理対応）
                await character_bot.generate_response(
                    message=message,
                    channel_info=channel_info,
                    chat_history=chat_history,
                    image_attachments=image_attachments
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
                channel_display = getattr(message.channel, 'name', 'DM')
                self.detailed_logger.log_error_detail(
                    error=e,
                    context=f"返答生成 - サーバー: {message.guild.name}, チャンネル: #{channel_display}",
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
        # DMチャンネルの場合
        if isinstance(channel, discord.DMChannel):
            recipient_name = "Unknown User"
            if channel.recipient:
                recipient_name = channel.recipient.display_name
            info = {
                'name': f"DM with {recipient_name}",
                'type': 'private',
                'topic': 'ダイレクトメッセージ',
                'id': channel.id
            }
        # グループDMチャンネルの場合
        elif isinstance(channel, discord.GroupChannel):
            info = {
                'name': channel.name if channel.name else f"Group DM ({len(channel.recipients)} members)",
                'type': 'group',
                'topic': 'グループダイレクトメッセージ',
                'id': channel.id
            }
        else:
            # 通常のチャンネル/スレッドの処理
            info = {
                'name': getattr(channel, 'name', 'Unknown Channel'),
                'type': str(channel.type),
                'topic': getattr(channel, 'topic', None) or '設定されていません',
                'id': channel.id
            }
            
            # スレッドの場合は親チャンネル情報も取得
            if isinstance(channel, discord.Thread):
                parent_name = getattr(channel.parent, 'name', 'Unknown') if channel.parent else 'Unknown'
                owner_name = channel.owner.display_name if channel.owner else '不明'
                info['parent_channel'] = parent_name
                info['thread_starter'] = owner_name
            
        return info
        
    async def get_chat_history(self, channel) -> List[Dict]:
        """チャット履歴を取得"""
        history_limit = self.config.get('general_settings.chat_history_limit', 100)
        history = []
        
        try:
            async for message in channel.history(limit=history_limit):
                # BOTメッセージは履歴から除外
                if not message.author or message.author.bot:
                    continue
                    
                # 安全にdisplay_nameを取得
                author_name = "Unknown User"
                if message.author:
                    author_name = getattr(message.author, 'display_name', 'Unknown User')
                
                history_item = {
                    'author': author_name,
                    'content': message.content or "",
                    'timestamp': message.created_at.isoformat(),
                    'attachments': len(message.attachments) > 0 if message.attachments else False,
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
        
        # ファンクションコール機能確認コマンド
        if content == f"{command_prefix} functions":
            await self.handle_functions_command(message)
    
    async def handle_status_command(self, message: discord.Message):
        """ステータス確認コマンドの処理（非同期処理情報追加・キューイング対応）"""
        try:
            # OpenAI API接続状態を取得
            openai_status = self.openai_handler.get_connection_status()
            rate_limit_status = self.openai_handler.get_rate_limit_status()
            
            # 現在の同時処理状況
            current_concurrent = len(self.active_message_tasks)
            processing_tasks = [t for t in self.active_message_tasks.values() if t.status == "processing"]
            
            # チャンネル別の処理状況
            channel_processing_stats = {}
            for task in self.active_message_tasks.values():
                if task.status == "processing":
                    channel_id = task.channel_id
                    if channel_id not in channel_processing_stats:
                        channel_processing_stats[channel_id] = 0
                    channel_processing_stats[channel_id] += 1
            
            # キューイング状況
            queued_messages_total = sum(queue.qsize() for queue in self.message_queue.values())
            active_queues = len([q for q in self.message_queue.values() if not q.empty()])
            
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
            
            # チャンネル別処理状況
            channel_processing_info = ""
            if channel_processing_stats:
                channel_processing_info = "\n🔧 **チャンネル別処理状況**\n"
                for channel_id, count in sorted(channel_processing_stats.items(), key=lambda x: x[1], reverse=True):
                    channel_name = f"チャンネル{channel_id}"
                    try:
                        channel = self.get_channel(channel_id)
                        if channel:
                            channel_name = f"#{channel.name}"
                    except:
                        pass
                    channel_processing_info += f"• {channel_name}: {count}件処理中\n"
            
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
• チャンネル別最大同時処理数: {self.max_concurrent_per_channel}
• 現在の同時処理数: {current_concurrent}
• 処理中タスク: {len(processing_tasks)}
• 総処理メッセージ数: {self.stats['total_messages_processed']}
• DMチャット処理数: {self.stats['dm_message_counts']}
• 平均応答時間: {self.stats['average_response_time']:.2f}秒
• ピーク同時処理数: {self.stats['concurrent_messages_peak']}
• 失敗メッセージ数: {self.stats['failed_messages']}

📋 **キューイング状況**
• キュー内メッセージ数: {queued_messages_total}
• アクティブキュー数: {active_queues}
• キュー処理済みメッセージ数: {self.stats['queued_messages']}{channel_processing_info}{server_stats}{channel_stats}"""

            # サーバーコンテキストキャッシュ情報を追加
            if self.server_context_cache.enabled and message.guild:
                cache_stats = self.server_context_cache.get_cache_stats(message.guild.id)
                if cache_stats:
                    status_info += f"""

🗄️ **サーバーコンテキストキャッシュ**
• 状態: 有効
• キャッシュメッセージ数: {cache_stats['message_count']}
• キャッシュチャンネル数: {cache_stats['channel_count']}
• キャッシュユーザー数: {cache_stats['user_count']}
• 最終更新: {cache_stats['last_updated']}"""
                else:
                    status_info += """

🗄️ **サーバーコンテキストキャッシュ**
• 状態: 初期化中または未初期化"""
            elif not self.server_context_cache.enabled:
                status_info += """

🗄️ **サーバーコンテキストキャッシュ**
• 状態: 無効"""
            
            await message.reply(status_info)
            
        except Exception as e:
            self.logger.error(f"ステータスコマンド処理エラー: {e}")
            await message.reply("申し訳ございません。ステータス情報の取得に失敗しました。")
    
    async def handle_functions_command(self, message: discord.Message):
        """ファンクションコール機能確認コマンドの処理"""
        try:
            if not self.function_call_handler.enabled:
                await message.reply("❌ ファンクションコール機能は無効化されています")
                return
            
            # 利用可能な関数の一覧を取得
            functions = self.function_call_handler.get_function_definitions()
            
            if not functions:
                await message.reply("❌ 利用可能な関数がありません")
                return
            
            # 関数一覧を構築
            functions_info = "🔧 **利用可能なファンクションコール機能**\n\n"
            for func in functions:
                functions_info += f"**{func['name']}**\n"
                functions_info += f"説明: {func['description']}\n"
                if 'parameters' in func and 'properties' in func['parameters']:
                    required = func['parameters'].get('required', [])
                    properties = func['parameters']['properties']
                    functions_info += "パラメータ:\n"
                    for prop_name, prop_info in properties.items():
                        required_mark = " (必須)" if prop_name in required else ""
                        functions_info += f"• {prop_name}{required_mark}: {prop_info.get('description', '説明なし')}\n"
                functions_info += "\n"
            
            functions_info += f"⚠️ **注意**: 管理者権限が必要です"
            
            await message.reply(functions_info)
            
        except Exception as e:
            self.logger.error(f"ファンクションコール機能確認コマンド処理エラー: {e}")
            await message.reply("申し訳ございません。ファンクションコール機能の確認に失敗しました。")
    
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
    
    def _get_safe_channel_name(self, channel) -> str:
        """チャンネル名を安全に取得"""
        if isinstance(channel, discord.DMChannel):
            return "DM"
        elif isinstance(channel, discord.GroupChannel):
            return "GroupDM"
        elif hasattr(channel, 'name'):
            return channel.name
        return "Unknown"
    
    def _get_safe_user_name(self, user) -> str:
        """ユーザー名を安全に取得"""
        if not user:
            return "Unknown User"
        return getattr(user, 'display_name', 'Unknown User')
        
    async def generate_response(self, message: discord.Message, channel_info: Dict, chat_history: List[Dict], image_attachments: List[Dict] = None):
        """返答を生成して送信（非同期最適化版）"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            # 画像添付の処理ログ
            if image_attachments:
                self.logger.info(f"🖼️ 画像付きメッセージを処理中 - 画像数: {len(image_attachments)}")
                for i, img in enumerate(image_attachments):
                    self.logger.info(f"画像 {i+1}: {img['filename']} (サイズ: {img['size']} bytes)")
            
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
                
            # ファンクションコールが有効かチェック
            function_definitions = self.parent_bot.function_call_handler.get_function_definitions()
            use_function_calls = len(function_definitions) > 0 and self.parent_bot.function_call_handler.enabled
            
            # ファンクションコール機能の状態をログ出力
            self.logger.info(f"ファンクションコール機能チェック - 有効: {use_function_calls}, 利用可能関数数: {len(function_definitions)}")
            
            # 統合されたレスポンス生成を実行
            channel_display = getattr(message.channel, 'name', 'DM')
            self.logger.info(f"🚀 統合レスポンス生成を開始 - ユーザー: {message.author.display_name}, チャンネル: #{channel_display}")
            response_message, full_response = await self._generate_unified_response(
                message, context, channel_info, chat_history, reply_context, image_attachments
            )
                
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
                # メッセージ送信の成功/失敗を正確に判定
                message_sent_success = (
                    response_message is not None and 
                    hasattr(response_message, 'id') and 
                    response_message.id is not None
                )
                
                channel_display = getattr(message.channel, 'name', 'DM')
                self.parent_bot.detailed_logger.log_message_generation(
                    server_name=message.guild.name,
                    channel_name=channel_display,
                    user_name=message.author.display_name,
                    character_name=self.character_name,
                    response_time=response_time,
                    token_count=estimated_output_tokens,
                    message_sent=message_sent_success,
                    input_tokens=estimated_input_tokens,
                    output_tokens=estimated_output_tokens,
                    response_content=full_response
                )
                
        except Exception as e:
            # エラー時の詳細ログ
            response_time = asyncio.get_event_loop().time() - start_time
            if message.guild:
                channel_display = getattr(message.channel, 'name', 'DM')
                self.parent_bot.detailed_logger.log_error_detail(
                    error=e,
                    context=f"返答生成 - サーバー: {message.guild.name}, チャンネル: #{channel_display}",
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
        
        # サーバーコンテキストキャッシュを使用（有効な場合）
        server_context = None
        if message.guild and self.parent_bot.server_context_cache.enabled:
            server_context = self.parent_bot.server_context_cache.get_context(message.guild.id)
        
        if server_context:
            # サーバー全体のコンテキストを使用
            self.logger.info("🗄️  サーバーコンテキストキャッシュを使用")
            context_parts.append(server_context)
        else:
            # 従来の方式：チャンネル情報と履歴を使用
            self.logger.info("📝 従来のチャンネル履歴を使用")
            
            # チャンネル情報
            context_parts.append(f"\n# チャンネル情報")
            context_parts.append(f"チャンネル名: {channel_info['name']}")
            context_parts.append(f"チャンネルトピック: {channel_info['topic']}")
            context_parts.append(f"チャンネルタイプ: {channel_info['type']}")
            
            # チャット履歴
            if chat_history:
                context_parts.append(f"\n# 最近のチャット履歴")
                # 取得上限（general_settings.chat_history_limit）と同じ件数をAIコンテキストにも使用
                history_count = self.parent_bot.config.get('general_settings.chat_history_limit', 100)
                for item in chat_history[-history_count:]:
                    # 返信先のメッセージは履歴から除外（重複を避けるため）
                    if reply_context and item['id'] == reply_context['id']:
                        continue
                    context_parts.append(f"{item['author']}: {item['content']}")
        
        # 返信先のメッセージ（存在する場合）
        if reply_context:
            context_parts.append(f"\n# 返信先のメッセージ")
            context_parts.append(f"{reply_context['author']}: {reply_context['content']}")
            if reply_context.get('attachments', False):
                context_parts.append(f"（添付ファイルあり）")
            context_parts.append(f"（このメッセージへの返信として、以下のメッセージが送信されました）")
                
        # 現在のメッセージ
        context_parts.append(f"\n# 現在のメッセージ")
        context_parts.append(f"{message.author.display_name}: {message.content}")
        
        # 返信の場合の指示
        if reply_context:
            context_parts.append(f"\n上記の返信先メッセージに対して、設定された人格で適切に返答してください。")
        else:
            context_parts.append(f"\n上記のメッセージに対して、設定された人格で返答してください。")
        
        return "\n".join(context_parts)
    
    async def _generate_unified_response(
        self, 
        message: discord.Message, 
        context: str, 
        channel_info: Dict, 
        chat_history: List[Dict], 
        reply_context: Dict,
        image_attachments: List[Dict] = None
    ) -> tuple[discord.Message, str]:
        """統合されたレスポンス生成（ファンクションコール対応 + ストリーミング）"""
        try:
            # ファンクション定義を取得
            function_definitions = self.parent_bot.function_call_handler.get_function_definitions()
            use_function_calls = len(function_definitions) > 0 and self.parent_bot.function_call_handler.enabled
            
            self.logger.info(f"🔧 統合レスポンス生成開始 - ファンクションコール: {use_function_calls}, 関数数: {len(function_definitions)}")
            
            # 画像添付がある場合のログ
            if image_attachments:
                self.logger.info(f"🖼️ 画像付きレスポンス生成 - 画像数: {len(image_attachments)}")
            
            if use_function_calls:
                # ファンクションコール対応のレスポンス生成（並列処理とタイムアウト短縮）
                self.logger.info(f"🚀 ファンクションコール対応レスポンス生成を開始（タイムアウト: 10秒）")
                
                # ファンクションコールとストリーミングを並列実行
                function_call_task = asyncio.create_task(
                    self.parent_bot.openai_handler.generate_response_with_function_calls(
                        context=context,
                        character_data=self.character_data,
                        function_definitions=function_definitions,
                        model=self.parent_bot.config.get('openai_settings.model', 'google/gemini-2.5-flash-lite'),
                        max_completion_tokens=self.parent_bot.config.get('openai_settings.max_completion_tokens', 16000),  # 設定ファイルから読み込み
                        image_attachments=image_attachments
                    )
                )
                
                # 短いタイムアウトでファンクションコールを待機
                function_call_timeout = self.parent_bot.config.get('openai_settings.function_call_timeout', 30)
                try:
                    response_data = await asyncio.wait_for(function_call_task, timeout=function_call_timeout)
                    if response_data["success"]:
                        # 成功した場合はファンクションコール処理を継続
                        pass
                    else:
                        # エラーの場合はストリーミングレスポンスにフォールバック
                        self.logger.warning(f"❌ ファンクションコールレスポンス生成失敗: {response_data['error']}")
                        self.logger.info(f"🔄 ストリーミングレスポンスにフォールバック")
                        return await self._generate_streaming_response_internal(message, context, image_attachments)
                        
                except asyncio.TimeoutError:
                    # タイムアウトした場合は即座にストリーミングに移行
                    self.logger.info(f"⏰ ファンクションコール処理がタイムアウト（{function_call_timeout}秒）、ストリーミングに即座に移行")
                    return await self._generate_streaming_response_internal(message, context, image_attachments)
                
                # レスポンスからツールコールをチェック
                choices = response_data.get("choices", [])
                if not choices:
                    self.logger.warning(f"⚠️ OpenAI APIレスポンスにchoicesがありません")
                    self.logger.info(f"🔄 ストリーミングレスポンスにフォールバック")
                    return await self._generate_streaming_response_internal(message, context, image_attachments)
                
                choice = choices[0]
                message_content = choice.get("message", {})
                tool_calls = message_content.get("tool_calls", [])
                
                if tool_calls:
                    self.logger.info(f"🔧 ツールコールを検出: {len(tool_calls)}個の関数呼び出し")
                    for i, tool_call in enumerate(tool_calls):
                        function_name = tool_call.get("function", {}).get("name", "不明")
                        self.logger.info(f"  📋 ツールコール {i+1}: {function_name}")
                    
                    # ツールコールがある場合の処理
                    return await self._handle_tool_calls(message, tool_calls, message_content, context, image_attachments)
                else:
                    self.logger.info(f"📝 ツールコールなし - テキストレスポンスを処理")
                    # 通常のテキストレスポンス
                    content = message_content.get("content", "")
                    if content:
                        self.logger.info(f"✅ テキストレスポンスを送信: {len(content)}文字")
                        response_message = await message.reply(content)
                        return response_message, content
                    else:
                        self.logger.warning(f"⚠️ テキストレスポンスが空です")
                        self.logger.info(f"🔄 ストリーミングレスポンスにフォールバック")
                        return await self._generate_streaming_response_internal(message, context, image_attachments)
            else:
                # ストリーミングレスポンス生成
                self.logger.info(f"📝 ストリーミングレスポンス生成を開始")
                return await self._generate_streaming_response_internal(message, context, image_attachments)
                    
        except Exception as e:
            self.logger.error(f"統合レスポンス生成エラー: {e}")
            # エラーの場合はストリーミングレスポンスにフォールバック
            return await self._generate_streaming_response_internal(message, context, image_attachments)
    
    async def _generate_streaming_response_internal(self, message: discord.Message, context: str, image_attachments: List[Dict] = None) -> tuple[discord.Message, str]:
        """内部用ストリーミングレスポンス生成（画像添付対応）"""
        response_message = None
        full_response = ""
        is_first_chunk = True
        
        # 画像添付がある場合のログ
        if image_attachments:
            self.logger.info(f"🖼️ 画像付きストリーミングレスポンス生成開始 - 画像数: {len(image_attachments)}")
        
        async for chunk in self.parent_bot.openai_handler.generate_streaming_response(
            context=context,
            character_data=self.character_data,
            model=self.parent_bot.config.get('openai_settings.model', 'google/gemini-2.5-flash-lite'),
            max_completion_tokens=self.parent_bot.config.get('openai_settings.max_completion_tokens', 16000),  # 設定ファイルから読み込み
            image_attachments=image_attachments
        ):
            full_response += chunk
            
            # 最初のチャンクの場合、メッセージを送信
            if is_first_chunk:
                try:
                    response_message = await message.reply(full_response[:2000])
                    is_first_chunk = False
                    self.logger.debug(f"初回メッセージ送信完了: {len(full_response)}文字")
                except discord.Forbidden as e:
                    self.logger.error(f"❌ 初回メッセージ送信失敗（権限不足）: {e}")
                    # 権限不足の場合は、次のチャンクで再試行
                    continue
                except discord.HTTPException as e:
                    self.logger.error(f"❌ 初回メッセージ送信失敗（HTTPエラー）: {e}")
                    # HTTPエラーの場合は、次のチャンクで再試行
                    continue
                except Exception as e:
                    self.logger.error(f"❌ 初回メッセージ送信失敗（予期しないエラー）: {e}")
                    # 予期しないエラーの場合は、次のチャンクで再試行
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
                self.logger.info(f"🔄 フォールバックメッセージ送信を試行: {len(full_response)}文字")
                response_message = await message.reply(full_response[:2000])
                self.logger.info(f"✅ フォールバックメッセージ送信成功")
            except discord.Forbidden as e:
                self.logger.error(f"❌ フォールバックメッセージ送信失敗（権限不足）: {e}")
            except discord.HTTPException as e:
                self.logger.error(f"❌ フォールバックメッセージ送信失敗（HTTPエラー）: {e}")
            except Exception as e:
                self.logger.error(f"❌ フォールバックメッセージ送信失敗（予期しないエラー）: {e}")
        elif response_message and full_response:
            try:
                await response_message.edit(content=full_response[:2000])
            except discord.NotFound:
                self.logger.warning(f"⚠️ メッセージ編集失敗（メッセージが見つかりません）")
            except discord.Forbidden as e:
                self.logger.error(f"❌ メッセージ編集失敗（権限不足）: {e}")
            except discord.HTTPException as e:
                self.logger.error(f"❌ メッセージ編集失敗（HTTPエラー）: {e}")
            except Exception as e:
                self.logger.error(f"❌ メッセージ編集失敗（予期しないエラー）: {e}")
        
        return response_message, full_response
    
    async def _handle_tool_calls(
        self, 
        message: discord.Message, 
        tool_calls: List[Dict], 
        message_content: Dict, 
        context: str,
        image_attachments: List[Dict] = None
    ) -> tuple[discord.Message, str]:
        """ツールコールを処理"""
        try:
            # 最初のツールコールを処理
            tool_call = tool_calls[0]
            function_name = tool_call.get("function", {}).get("name")
            arguments = tool_call.get("function", {}).get("arguments", "{}")
            
            self.logger.info(f"🔧 ツールコール処理開始 - 関数: {function_name}")
            self.logger.info(f"📋 引数: {arguments}")
            
            # 引数をパース
            import json
            try:
                parsed_args = json.loads(arguments)
                self.logger.info(f"✅ 引数のパース成功: {parsed_args}")
            except json.JSONDecodeError as e:
                self.logger.error(f"❌ 引数のパース失敗: {e}")
                parsed_args = {}
            
            # ファンクションコールを実行
            self.logger.info(f"🚀 ファンクションコール実行開始: {function_name}")
            result = await self.parent_bot.function_call_handler.execute_function_call(
                function_name, parsed_args, message
            )
            
            # 結果をログ出力
            self.logger.info(f"📊 ファンクションコール実行結果: {result}")
            
            # 結果をフォーマット
            result_message = self.parent_bot.function_call_handler.format_function_result_for_ai(result)
            self.logger.info(f"📝 フォーマット済み結果: {result_message}")
            
            # 結果を送信
            self.logger.info(f"📤 結果をDiscordに送信中...")
            response_message = await message.reply(result_message)
            self.logger.info(f"✅ 結果送信完了")
            
            return response_message, result_message
            
        except Exception as e:
            # 詳細なエラー情報をログに出力
            self.logger.error(f"ツールコール処理エラー: {e}")
            self.logger.error(f"エラータイプ: {type(e).__name__}")
            self.logger.error(f"エラー詳細: {str(e)}")
            
            # エラーのトレースバック情報も出力
            import traceback
            self.logger.error(f"トレースバック: {traceback.format_exc()}")
            
            # エラーの属性情報も出力（利用可能な場合）
            if hasattr(e, '__dict__'):
                self.logger.error(f"エラー属性: {e.__dict__}")
            
            error_message = f"ツールコールの処理中にエラーが発生しました: {str(e)}"
            response_message = await message.reply(error_message)
            return response_message, error_message
    



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
