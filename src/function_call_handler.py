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
        
        # ファンクションコール設定
        self.enabled = config.get('function_call_settings.enabled', False)
        self.allowed_operations = config.get('function_call_settings.allowed_operations', [])
        self.require_admin = config.get('function_call_settings.require_admin', True)
        
        # 利用可能な関数の定義
        self.available_functions = self._define_available_functions()
        
    def _define_available_functions(self) -> List[Dict]:
        """利用可能な関数の定義を返す"""
        functions = []
        
        if "edit_thread" in self.allowed_operations:
            functions.append({
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
            })
            
        if "edit_channel" in self.allowed_operations:
            functions.append({
                "name": "edit_channel_name",
                "description": "Discordチャンネルの名前を変更します",
                "parameters": {
                    "type": "object",
                    "parameters": {
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
            })
            
        return functions
    
    def get_function_definitions(self) -> List[Dict]:
        """OpenAI用の関数定義を返す"""
        return self.available_functions
    
    async def execute_function_call(self, function_name: str, arguments: Dict, message: discord.Message) -> Dict:
        """ファンクションコールを実行"""
        if not self.enabled:
            return {
                "success": False,
                "error": "ファンクションコールが無効化されています"
            }
        
        # 管理者権限チェック
        if self.require_admin and not await self._check_admin_permission(message):
            return {
                "success": False,
                "error": "管理者権限が必要です"
            }
        
        # 関数の存在チェック
        if function_name not in [func["name"] for func in self.available_functions]:
            return {
                "success": False,
                "error": f"不明な関数: {function_name}"
            }
        
        try:
            # 関数の実行
            if function_name == "edit_thread_name":
                result = await self._edit_thread_name(arguments, message)
            elif function_name == "edit_channel_name":
                result = await self._edit_channel_name(arguments, message)
            else:
                result = {
                    "success": False,
                    "error": f"未実装の関数: {function_name}"
                }
            
            # ログ出力
            if result["success"]:
                self.logger.info(f"ファンクションコール成功: {function_name} - {message.author.display_name}")
            else:
                self.logger.error(f"ファンクションコール失敗: {function_name} - {result['error']}")
            
            return result
            
        except Exception as e:
            error_msg = f"ファンクションコール実行中にエラー: {str(e)}"
            self.logger.error(error_msg)
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
            
            # スレッドの取得
            thread = self.bot.get_channel(thread_id)
            if not thread or not isinstance(thread, discord.Thread):
                return {
                    "success": False,
                    "error": "指定されたスレッドが見つかりません"
                }
            
            # スレッド名の変更
            await thread.edit(name=new_name)
            
            return {
                "success": True,
                "message": f"スレッド名を「{new_name}」に変更しました",
                "thread_name": new_name,
                "thread_id": thread_id
            }
            
        except ValueError:
            return {
                "success": False,
                "error": "無効なスレッドIDです"
            }
        except discord.Forbidden:
            return {
                "success": False,
                "error": "スレッド名を変更する権限がありません"
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"スレッド名変更中にエラー: {str(e)}"
            }
    
    async def _edit_channel_name(self, arguments: Dict, message: discord.Message) -> Dict:
        """チャンネル名を変更"""
        try:
            channel_id = int(arguments.get("channel_id"))
            new_name = arguments.get("new_name")
            
            # チャンネルの取得
            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                return {
                    "success": False,
                    "error": "指定されたチャンネルが見つかりません"
                }
            
            # チャンネル名の変更
            await channel.edit(name=new_name)
            
            return {
                "success": True,
                "message": f"チャンネル名を「{new_name}」に変更しました",
                "channel_name": new_name,
                "channel_id": channel_id
            }
            
        except ValueError:
            return {
                "success": False,
                "error": "無効なチャンネルIDです"
            }
        except discord.Forbidden:
            return {
                "success": False,
                "error": "チャンネル名を変更する権限がありません"
            }
        except Exception as e:
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
