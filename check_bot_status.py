#!/usr/bin/env python3
"""
BOTの状態確認スクリプト
"""
import asyncio
import os
import discord
from dotenv import load_dotenv

load_dotenv('env.local')

async def check_bot():
    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.members = True
    
    client = discord.Client(intents=intents)
    
    @client.event
    async def on_ready():
        print(f'🤖 BOT情報: {client.user}')
        print(f'🆔 BOT ID: {client.user.id}')
        print(f'🏠 参加サーバー数: {len(client.guilds)}')
        
        if len(client.guilds) == 0:
            print('❌ BOTがどのサーバーにも参加していません')
            print('📝 招待URLを確認して再招待してください')
        else:
            for guild in client.guilds:
                print(f'✅ サーバー: {guild.name} (ID: {guild.id}, メンバー数: {guild.member_count})')
                
        await client.close()
    
    @client.event
    async def on_guild_join(guild):
        print(f'🎉 新しいサーバーに参加: {guild.name}')
    
    token = os.getenv('DISCORD_BOT_TOKEN')
    if token:
        print('🔑 TOKENを確認しました')
        try:
            await client.start(token)
        except Exception as e:
            print(f'❌ 接続エラー: {e}')
    else:
        print('❌ DISCORD_BOT_TOKENが見つかりません')

if __name__ == "__main__":
    asyncio.run(check_bot())
