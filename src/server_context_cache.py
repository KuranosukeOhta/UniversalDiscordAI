"""
Universal Discord AI - Server Context Cache
サーバー全体の会話ログをキャッシュして高速にコンテキストを生成するモジュール
"""

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from pathlib import Path

import discord


class ServerContextCache:
    """サーバーコンテキストのキャッシュ管理"""
    
    def __init__(self, config, cache_dir: str = "cache/servers"):
        self.config = config
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # メモリキャッシュ（高速アクセス用）
        self.memory_cache: Dict[int, Dict] = {}
        
        # ロック（同時書き込み防止）
        self.cache_locks: Dict[int, asyncio.Lock] = {}
        
        # ログ設定
        self.logger = logging.getLogger(__name__)
        
        # 設定読み込み
        self.max_messages = config.get('server_context_settings.max_messages_per_server', 5000)
        self.per_channel_limit = config.get('server_context_settings.per_channel_limit', 500)
        self.cache_ttl_minutes = config.get('server_context_settings.cache_ttl_minutes', 60)
        self.enabled = config.get('server_context_settings.enabled', False)
        self.include_threads = config.get('server_context_settings.include_threads', True)
        
        self.logger.info("=" * 60)
        self.logger.info("🗄️  ServerContextCache 初期化")
        self.logger.info(f"   ├─ 有効: {self.enabled}")
        self.logger.info(f"   ├─ キャッシュディレクトリ: {self.cache_dir}")
        self.logger.info(f"   ├─ サーバーあたり最大メッセージ数: {self.max_messages}")
        self.logger.info(f"   ├─ チャンネルあたり最大メッセージ数: {self.per_channel_limit}")
        self.logger.info(f"   ├─ キャッシュTTL: {self.cache_ttl_minutes}分")
        self.logger.info(f"   └─ スレッド含む: {self.include_threads}")
        self.logger.info("=" * 60)
    
    def _get_cache_lock(self, guild_id: int) -> asyncio.Lock:
        """サーバー別のロックを取得"""
        if guild_id not in self.cache_locks:
            self.cache_locks[guild_id] = asyncio.Lock()
        return self.cache_locks[guild_id]
    
    def _get_cache_path(self, guild_id: int) -> Path:
        """キャッシュファイルのパスを取得"""
        return self.cache_dir / f"{guild_id}.json"
    
    async def initialize_server(self, guild: discord.Guild) -> bool:
        """
        サーバーの全チャンネルから履歴を取得してキャッシュを初期化
        BOT起動時に呼び出される
        """
        if not self.enabled:
            self.logger.info(f"⏭️  サーバーコンテキストキャッシュが無効のためスキップ: {guild.name}")
            return False
        
        guild_id = guild.id
        lock = self._get_cache_lock(guild_id)
        
        async with lock:
            self.logger.info("")
            self.logger.info("=" * 70)
            self.logger.info(f"🚀 サーバーコンテキスト初期化開始: {guild.name} (ID: {guild_id})")
            self.logger.info("=" * 70)
            
            start_time = datetime.now()
            
            # キャッシュ構造を初期化
            cache_data = {
                "server_id": str(guild_id),
                "server_name": guild.name,
                "last_updated": datetime.now().isoformat(),
                "channels": {},
                "users": {},
                "messages": []
            }
            
            # テキストチャンネルを取得
            text_channels = [ch for ch in guild.channels if isinstance(ch, discord.TextChannel)]
            self.logger.info(f"📋 テキストチャンネル数: {len(text_channels)}")
            
            # スレッドも含める場合
            threads = []
            if self.include_threads:
                for channel in text_channels:
                    try:
                        channel_threads = channel.threads
                        threads.extend(channel_threads)
                    except Exception as e:
                        self.logger.warning(f"   ⚠️ スレッド取得エラー ({channel.name}): {e}")
                self.logger.info(f"🧵 アクティブスレッド数: {len(threads)}")
            
            # チャンネル情報を収集
            self.logger.info("")
            self.logger.info("📂 チャンネル情報を収集中...")
            for channel in text_channels:
                cache_data["channels"][str(channel.id)] = {
                    "name": channel.name,
                    "mention": f"<#{channel.id}>",
                    "topic": channel.topic or ""
                }
                self.logger.info(f"   ├─ #{channel.name} (ID: {channel.id})")
            
            for thread in threads:
                cache_data["channels"][str(thread.id)] = {
                    "name": thread.name,
                    "mention": f"<#{thread.id}>",
                    "topic": f"スレッド (親: #{thread.parent.name if thread.parent else 'unknown'})"
                }
                self.logger.info(f"   ├─ 🧵 {thread.name} (ID: {thread.id})")
            
            # チャンネルあたりの取得件数を計算
            total_channels = len(text_channels) + len(threads)
            if total_channels > 0:
                adjusted_per_channel = min(
                    self.per_channel_limit,
                    self.max_messages // total_channels
                )
            else:
                adjusted_per_channel = self.per_channel_limit
            
            self.logger.info("")
            self.logger.info(f"📊 取得設定:")
            self.logger.info(f"   ├─ チャンネル総数: {total_channels}")
            self.logger.info(f"   ├─ チャンネルあたり取得件数: {adjusted_per_channel}")
            self.logger.info(f"   └─ 最大合計メッセージ数: {self.max_messages}")
            
            # 全チャンネルからメッセージを収集
            all_messages = []
            users_seen: Set[int] = set()
            
            self.logger.info("")
            self.logger.info("📨 メッセージ収集開始...")
            
            # テキストチャンネルから収集
            for i, channel in enumerate(text_channels, 1):
                channel_messages = await self._fetch_channel_messages(
                    channel, adjusted_per_channel, users_seen, cache_data
                )
                all_messages.extend(channel_messages)
                self.logger.info(f"   [{i}/{len(text_channels)}] #{channel.name}: {len(channel_messages)}件取得")
            
            # スレッドから収集
            if self.include_threads and threads:
                self.logger.info("")
                self.logger.info("🧵 スレッドからメッセージ収集中...")
                for i, thread in enumerate(threads, 1):
                    thread_messages = await self._fetch_channel_messages(
                        thread, adjusted_per_channel // 2, users_seen, cache_data  # スレッドは少なめ
                    )
                    all_messages.extend(thread_messages)
                    self.logger.info(f"   [{i}/{len(threads)}] 🧵 {thread.name}: {len(thread_messages)}件取得")
            
            # 時系列順にソート
            all_messages.sort(key=lambda x: x["timestamp"])
            
            # 最大件数に制限
            if len(all_messages) > self.max_messages:
                all_messages = all_messages[-self.max_messages:]
                self.logger.info(f"   ⚠️ メッセージ数を {self.max_messages} 件に制限しました")
            
            cache_data["messages"] = all_messages
            cache_data["last_updated"] = datetime.now().isoformat()
            
            # メモリキャッシュに保存
            self.memory_cache[guild_id] = cache_data
            
            # JSONファイルに保存
            await self._save_cache_to_file(guild_id, cache_data)
            
            # 完了ログ
            elapsed = (datetime.now() - start_time).total_seconds()
            self.logger.info("")
            self.logger.info("=" * 70)
            self.logger.info(f"✅ サーバーコンテキスト初期化完了: {guild.name}")
            self.logger.info(f"   ├─ 総メッセージ数: {len(all_messages)}")
            self.logger.info(f"   ├─ ユニークユーザー数: {len(cache_data['users'])}")
            self.logger.info(f"   ├─ チャンネル数: {len(cache_data['channels'])}")
            self.logger.info(f"   ├─ 所要時間: {elapsed:.2f}秒")
            self.logger.info(f"   └─ キャッシュファイル: {self._get_cache_path(guild_id)}")
            self.logger.info("=" * 70)
            self.logger.info("")
            
            return True
    
    async def _fetch_channel_messages(
        self, 
        channel, 
        limit: int, 
        users_seen: Set[int],
        cache_data: Dict
    ) -> List[Dict]:
        """チャンネルからメッセージを取得"""
        messages = []
        
        try:
            async for message in channel.history(limit=limit):
                # BOTメッセージはスキップ
                if message.author.bot:
                    continue
                
                # ユーザー情報を収集
                if message.author.id not in users_seen:
                    users_seen.add(message.author.id)
                    cache_data["users"][str(message.author.id)] = {
                        "name": message.author.display_name,
                        "mention": f"<@{message.author.id}>"
                    }
                
                # メッセージデータを追加
                messages.append({
                    "id": str(message.id),
                    "channel_id": str(channel.id),
                    "author_id": str(message.author.id),
                    "content": message.content,
                    "timestamp": message.created_at.isoformat(),
                    "has_attachments": len(message.attachments) > 0
                })
                
        except discord.Forbidden:
            self.logger.warning(f"   ⚠️ アクセス権限なし: #{channel.name}")
        except Exception as e:
            self.logger.error(f"   ❌ メッセージ取得エラー (#{channel.name}): {e}")
        
        return messages
    
    async def _save_cache_to_file(self, guild_id: int, cache_data: Dict):
        """キャッシュをJSONファイルに保存"""
        cache_path = self._get_cache_path(guild_id)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            self.logger.debug(f"💾 キャッシュファイル保存完了: {cache_path}")
        except Exception as e:
            self.logger.error(f"❌ キャッシュファイル保存エラー: {e}")
    
    async def _load_cache_from_file(self, guild_id: int) -> Optional[Dict]:
        """JSONファイルからキャッシュを読み込み"""
        cache_path = self._get_cache_path(guild_id)
        try:
            if cache_path.exists():
                with open(cache_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            self.logger.error(f"❌ キャッシュファイル読み込みエラー: {e}")
        return None
    
    def add_message(self, message: discord.Message):
        """
        新規メッセージをリアルタイムでキャッシュに追加
        on_messageから呼び出される
        """
        if not self.enabled:
            return
        
        if not message.guild:
            return
        
        if message.author.bot:
            return
        
        guild_id = message.guild.id
        
        # メモリキャッシュがない場合はスキップ
        if guild_id not in self.memory_cache:
            self.logger.debug(f"⏭️  キャッシュ未初期化のためスキップ: {message.guild.name}")
            return
        
        cache_data = self.memory_cache[guild_id]
        
        # ユーザー情報を追加（未登録の場合）
        author_id = str(message.author.id)
        if author_id not in cache_data["users"]:
            cache_data["users"][author_id] = {
                "name": message.author.display_name,
                "mention": f"<@{message.author.id}>"
            }
            self.logger.info(f"👤 新規ユーザー追加: {message.author.display_name} (ID: {author_id})")
        
        # チャンネル情報を追加（未登録の場合）
        channel_id = str(message.channel.id)
        if channel_id not in cache_data["channels"]:
            cache_data["channels"][channel_id] = {
                "name": getattr(message.channel, 'name', 'DM'),
                "mention": f"<#{message.channel.id}>",
                "topic": getattr(message.channel, 'topic', '') or ""
            }
            self.logger.info(f"📂 新規チャンネル追加: #{getattr(message.channel, 'name', 'DM')} (ID: {channel_id})")
        
        # メッセージを追加
        new_message = {
            "id": str(message.id),
            "channel_id": channel_id,
            "author_id": author_id,
            "content": message.content,
            "timestamp": message.created_at.isoformat(),
            "has_attachments": len(message.attachments) > 0
        }
        
        cache_data["messages"].append(new_message)
        
        # 最大件数を超えた場合、古いメッセージを削除
        if len(cache_data["messages"]) > self.max_messages:
            removed_count = len(cache_data["messages"]) - self.max_messages
            cache_data["messages"] = cache_data["messages"][-self.max_messages:]
            self.logger.debug(f"🗑️  古いメッセージ {removed_count} 件を削除")
        
        cache_data["last_updated"] = datetime.now().isoformat()
        
        self.logger.info(f"📩 メッセージキャッシュ追加: [{message.guild.name}] #{getattr(message.channel, 'name', 'DM')} - {message.author.display_name}: {message.content[:50]}...")
    
    def get_context(self, guild_id: int) -> Optional[str]:
        """
        キャッシュからAI用コンテキストを生成
        高速（メモリから読み込み）
        """
        if not self.enabled:
            return None
        
        if guild_id not in self.memory_cache:
            self.logger.warning(f"⚠️  キャッシュが見つかりません: guild_id={guild_id}")
            return None
        
        cache_data = self.memory_cache[guild_id]
        
        self.logger.info("")
        self.logger.info("📝 サーバーコンテキスト生成開始...")
        start_time = datetime.now()
        
        context_parts = []
        
        # メンションマッピングセクション
        context_parts.append("# メンション用マッピング（返答時に使用してください）")
        context_parts.append("")
        context_parts.append("## チャンネル")
        for channel_id, channel_info in cache_data["channels"].items():
            context_parts.append(f"- {channel_info['name']} → {channel_info['mention']}")
        
        context_parts.append("")
        context_parts.append("## ユーザー")
        for user_id, user_info in cache_data["users"].items():
            context_parts.append(f"- {user_info['name']} → {user_info['mention']}")
        
        # サーバー情報
        context_parts.append("")
        context_parts.append("# サーバー情報")
        context_parts.append(f"サーバー名: {cache_data['server_name']}")
        context_parts.append(f"チャンネル数: {len(cache_data['channels'])}")
        context_parts.append(f"アクティブユーザー数: {len(cache_data['users'])}")
        context_parts.append(f"キャッシュ更新日時: {cache_data['last_updated']}")
        
        # 会話ログセクション
        context_parts.append("")
        context_parts.append("# サーバー全体の会話ログ（時系列順）")
        context_parts.append("")
        
        # メッセージを整形
        for msg in cache_data["messages"]:
            channel_info = cache_data["channels"].get(msg["channel_id"], {"name": "unknown", "mention": ""})
            user_info = cache_data["users"].get(msg["author_id"], {"name": "unknown", "mention": ""})
            
            # タイムスタンプを読みやすく
            try:
                dt = datetime.fromisoformat(msg["timestamp"])
                timestamp_str = dt.strftime("%Y-%m-%d %H:%M")
            except:
                timestamp_str = msg["timestamp"][:16]
            
            # メッセージ行
            line = f"## [{timestamp_str}] #{channel_info['name']} {channel_info['mention']}"
            context_parts.append(line)
            
            content_line = f"{user_info['name']} {user_info['mention']}: {msg['content']}"
            if msg.get("has_attachments"):
                content_line += " (添付ファイルあり)"
            context_parts.append(content_line)
            context_parts.append("")
        
        # 返答ルール
        context_parts.append("# 返答ルール")
        context_parts.append("- チャンネルやユーザーに言及する際は、上記のマッピングを使って <#ID> や <@ID> 形式でメンションしてください")
        context_parts.append("- 例: 「#generalで話してた」→「<#チャンネルID> で話してた」")
        context_parts.append("- サーバー全体の会話ログを参考に、過去の話題や文脈を踏まえて返答してください")
        
        context = "\n".join(context_parts)
        
        elapsed = (datetime.now() - start_time).total_seconds() * 1000
        self.logger.info(f"   ├─ メッセージ数: {len(cache_data['messages'])}")
        self.logger.info(f"   ├─ コンテキスト長: {len(context)} 文字")
        self.logger.info(f"   └─ 生成時間: {elapsed:.2f}ms")
        self.logger.info("")
        
        return context
    
    def get_mention_mapping(self, guild_id: int) -> Dict:
        """メンションマッピング情報を取得"""
        if guild_id not in self.memory_cache:
            return {"channels": {}, "users": {}}
        
        cache_data = self.memory_cache[guild_id]
        return {
            "channels": cache_data.get("channels", {}),
            "users": cache_data.get("users", {})
        }
    
    def get_cache_stats(self, guild_id: int) -> Optional[Dict]:
        """キャッシュの統計情報を取得"""
        if guild_id not in self.memory_cache:
            return None
        
        cache_data = self.memory_cache[guild_id]
        return {
            "server_name": cache_data.get("server_name", "unknown"),
            "message_count": len(cache_data.get("messages", [])),
            "channel_count": len(cache_data.get("channels", {})),
            "user_count": len(cache_data.get("users", {})),
            "last_updated": cache_data.get("last_updated", "unknown")
        }
    
    async def periodic_sync(self, guild: discord.Guild):
        """
        定期的な差分同期（オプション）
        長時間稼働時のキャッシュ整合性を保つ
        """
        if not self.enabled:
            return
        
        self.logger.info(f"🔄 定期同期開始: {guild.name}")
        
        # 現在のキャッシュを再構築
        await self.initialize_server(guild)
        
        self.logger.info(f"✅ 定期同期完了: {guild.name}")
    
    async def save_all_caches(self):
        """全サーバーのキャッシュをファイルに保存"""
        self.logger.info("💾 全キャッシュをファイルに保存中...")
        
        for guild_id, cache_data in self.memory_cache.items():
            await self._save_cache_to_file(guild_id, cache_data)
        
        self.logger.info(f"✅ {len(self.memory_cache)} サーバーのキャッシュを保存しました")
