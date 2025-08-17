"""
Universal Discord AI - Main Bot Module
メインのDiscord BOT実装
"""

import asyncio
import logging
import os
import signal
import sys
from typing import Dict, List, Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

from character_manager import CharacterManager
from openai_handler import OpenAIHandler
from utils import ConfigManager, setup_logging, TokenCounter, DetailedLogger

# 環境変数を読み込み
load_dotenv('env.local')

class UniversalDiscordAI(commands.Bot):
    """Universal Discord AI Bot クラス"""
    
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
        self.openai_handler = OpenAIHandler()
        self.token_counter = TokenCounter()
        
        # BOTインスタンスの管理
        self.character_bots: Dict[str, 'CharacterBot'] = {}
        self.active_responses: Dict[int, asyncio.Task] = {}
        
        # ログ設定
        self.logger = setup_logging()
        self.detailed_logger = DetailedLogger(self.config)
        
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
        
    async def on_ready(self):
        """BOT接続完了時の処理"""
        self.logger.info(f'{self.user} として Discord に接続しました')
        self.logger.info(f'サーバー数: {len(self.guilds)}')
        
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
            type=discord.ActivityType.watching,
            name=self.config.get('discord_settings.status', 'チャンネルを監視中...')
        )
        await self.change_presence(
            status=discord.Status.online,  # 明示的にオンライン設定
            activity=activity
        )
        self.logger.info("BOTステータスをオンラインに設定しました")
        
        # 料金体系のサマリーを表示
        cost_summary = self.detailed_logger.cost_calculator.get_cost_summary()
        self.logger.info(cost_summary)
        
        # OpenAI API接続状態のヘルスモニタリングを開始
        asyncio.create_task(self.openai_handler.start_health_monitoring())
        self.logger.info("OpenAI API接続状態のヘルスモニタリングを開始しました")
    
    async def on_disconnect(self):
        """Discord切断時の処理"""
        self.logger.warning("Discordから切断されました")
    
    async def on_resumed(self):
        """Discord再接続時の処理"""
        self.logger.info("Discordに再接続しました")
        # 再接続時にステータスを再設定
        try:
            activity = discord.Activity(
                type=discord.ActivityType.watching,
                name=self.config.get('discord_settings.status', 'チャンネルを監視中...')
            )
            await self.change_presence(
                status=discord.Status.online,
                activity=activity
            )
            self.logger.info("再接続時にBOTステータスをオンラインに再設定しました")
        except Exception as e:
            self.logger.warning(f"再接続時のステータス設定エラー: {e}")
    
    async def close(self):
        """BOT終了時の処理"""
        self.logger.info("BOTを終了中...")
        
        # ステータスをオフラインに設定（複数回試行）
        for attempt in range(3):
            try:
                await self.change_presence(
                    status=discord.Status.offline,
                    activity=None
                )
                self.logger.info("BOTステータスをオフラインに設定しました")
                break
            except discord.ConnectionClosed:
                self.logger.info("Discord接続が既に閉じられています")
                break
            except Exception as e:
                self.logger.warning(f"ステータス変更エラー (試行 {attempt + 1}/3): {e}")
                if attempt < 2:  # 最後の試行でない場合は少し待機
                    await asyncio.sleep(0.5)
        
        # 親クラスの終了処理を呼び出し
        try:
            await super().close()
        except Exception as e:
            self.logger.warning(f"親クラスの終了処理でエラー: {e}")
        
        # aiohttpセッションの適切な終了処理
        try:
            if hasattr(self, 'http') and hasattr(self.http, '_HTTPClient__session'):
                session = self.http._HTTPClient__session
                if not session.closed:
                    await session.close()
                    self.logger.info("aiohttpセッションを適切に終了しました")
        except Exception as e:
            self.logger.warning(f"aiohttpセッション終了処理でエラー: {e}")
        
    async def on_message(self, message: discord.Message):
        """メッセージ受信時の処理"""
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
        
        # 前のメッセージがBOTかどうかをチェック（設定で有効化されている場合のみ）
        is_previous_bot = False
        if self.config.get('bot_settings.continuous_conversation_enabled', True):
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
            
        # 返答処理を開始
        await self.handle_mention(message)
        
    async def handle_mention(self, message: discord.Message):
        """メンション時の返答処理"""
        start_time = asyncio.get_event_loop().time()
        
        try:
            # typing indicator開始（入力中ステータスを表示）
            async with message.channel.typing():
                # チャンネル情報を取得
                channel_info = await self.get_channel_info(message.channel)
                
                # チャット履歴を取得
                chat_history = await self.get_chat_history(message.channel)
                
                # 使用する人格を決定（現在はデフォルト人格を使用）
                character_name = self.config.get('character_settings.default_character', 'friendly')
                character_bot = self.character_bots.get(character_name)
                
                if not character_bot:
                    await message.reply("申し訳ございません。人格設定の読み込みに失敗しました。")
                    return
                
                # キャラクター選択の詳細ログ
                if message.guild:
                    available_characters = list(self.character_bots.keys())
                    self.detailed_logger.log_character_selection(
                        server_name=message.guild.name,
                        channel_name=message.channel.name,
                        selected_character=character_name,
                        available_characters=available_characters
                    )
                
                # 返答生成タスクを開始
                response_task = asyncio.create_task(
                    character_bot.generate_response(
                        message=message,
                        channel_info=channel_info,
                        chat_history=chat_history
                    )
                )
                
                # アクティブな返答として管理
                self.active_responses[message.id] = response_task
                
                # 返答完了まで待機
                await response_task
                
                # 成功時のレスポンス時間ログ
                response_time = asyncio.get_event_loop().time() - start_time
                if message.guild:
                    self.detailed_logger.log_response_time(
                        operation="メンション処理",
                        response_time=response_time,
                        success=True
                    )
                
        except Exception as e:
            # エラー時の詳細ログ
            response_time = asyncio.get_event_loop().time() - start_time
            if message.guild:
                self.detailed_logger.log_error_detail(
                    error=e,
                    context=f"メンション処理 - サーバー: {message.guild.name}, チャンネル: #{message.channel.name}",
                    additional_info=f"ユーザー: {message.author.display_name}, レスポンス時間: {response_time:.2f}秒"
                )
            else:
                self.detailed_logger.log_error_detail(
                    error=e,
                    context="メンション処理 - DM",
                    additional_info=f"ユーザー: {message.author.display_name}, レスポンス時間: {response_time:.2f}秒"
                )
            
            await message.reply(f"エラーが発生しました: {str(e)}")
        finally:
            # タスクをクリーンアップ
            if message.id in self.active_responses:
                del self.active_responses[message.id]
                
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
        """ステータス確認コマンドの処理"""
        try:
            # OpenAI API接続状態を取得
            openai_status = self.openai_handler.get_connection_status()
            rate_limit_status = self.openai_handler.get_rate_limit_status()
            
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
• 利用可能人格: {', '.join(self.character_bots.keys())}"""
            
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
    """個別の人格を持つBOTインスタンス"""
    
    def __init__(self, character_name: str, character_data: Dict, parent_bot: UniversalDiscordAI):
        self.character_name = character_name
        self.character_data = character_data
        self.parent_bot = parent_bot
        self.logger = logging.getLogger(f"CharacterBot.{character_name}")
        
    async def generate_response(self, message: discord.Message, channel_info: Dict, chat_history: List[Dict]):
        """返答を生成して送信"""
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
                character_data=self.character_data
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
            if message.guild:
                # トークン数の推定（簡易版）
                estimated_output_tokens = len(full_response.split())
                estimated_input_tokens = len(context.split())  # コンテキストのトークン数推定
                
                self.parent_bot.detailed_logger.log_message_generation(
                    server_name=message.guild.name,
                    channel_name=message.channel.name,
                    user_name=message.author.display_name,
                    character_name=self.character_name,
                    response_time=response_time,
                    token_count=estimated_output_tokens,
                    message_sent=response_message is not None,
                    input_tokens=estimated_input_tokens,
                    output_tokens=estimated_output_tokens
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
