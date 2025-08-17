"""
Universal Discord AI - Main Bot Module
メインのDiscord BOT実装
"""

import asyncio
import logging
import os
import sys
from typing import Dict, List, Optional

import discord
from discord.ext import commands
from dotenv import load_dotenv

from character_manager import CharacterManager
from openai_handler import OpenAIHandler
from utils import ConfigManager, setup_logging, TokenCounter

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
        
        # ステータスをオフラインに設定
        try:
            await self.change_presence(
                status=discord.Status.offline,
                activity=None
            )
            self.logger.info("BOTステータスをオフラインに設定しました")
        except Exception as e:
            self.logger.warning(f"ステータス変更エラー: {e}")
        
        # 親クラスの終了処理を呼び出し
        await super().close()
        
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
        
        # ロールメンションもチェック
        if not is_mentioned and message.guild:
            bot_member = message.guild.get_member(self.user.id)
            if bot_member:
                for role in bot_member.roles:
                    if role.id in message.raw_role_mentions:
                        is_mentioned = True
                        self.logger.debug(f"ロールメンション検知: {role.name}")
                        break
        
        # デバッグ用ログ
        self.logger.debug(f"メッセージ受信: {message.author} -> {message.content}")
        self.logger.debug(f"メンション検知: {is_mentioned}")
        
        if not is_mentioned:
            return
            
        # 返答処理を開始
        await self.handle_mention(message)
        
    async def handle_mention(self, message: discord.Message):
        """メンション時の返答処理"""
        try:
            # typing indicator開始
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
                
        except Exception as e:
            self.logger.error(f"メンション処理中にエラーが発生: {e}")
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
        history_limit = self.config.get('bot_settings.chat_history_limit', 100)
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
                    'attachments': len(message.attachments) > 0
                }
                history.append(history_item)
                
            # 時系列順に並び替え（古い順）
            history.reverse()
            
        except Exception as e:
            self.logger.error(f"チャット履歴取得中にエラー: {e}")
            
        return history


class CharacterBot:
    """個別の人格を持つBOTインスタンス"""
    
    def __init__(self, character_name: str, character_data: Dict, parent_bot: UniversalDiscordAI):
        self.character_name = character_name
        self.character_data = character_data
        self.parent_bot = parent_bot
        self.logger = logging.getLogger(f"CharacterBot.{character_name}")
        
    async def generate_response(self, message: discord.Message, channel_info: Dict, chat_history: List[Dict]):
        """返答を生成して送信"""
        try:
            # コンテキストを構築
            context = self.build_context(message, channel_info, chat_history)
            
            # トークン数チェック
            if not self.parent_bot.token_counter.check_context_limit(context):
                await message.reply("申し訳ございません。コンテキストが長すぎるため、履歴を短縮して再試行してください。")
                return
                
            # OpenAI APIで返答生成（ストリーミング）
            response_message = await message.reply("考え中...")
            
            full_response = ""
            async for chunk in self.parent_bot.openai_handler.generate_streaming_response(
                context=context,
                character_data=self.character_data
            ):
                full_response += chunk
                
                # 定期的にメッセージを更新
                if len(full_response) % 100 == 0:  # 100文字ごとに更新
                    try:
                        await response_message.edit(content=full_response[:2000])  # Discord制限
                    except discord.NotFound:
                        # メッセージが削除された場合
                        break
                    except discord.HTTPException:
                        # 編集制限に達した場合
                        pass
                        
            # 最終的な返答を設定
            try:
                await response_message.edit(content=full_response[:2000])
            except discord.NotFound:
                pass
                
        except Exception as e:
            self.logger.error(f"返答生成中にエラー: {e}")
            try:
                await message.reply(f"申し訳ございません。エラーが発生しました: {str(e)}")
            except:
                pass
                
    def build_context(self, message: discord.Message, channel_info: Dict, chat_history: List[Dict]) -> str:
        """AIへ送信するコンテキストを構築"""
        context_parts = []
        
        # 人格設定
        context_parts.append(f"# 人格設定\n{self.character_data.get('content', '')}")
        
        # チャンネル情報
        context_parts.append(f"\n# チャンネル情報")
        context_parts.append(f"チャンネル名: {channel_info['name']}")
        context_parts.append(f"チャンネルトピック: {channel_info['topic']}")
        context_parts.append(f"チャンネルタイプ: {channel_info['type']}")
        
        # チャット履歴
        if chat_history:
            context_parts.append(f"\n# 最近のチャット履歴")
            for item in chat_history[-20:]:  # 直近20件
                context_parts.append(f"{item['author']}: {item['content']}")
                
        # 現在のメッセージ
        context_parts.append(f"\n# 現在のメッセージ")
        context_parts.append(f"{message.author.display_name}: {message.content}")
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
        
    # BOTインスタンスを作成して実行
    bot = UniversalDiscordAI()
    
    try:
        await bot.start(token)
    except KeyboardInterrupt:
        print("\nBOTを停止しています...")
        try:
            await bot.close()
            print("BOTを正常に停止しました")
        except Exception as e:
            print(f"BOT停止中にエラー: {e}")
    except Exception as e:
        print(f"BOT実行中にエラーが発生: {e}")
        try:
            await bot.close()
        except Exception as close_error:
            print(f"BOT停止中にエラー: {close_error}")
        sys.exit(1)


if __name__ == "__main__":
    # ログディレクトリを作成
    os.makedirs('logs', exist_ok=True)
    
    # メイン実行
    asyncio.run(main())
