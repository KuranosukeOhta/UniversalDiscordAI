#!/usr/bin/env python3
"""
メンションIDの詳細確認スクリプト
"""
import asyncio
import os
import discord
from dotenv import load_dotenv

load_dotenv('env.local')

class MentionDebugBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
        super().__init__(intents=intents)
    
    async def on_ready(self):
        print(f'🤖 BOT情報:')
        print(f'   名前: {self.user.name}')
        print(f'   ID: {self.user.id}')
        print(f'   メンション形式: <@{self.user.id}>')
        print(f'   メンション形式(ニックネーム): <@!{self.user.id}>')
        
        for guild in self.guilds:
            print(f'\n🏠 サーバー: {guild.name}')
            me = guild.me
            print(f'   サーバー内での名前: {me.display_name}')
            print(f'   サーバー内でのID: {me.id}')
            print(f'   ニックネーム: {me.nick}')
            
            # ロールを確認
            print(f'   BOTのロール:')
            for role in me.roles:
                if role.name != '@everyone':
                    print(f'     - {role.name} (ID: {role.id}) -> <@&{role.id}>')
        
        print(f'\n💡 テスト: メンションを送信してください')
    
    async def on_message(self, message):
        if message.author == self.user or message.author.bot:
            return
            
        print(f'\n📨 メッセージ詳細分析:')
        print(f'   内容: {message.content}')
        print(f'   Raw mentions: {message.raw_mentions}')
        print(f'   Raw role mentions: {message.raw_role_mentions}')
        print(f'   Mentions: {[str(u) for u in message.mentions]}')
        print(f'   Role mentions: {[str(r) for r in message.role_mentions]}')
        
        # 各種メンション検知方法をテスト
        print(f'\n🔍 メンション検知テスト:')
        print(f'   self.user.mentioned_in(message): {self.user.mentioned_in(message)}')
        print(f'   BOT ID in raw_mentions: {self.user.id in message.raw_mentions}')
        
        # メンションされているかの詳細確認
        is_mentioned = False
        mention_type = ""
        
        # 1. 直接メンション
        if self.user.id in message.raw_mentions:
            is_mentioned = True
            mention_type = "直接メンション"
        
        # 2. BOTロールメンション
        guild = message.guild
        if guild:
            bot_member = guild.get_member(self.user.id)
            if bot_member:
                for role in bot_member.roles:
                    if role.id in message.raw_role_mentions:
                        is_mentioned = True
                        mention_type = f"ロールメンション ({role.name})"
                        break
        
        print(f'   カスタム検知: {is_mentioned} ({mention_type})')
        
        if is_mentioned:
            print(f'   → 🎉 メンション確認！返答中...')
            try:
                await message.reply(f'メンション検知成功！✨\n検知方法: {mention_type}')
                print(f'   → ✅ 返答送信完了')
            except Exception as e:
                print(f'   → ❌ 返答エラー: {e}')

async def main():
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print('❌ DISCORD_BOT_TOKENが設定されていません')
        return
    
    client = MentionDebugBot()
    
    try:
        await client.start(token)
    except KeyboardInterrupt:
        print('\n⏹️  BOTを停止中...')
        await client.close()

if __name__ == "__main__":
    print('🔍 メンションID詳細確認を開始...')
    asyncio.run(main())
