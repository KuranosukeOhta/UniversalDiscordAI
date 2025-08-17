"""
Universal Discord AI - Function Call Handler
Discord API操作のためのファンクションコールハンドラ
"""

import logging
from typing import Dict, List, Optional, Any
import discord
from discord.ext import commands


class FunctionCallHandler:
    """Discord API操作のためのファンクションコールハンドラ"""
    
    def __init__(self, bot: commands.Bot, config: Dict):
        self.bot = bot
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 設定の内容をログ出力
        self.logger.info(f"FunctionCallHandler初期化開始")
        self.logger.info(f"受け取った設定: {config}")
        
        # ファンクションコール設定
        self.enabled = config.get('function_call_settings.enabled', False)
        self.allowed_operations = config.get('function_call_settings.allowed_operations', [])
        self.require_admin = config.get('function_call_settings.require_admin', True)
        
        self.logger.info(f"ファンクションコール設定 - 有効: {self.enabled}, 操作: {self.allowed_operations}, 管理者要求: {self.require_admin}")
        
        # 利用可能な関数の定義
        self.available_functions = self._define_available_functions()
        self.logger.info(f"利用可能な関数定義完了: {len(self.available_functions)}個")
        
    def _define_available_functions(self) -> List[Dict]:
        """利用可能な関数の定義を返す"""
        functions = []
        
        if "edit_thread" in self.allowed_operations:
            functions.append({
                "type": "function",
                "function": {
                    "name": "edit_thread_name",
                    "description": "Discordスレッドの名前を変更します",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "thread_id": {
                                "type": "string",
                                "description": "変更したいスレッドのID"
                            },
                            "new_name": {
                                "type": "string",
                                "description": "新しいスレッド名"
                            }
                        },
                        "required": ["thread_id", "new_name"]
                    }
                }
            })
            
        if "edit_channel" in self.allowed_operations:
            functions.append({
                "type": "function",
                "function": {
                    "name": "edit_channel_name",
                    "description": "Discordチャンネルの名前を変更します",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel_id": {
                                "type": "string",
                                "description": "変更したいチャンネルのID"
                            },
                            "new_name": {
                                "type": "string",
                                "description": "新しいチャンネル名"
                            }
                        },
                        "required": ["channel_id", "new_name"]
                    }
                }
            })
            
        return functions
    
    def get_function_definitions(self) -> List[Dict]:
        """OpenAI用の関数定義を返す"""
        return self.available_functions
    
    async def execute_function_call(self, function_name: str, arguments: Dict, message: discord.Message) -> Dict:
        """ファンクションコールを実行"""
        self.logger.info(f"🔧 ファンクションコール実行開始: {function_name}")
        self.logger.info(f"👤 実行ユーザー: {message.author.display_name} (ID: {message.author.id})")
        self.logger.info(f"📍 チャンネル: #{message.channel.name} (ID: {message.channel.id})")
        self.logger.info(f"📋 引数: {arguments}")
        
        if not self.enabled:
            self.logger.warning(f"❌ ファンクションコール機能が無効化されています")
            return {
                "success": False,
                "error": "ファンクションコールが無効化されています"
            }
        
        # 管理者権限チェック
        if self.require_admin:
            self.logger.info(f"🔐 管理者権限チェック開始")
            has_permission = await self._check_admin_permission(message)
            self.logger.info(f"🔐 管理者権限チェック結果: {has_permission}")
            
            if not has_permission:
                self.logger.warning(f"❌ 管理者権限が不足: {message.author.display_name}")
                return {
                    "success": False,
                    "error": "管理者権限が必要です"
                }
        else:
            self.logger.info(f"🔓 管理者権限チェックをスキップ")
        
        # 関数の存在チェック
        available_function_names = [func["name"] for func in self.available_functions]
        self.logger.info(f"📋 利用可能な関数: {available_function_names}")
        
        if function_name not in available_function_names:
            self.logger.error(f"❌ 不明な関数: {function_name}")
            return {
                "success": False,
                "error": f"不明な関数: {function_name}"
            }
        
        try:
            self.logger.info(f"🚀 関数実行開始: {function_name}")
            
            # 関数の実行
            if function_name == "edit_thread_name":
                self.logger.info(f"📝 スレッド名変更関数を実行")
                result = await self._edit_thread_name(arguments, message)
            elif function_name == "edit_channel_name":
                self.logger.info(f"📝 チャンネル名変更関数を実行")
                result = await self._edit_channel_name(arguments, message)
            else:
                self.logger.error(f"❌ 未実装の関数: {function_name}")
                result = {
                    "success": False,
                    "error": f"未実装の関数: {function_name}"
                }
            
            # ログ出力
            if result["success"]:
                self.logger.info(f"✅ ファンクションコール成功: {function_name} - {message.author.display_name}")
            else:
                self.logger.error(f"❌ ファンクションコール失敗: {function_name} - {result['error']}")
            
            return result
            
        except Exception as e:
            error_msg = f"ファンクションコール実行中にエラー: {str(e)}"
            self.logger.error(f"❌ {error_msg}")
            self.logger.error(f"📋 エラー詳細: {type(e).__name__}: {str(e)}")
            return {
                "success": False,
                "error": error_msg
            }
    
    async def _check_admin_permission(self, message: discord.Message) -> bool:
        """管理者権限をチェック"""
        if not message.guild:
            return False
        
        # サーバーオーナーかチェック
        if message.author.id == message.guild.owner_id:
            return True
        
        # 管理者権限を持つロールかチェック
        if message.author.guild_permissions.administrator:
            return True
        
        # 特定のロール名で管理者権限をチェック（設定可能）
        admin_roles = self.config.get('function_call_settings.admin_roles', [])
        if admin_roles:
            user_roles = [role.name for role in message.author.roles]
            if any(role in user_roles for role in admin_roles):
                return True
        
        return False
    
    async def _edit_thread_name(self, arguments: Dict, message: discord.Message) -> Dict:
        """スレッド名を変更"""
        try:
            thread_id = int(arguments.get("thread_id"))
            new_name = arguments.get("new_name")
            
            self.logger.info(f"📝 スレッド名変更開始 - スレッドID: {thread_id}, 新しい名前: {new_name}")
            
            # スレッドの取得
            thread = self.bot.get_channel(thread_id)
            if not thread or not isinstance(thread, discord.Thread):
                self.logger.error(f"❌ スレッドが見つからないか、スレッドではありません - ID: {thread_id}")
                return {
                    "success": False,
                    "error": "指定されたスレッドが見つかりません"
                }
            
            self.logger.info(f"✅ スレッド取得成功: {thread.name}")
            
            # スレッド名の変更
            self.logger.info(f"🔄 スレッド名を変更中: {thread.name} → {new_name}")
            await thread.edit(name=new_name)
            self.logger.info(f"✅ スレッド名変更完了")
            
            return {
                "success": True,
                "message": f"スレッド名を「{new_name}」に変更しました",
                "thread_name": new_name,
                "thread_id": thread_id
            }
            
        except ValueError:
            self.logger.error(f"❌ 無効なスレッドID: {arguments.get('thread_id')}")
            return {
                "success": False,
                "error": "無効なスレッドIDです"
            }
        except discord.Forbidden:
            self.logger.error(f"❌ スレッド名変更権限が不足")
            return {
                "success": False,
                "error": "スレッド名を変更する権限がありません"
            }
        except Exception as e:
            self.logger.error(f"❌ スレッド名変更中にエラー: {str(e)}")
            return {
                "success": False,
                "error": f"スレッド名変更中にエラー: {str(e)}"
            }
    
    async def _edit_channel_name(self, arguments: Dict, message: discord.Message) -> Dict:
        """チャンネル名を変更"""
        try:
            channel_id = int(arguments.get("channel_id"))
            new_name = arguments.get("new_name")
            
            self.logger.info(f"📝 チャンネル名変更開始 - チャンネルID: {channel_id}, 新しい名前: {new_name}")
            
            # チャンネルの取得
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                self.logger.error(f"❌ チャンネルが見つからないか、テキストチャンネルではありません - ID: {channel_id}")
                return {
                    "success": False,
                    "error": "指定されたチャンネルが見つかりません"
                }
            
            self.logger.info(f"✅ チャンネル取得成功: {channel.name}")
            
            # チャンネル名の変更
            self.logger.info(f"🔄 チャンネル名を変更中: {channel.name} → {new_name}")
            await channel.edit(name=new_name)
            self.logger.info(f"✅ チャンネル名変更完了")
            
            return {
                "success": True,
                "message": f"チャンネル名を「{new_name}」に変更しました",
                "channel_name": new_name,
                "channel_id": channel_id
            }
            
        except ValueError:
            self.logger.error(f"❌ 無効なチャンネルID: {arguments.get('channel_id')}")
            return {
                "success": False,
                "error": "無効なチャンネルIDです"
            }
        except discord.Forbidden:
            self.logger.error(f"❌ チャンネル名変更権限が不足")
            return {
                "success": False,
                "error": "チャンネル名を変更する権限がありません"
            }
        except Exception as e:
            self.logger.error(f"❌ チャンネル名変更中にエラー: {str(e)}")
            return {
                "success": False,
                "error": f"チャンネル名変更中にエラー: {str(e)}"
            }
    
    def format_function_result_for_ai(self, result: Dict) -> str:
        """AI用に関数実行結果をフォーマット"""
        if result["success"]:
            return f"✅ {result['message']}"
        else:
            return f"❌ エラー: {result['error']}"
