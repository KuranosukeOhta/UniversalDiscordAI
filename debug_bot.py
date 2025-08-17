#!/usr/bin/env python3
"""
デバッグ用BOT - メッセージ受信状況を詳細に確認
"""
import asyncio
import os
import discord
from dotenv import load_dotenv

load_dotenv('env.local')

class DebugBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)
    
    async def on_ready(self):
        print(f'🤖 デバッグBOT起動: {self.user}')
        print(f'🆔 BOT ID: {self.user.id}')
        print(f'🏠 参加サーバー数: {len(self.guilds)}')
        
        for guild in self.guilds:
            print(f'✅ サーバー: {guild.name} (ID: {guild.id})')
            print(f'📝 テキストチャンネル:')
            for channel in guild.text_channels:
                permissions = channel.permissions_for(guild.me)
                print(f'   #{channel.name}: 読み取り={permissions.read_messages}, 送信={permissions.send_messages}')
        
        print(f'\n💡 テスト方法: Discordで以下のようにメンションしてください')
        print(f'   @{self.user.name} こんにちは')
        print(f'⏹️  停止するには Ctrl+C を押してください\n')
    
    async def on_message(self, message):
        print(f'\n📨 メッセージ受信!')
        print(f'   チャンネル: #{message.channel.name}')
        print(f'   送信者: {message.author.name} (ID: {message.author.id})')
        print(f'   内容: {message.content}')
        print(f'   BOTメッセージ?: {message.author.bot}')
        print(f'   メンション数: {len(message.mentions)}')
        
        # 自分のメッセージは無視
        if message.author == self.user:
            print('   → 自分のメッセージなので無視')
            return
            
        # BOTメッセージは無視
        if message.author.bot:
            print('   → BOTメッセージなので無視')
            return
        
        # メンション確認
        mentioned = self.user.mentioned_in(message)
        print(f'   メンション検知: {mentioned}')
        
        if mentioned:
            print('   → 🎉 メンション確認！返答中...')
            try:
                await message.reply(f'デバッグBOTです！メッセージを受信しました✨\n送信内容: {message.content}')
                print('   → ✅ 返答送信完了')
            except Exception as e:
                print(f'   → ❌ 返答エラー: {e}')
        else:
            print('   → メンションなし、無視')
    
    async def on_guild_join(self, guild):
        print(f'🎉 新しいサーバーに参加: {guild.name}')
    
    async def on_error(self, event, *args, **kwargs):
        print(f'❌ エラー発生 ({event}): {args}')

async def main():
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print('❌ DISCORD_BOT_TOKENが設定されていません')
        return
    
    client = DebugBot()
    
    try:
        await client.start(token)
    except KeyboardInterrupt:
        print('\n⏹️  BOTを停止中...')
        await client.close()
    except Exception as e:
        print(f'❌ BOT実行エラー: {e}')
        await client.close()

if __name__ == "__main__":
    print('🚀 デバッグBOTを起動中...')
    asyncio.run(main())
