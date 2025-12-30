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
        
        if "edit_thread" in self.allowed_operations or "edit_channel" in self.allowed_operations:
            functions.append({
                "type": "function",
                "function": {
                    "name": "edit_conversation_name",
                    "description": "会話中のスレッドまたはチャンネルの名前を変更します。スレッド内ではスレッド名、チャンネル内ではチャンネル名が変更されます。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "new_name": {
                                "type": "string",
                                "description": "新しい名前"
                            }
                        },
                        "required": ["new_name"]
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
        
        # 安全にユーザー情報を取得
        user_name = "Unknown User"
        user_id = "Unknown"
        if message.author:
            user_name = getattr(message.author, 'display_name', 'Unknown User')
            user_id = str(message.author.id) if hasattr(message.author, 'id') else "Unknown"
        
        # 安全にチャンネル情報を取得
        channel_name = "Unknown Channel"
        channel_id = "Unknown"
        if message.channel:
            if isinstance(message.channel, discord.DMChannel):
                channel_name = "DM"
            elif hasattr(message.channel, 'name'):
                channel_name = message.channel.name
            channel_id = str(message.channel.id) if hasattr(message.channel, 'id') else "Unknown"
        
        self.logger.info(f"👤 実行ユーザー: {user_name} (ID: {user_id})")
        self.logger.info(f"📍 チャンネル: #{channel_name} (ID: {channel_id})")
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
                user_name = "Unknown User"
                if message.author:
                    user_name = getattr(message.author, 'display_name', 'Unknown User')
                self.logger.warning(f"❌ 管理者権限が不足: {user_name}")
                return {
                    "success": False,
                    "error": "管理者権限が必要です"
                }
        else:
            self.logger.info(f"🔓 管理者権限チェックをスキップ")
        
        # 関数の存在チェック
        available_function_names = [func["function"]["name"] for func in self.available_functions]
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
            if function_name == "edit_conversation_name":
                self.logger.info(f"📝 会話名変更関数を実行")
                result = await self._edit_conversation_name(arguments, message)
            else:
                self.logger.error(f"❌ 未実装の関数: {function_name}")
                result = {
                    "success": False,
                    "error": f"未実装の関数: {function_name}"
                }
            
            # ログ出力
            user_name = "Unknown User"
            if message.author:
                user_name = getattr(message.author, 'display_name', 'Unknown User')
            
            if result["success"]:
                self.logger.info(f"✅ ファンクションコール成功: {function_name} - {user_name}")
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
    
    async def _edit_conversation_name(self, arguments: Dict, message: discord.Message) -> Dict:
        """スレッドまたはチャンネルの名前を変更"""
        try:
            new_name = arguments.get("new_name")
            
            self.logger.info(f"📝 会話名変更開始 - 新しい名前: {new_name}")
            self.logger.info(f"🔍 メッセージチャンネルの詳細情報:")
            
            channel_name = "Unknown Channel"
            if isinstance(message.channel, discord.DMChannel):
                channel_name = "DM"
            elif hasattr(message.channel, 'name'):
                channel_name = message.channel.name
            
            self.logger.info(f"  - チャンネル名: {channel_name}")
            self.logger.info(f"  - チャンネルID: {message.channel.id}")
            self.logger.info(f"  - チャンネルタイプ: {type(message.channel)}")
            self.logger.info(f"  - チャンネルクラス名: {message.channel.__class__.__name__}")
            self.logger.info(f"  - チャンネル基底クラス: {message.channel.__class__.__bases__}")
            
            # 現在のチャンネルがスレッドかテキストチャンネルかを判断
            if isinstance(message.channel, discord.Thread):
                self.logger.info(f"🔍 現在のチャンネルはスレッドです。スレッド名を変更します。")
                thread = message.channel
                self.logger.info(f"🔍 スレッドオブジェクト詳細: {type(thread)}")
                self.logger.info(f"🔍 スレッド属性: {dir(thread)}")
                
                # スレッド名の取得とログ
                try:
                    current_name = thread.name
                    self.logger.info(f"✅ スレッド取得成功: {current_name}")
                except Exception as name_error:
                    self.logger.error(f"❌ スレッド名取得エラー: {str(name_error)}")
                    self.logger.error(f"❌ スレッドオブジェクト: {thread}")
                    return {
                        "success": False,
                        "error": f"スレッド名の取得に失敗: {str(name_error)}"
                    }
                
                # スレッド名の変更
                self.logger.info(f"🔄 スレッド名を変更中: {current_name} → {new_name}")
                try:
                    await thread.edit(name=new_name)
                    self.logger.info(f"✅ スレッド名変更完了")
                except Exception as edit_error:
                    self.logger.error(f"❌ スレッド名変更エラー: {str(edit_error)}")
                    return {
                        "success": False,
                        "error": f"スレッド名変更に失敗: {str(edit_error)}"
                    }
                
                return {
                    "success": True,
                    "message": f"スレッド名を「{new_name}」に変更しました",
                    "conversation_name": new_name,
                    "conversation_type": "thread"
                }
            elif hasattr(message.channel, 'name') and hasattr(message.channel, 'edit'):
                # テキストチャンネルの判定を修正
                self.logger.info(f"🔍 現在のチャンネルはテキストチャンネルと判定されました。チャンネル名を変更します。")
                channel = message.channel
                self.logger.info(f"🔍 チャンネルオブジェクト詳細: {type(channel)}")
                self.logger.info(f"🔍 チャンネル属性: {dir(channel)}")
                
                # チャンネル名の取得とログ
                try:
                    current_name = channel.name
                    self.logger.info(f"✅ チャンネル取得成功: {current_name}")
                except Exception as name_error:
                    self.logger.error(f"❌ チャンネル名取得エラー: {str(name_error)}")
                    self.logger.error(f"❌ チャンネルオブジェクト: {channel}")
                    return {
                        "success": False,
                        "error": f"チャンネル名の取得に失敗: {str(name_error)}"
                    }
                
                # チャンネル名の変更
                self.logger.info(f"🔄 チャンネル名を変更中: {current_name} → {new_name}")
                try:
                    await channel.edit(name=new_name)
                    self.logger.info(f"✅ チャンネル名変更完了")
                except Exception as edit_error:
                    self.logger.error(f"❌ チャンネル名変更エラー: {str(edit_error)}")
                    return {
                        "success": False,
                        "error": f"チャンネル名変更に失敗: {str(edit_error)}"
                    }
                
                return {
                    "success": True,
                    "message": f"チャンネル名を「{new_name}」に変更しました",
                    "conversation_name": new_name,
                    "conversation_type": "channel"
                }
            else:
                self.logger.warning(f"⚠️ 現在のチャンネルはスレッドでもテキストチャンネルでもありません: {type(message.channel)}")
                self.logger.warning(f"⚠️ チャンネルの属性: {dir(message.channel)}")
                return {
                    "success": False,
                    "error": "現在のメッセージはスレッドまたはテキストチャンネル内にありません。"
                }
            
        except ValueError:
            self.logger.error(f"❌ 無効なスレッドIDまたはチャンネルID: {arguments.get('thread_id') or arguments.get('channel_id')}")
            return {
                "success": False,
                "error": "無効なIDです"
            }
        except discord.Forbidden:
            self.logger.error(f"❌ 名前変更権限が不足")
            return {
                "success": False,
                "error": "名前を変更する権限がありません"
            }
        except Exception as e:
            self.logger.error(f"❌ 会話名変更中にエラー: {str(e)}")
            self.logger.error(f"❌ エラータイプ: {type(e).__name__}")
            self.logger.error(f"❌ エラー詳細: {str(e)}")
            return {
                "success": False,
                "error": f"会話名変更中にエラー: {str(e)}"
            }
    
    def format_function_result_for_ai(self, result: Dict) -> str:
        """AI用に関数実行結果をフォーマット"""
        if result["success"]:
            return f"✅ {result['message']}"
        else:
            return f"❌ エラー: {result['error']}"
