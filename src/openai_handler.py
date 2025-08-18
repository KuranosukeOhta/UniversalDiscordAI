"""
Universal Discord AI - OpenAI Handler
OpenAI APIとの通信を管理するモジュール
"""

import os
import asyncio
import logging
from typing import Dict, AsyncGenerator, Optional, List
import aiohttp
import json
from aiolimiter import AsyncLimiter
from utils import ConfigManager


class OpenAIHandler:
    """OpenAI API通信ハンドラー"""
    
    def __init__(self, config: ConfigManager = None):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.base_url = "https://api.openai.com/v1"
        self.logger = logging.getLogger(__name__)
        
        # 設定マネージャーを設定
        self.config = config or ConfigManager()
        
        # レート制限設定（動的調整対応）
        self.rate_limiter = AsyncLimiter(max_rate=50, time_period=60)  # 60秒間に50リクエスト
        self.current_rate_limit = 50
        
        # リクエスト設定
        self.timeout = aiohttp.ClientTimeout(total=self.config.get('openai_settings.timeout_seconds', 120))
        self.max_retries = self.config.get('openai_settings.retry_attempts', 3)
        self.retry_delay = 1.0
        
        # 接続状態監視
        self.connection_status = "unknown"  # unknown, healthy, degraded, failed
        self.last_successful_call = None
        self.consecutive_failures = 0
        self.max_consecutive_failures = 5
        self.health_check_interval = 60  # 60秒ごとにヘルスチェック
        self.auto_recovery_enabled = True
        
        if not self.api_key:
            self.logger.error("OPENAI_API_KEY が設定されていません")
            
    async def generate_streaming_response(
        self, 
        context: str, 
        character_data: Dict,
        model: str = "gpt-5",
        max_completion_tokens: int = 16000,  # GPT-5ではmax_completion_tokensを使用
        temperature: float = 1.0,  # GPT-5はtemperature=1のみサポート
        function_definitions: List[Dict] = None,
        image_attachments: List[Dict] = None
    ) -> AsyncGenerator[str, None]:
        """ストリーミングレスポンスを生成"""
        
        if not self.api_key:
            yield "エラー: OpenAI APIキーが設定されていません"
            return
        
        # 接続状態を事前にチェック（高速化）
        if not await self._check_connection_health_fast():
            yield "接続が不安定です。しばらく待ってから再試行してください。"
            return
            
        # システムプロンプトを構築
        system_prompt = self._build_system_prompt(character_data)
        
        # リクエストデータを構築
        request_data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt}
            ],
            "max_completion_tokens": max_completion_tokens,  # GPT-5ではmax_completion_tokensを使用
            "stream": True
        }
        
        # 画像添付がある場合のメッセージ構造
        if image_attachments:
            self.logger.info(f"🖼️ 画像付きメッセージ構造を構築中: {len(image_attachments)}個の画像")
            
            # 画像付きメッセージの場合
            user_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": context}
                ]
            }
            
            # 画像を追加
            for i, image_data in enumerate(image_attachments):
                image_content = {
                    "type": "image_url",
                    "image_url": {
                        "url": image_data["url"],
                        "detail": image_data.get("detail", "auto")
                    }
                }
                user_message["content"].append(image_content)
                
                self.logger.info(f"画像 {i+1} をメッセージに追加:")
                self.logger.info(f"  - ファイル名: {image_data['filename']}")
                self.logger.info(f"  - URL: {image_data['url']}")
                self.logger.info(f"  - 詳細レベル: {image_data.get('detail', 'auto')}")
            
            request_data["messages"].append(user_message)
            self.logger.info(f"✅ 画像付きメッセージ構造構築完了")
        else:
            # テキストのみのメッセージ
            self.logger.info("📝 テキストのみのメッセージ構造を構築")
            request_data["messages"].append({
                "role": "user", 
                "content": context
            })
        
        # ファンクションコールが有効な場合、関数定義を追加
        if function_definitions:
            request_data["tools"] = function_definitions
            request_data["tool_choice"] = "auto"
        
        # GPT-5では temperature=1 がデフォルトなので、1以外の場合のみ指定
        if temperature != 1.0:
            request_data["temperature"] = temperature
        
        # リクエストデータの詳細をログ出力
        self.logger.info(f"🚀 OpenAI APIリクエスト構造:")
        self.logger.info(f"  - モデル: {model}")
        self.logger.info(f"  - 最大トークン数: {max_completion_tokens}")
        self.logger.info(f"  - ストリーミング: {request_data.get('stream', False)}")
        self.logger.info(f"  - メッセージ数: {len(request_data['messages'])}")
        if image_attachments:
            self.logger.info(f"  - 画像添付: {len(image_attachments)}個")
        if function_definitions:
            self.logger.info(f"  - 関数定義: {len(function_definitions)}個")
        
        # レート制限チェック
        await self.rate_limiter.acquire()
        
        start_time = asyncio.get_event_loop().time()
        retry_count = 0
        
        while retry_count < self.max_retries:
            try:
                async with aiohttp.ClientSession(timeout=self.timeout) as session:
                    headers = {
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                    
                    async with session.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=request_data
                    ) as response:
                        
                        if response.status == 429:  # Rate limit exceeded
                            await self._handle_rate_limit(response)
                            retry_count += 1
                            await asyncio.sleep(self.retry_delay * retry_count)
                            continue
                            
                        if response.status != 200:
                            error_text = await response.text()
                            response_time = asyncio.get_event_loop().time() - start_time
                            
                            # エラーの詳細ログ
                            self.logger.error(f"OpenAI API エラー ({response.status}): {error_text}")
                            self.logger.error(f"エラー詳細 - レスポンス時間: {response_time:.2f}秒, リトライ回数: {retry_count}")
                            
                            yield f"エラー: OpenAI API呼び出しに失敗しました (HTTP {response.status})"
                            return
                            
                        # ストリーミングレスポンスを処理
                        async for chunk in self._process_streaming_response(response):
                            if chunk:
                                yield chunk
                                
                        # 成功時の接続状態更新
                        self._update_connection_status(success=True)
                        return  # 成功時は終了
                        
            except asyncio.TimeoutError:
                response_time = asyncio.get_event_loop().time() - start_time
                self.logger.error(f"OpenAI API タイムアウト (設定: {self.timeout.total}秒, 実際: {response_time:.2f}秒)")
                self.logger.error(f"タイムアウト詳細 - モデル: {model}, 最大トークン: {max_completion_tokens}, コンテキスト長: {len(context)}文字")
                if image_attachments:
                    self.logger.error(f"画像添付: {len(image_attachments)}個")
                self._update_connection_status(success=False, error_type="timeout")
                retry_count += 1
                if retry_count >= self.max_retries:
                    yield f"エラー: OpenAI APIがタイムアウトしました (設定: {self.timeout.total}秒)"
                    return
                await asyncio.sleep(self.retry_delay * retry_count)
                
            except Exception as e:
                # エラーの詳細情報をログ出力
                self.logger.error(f"❌ OpenAI API 呼び出しエラー: {type(e).__name__}: {str(e)}")
                self.logger.error(f"📋 エラー詳細: {e}")
                
                # エラーのトレースバック情報も含める
                import traceback
                error_traceback = traceback.format_exc()
                self.logger.error(f"📋 トレースバック: {error_traceback}")
                
                self._update_connection_status(success=False, error_type="exception", error=str(e))
                retry_count += 1
                if retry_count >= self.max_retries:
                    yield f"エラー: OpenAI API呼び出し中に問題が発生しました: {type(e).__name__}: {str(e)}"
                    return
                await asyncio.sleep(self.retry_delay * retry_count)
                
    async def _process_streaming_response(self, response) -> AsyncGenerator[str, None]:
        """ストリーミングレスポンスを処理"""
        buffer = ""
        
        async for line in response.content:
            line = line.decode('utf-8').strip()
            
            if not line:
                continue
                
            if line.startswith('data: '):
                data = line[6:]  # 'data: ' を除去
                
                if data == '[DONE]':
                    break
                    
                try:
                    json_data = json.loads(data)
                    choices = json_data.get('choices', [])
                    
                    if choices:
                        delta = choices[0].get('delta', {})
                        content = delta.get('content', '')
                        
                        if content:
                            buffer += content
                            yield content
                            
                        # 終了判定
                        if choices[0].get('finish_reason'):
                            break
                            
                except json.JSONDecodeError as e:
                    self.logger.warning(f"JSON解析エラー: {e}, データ: {data}")
                    continue
                except Exception as e:
                    self.logger.error(f"ストリーミング処理エラー: {e}")
                    continue
                    
    def _build_system_prompt(self, character_data: Dict) -> str:
        """システムプロンプトを構築"""
        prompt_parts = [
            "あなたはDiscordのAIアシスタントです。",
            "以下の人格設定に従って、自然で一貫性のある返答をしてください。",
            "",
        ]
        
        # 人格設定を追加
        if character_data.get('personality'):
            prompt_parts.append(f"【基本性格】")
            prompt_parts.append(character_data['personality'])
            prompt_parts.append("")
            
        if character_data.get('speaking_style'):
            prompt_parts.append(f"【話し方・口調】")
            prompt_parts.append(character_data['speaking_style'])
            prompt_parts.append("")
            
        if character_data.get('specialties'):
            prompt_parts.append(f"【専門分野・得意なこと】")
            prompt_parts.append(character_data['specialties'])
            prompt_parts.append("")
            
        if character_data.get('avoid'):
            prompt_parts.append(f"【避けるべき表現・行動】")
            prompt_parts.append(character_data['avoid'])
            prompt_parts.append("")
            
        # 基本的なルール
        prompt_parts.extend([
            "【基本ルール】",
            "- Discord上での会話であることを意識してください",
            "- 長すぎる返答は避け、適度な長さで回答してください",
            "- 絵文字や顔文字を適度に使用して親しみやすさを演出してください",
            "- ユーザーの質問や発言に対して建設的で有用な返答を心がけてください",
            "- 不適切な内容や有害な内容は避けてください"
        ])
        
        return "\n".join(prompt_parts)
    
    async def generate_response_with_function_calls(
        self, 
        context: str, 
        character_data: Dict,
        function_definitions: List[Dict],
        model: str = "gpt-5",
        max_completion_tokens: int = 16000,  # GPT-5ではmax_completion_tokensを使用
        temperature: float = 1.0,
        image_attachments: List[Dict] = None
    ) -> Dict:
        """ファンクションコール対応のレスポンスを生成"""
        
        if not self.api_key:
            return {
                "success": False,
                "error": "OpenAI APIキーが設定されていません"
            }
        
        # システムプロンプトを構築
        system_prompt = self._build_system_prompt(character_data)
        
        # ファンクションコール用のシステムプロンプトを追加
        system_prompt += "\n\n【ファンクションコール機能】"
        system_prompt += "\n必要に応じて、以下の関数を使用してDiscordの操作を実行できます。"
        system_prompt += "\n関数を使用する場合は、適切な引数を指定してください。"
        
        # リクエストデータを構築
        request_data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt}
            ],
            "max_completion_tokens": max_completion_tokens,  # GPT-5ではmax_completion_tokensを使用
            "tools": function_definitions,
            "tool_choice": "auto"
        }
        
        # 画像添付がある場合のメッセージ構造
        if image_attachments:
            self.logger.info(f"🖼️ ファンクションコール処理で画像付きメッセージ構造を構築中: {len(image_attachments)}個の画像")
            
            # 画像付きメッセージの場合
            user_message = {
                "role": "user",
                "content": [
                    {"type": "text", "text": context}
                ]
            }
            
            # 画像を追加
            for i, image_data in enumerate(image_attachments):
                image_content = {
                    "type": "image_url",
                    "image_url": {
                        "url": image_data["url"],
                        "detail": image_data.get("detail", "auto")
                    }
                }
                user_message["content"].append(image_content)
                
                self.logger.info(f"画像 {i+1} をファンクションコールメッセージに追加:")
                self.logger.info(f"  - ファイル名: {image_data['filename']}")
                self.logger.info(f"  - URL: {image_data['url']}")
                self.logger.info(f"  - 詳細レベル: {image_data.get('detail', 'auto')}")
            
            request_data["messages"].append(user_message)
            self.logger.info(f"✅ ファンクションコール用画像付きメッセージ構造構築完了")
        else:
            # テキストのみのメッセージ
            self.logger.info("📝 ファンクションコール用テキストのみのメッセージ構築")
            request_data["messages"].append({
                "role": "user", 
                "content": context
            })
        
        # GPT-5では temperature=1 がデフォルトなので、1以外の場合のみ指定
        if temperature != 1.0:
            request_data["temperature"] = temperature
        
        # ファンクションコール用リクエストデータの詳細をログ出力
        self.logger.info(f"🚀 ファンクションコール用OpenAI APIリクエスト構造:")
        self.logger.info(f"  - モデル: {model}")
        self.logger.info(f"  - 最大トークン数: {max_completion_tokens}")
        self.logger.info(f"  - ストリーミング: {request_data.get('stream', False)}")
        self.logger.info(f"  - メッセージ数: {len(request_data['messages'])}")
        self.logger.info(f"  - 関数定義: {len(function_definitions)}個")
        if image_attachments:
            self.logger.info(f"  - 画像添付: {len(image_attachments)}個")
        
        try:
            # レート制限チェック
            await self.rate_limiter.acquire()
            
            start_time = asyncio.get_event_loop().time()
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=request_data
                ) as response:
                    
                    if response.status == 200:
                        response_data = await response.json()
                        response_time = asyncio.get_event_loop().time() - start_time
                        self.logger.info(f"✅ ファンクションコール成功 - レスポンス時間: {response_time:.2f}秒")
                        return {
                            "success": True,
                            "response": response_data,
                            "choices": response_data.get("choices", [])
                        }
                    else:
                        error_text = await response.text()
                        response_time = asyncio.get_event_loop().time() - start_time
                        self.logger.error(f"❌ ファンクションコール失敗 - HTTP {response.status} (レスポンス時間: {response_time:.2f}秒)")
                        self.logger.error(f"エラー詳細: {error_text}")
                        return {
                            "success": False,
                            "error": f"OpenAI API エラー - HTTP {response.status}: {error_text}"
                        }
                        
        except asyncio.TimeoutError:
            response_time = asyncio.get_event_loop().time() - start_time
            self.logger.error(f"❌ ファンクションコールタイムアウト (設定: {self.timeout.total}秒, 実際: {response_time:.2f}秒)")
            self.logger.error(f"タイムアウト詳細 - モデル: {model}, 最大トークン: {max_completion_tokens}, コンテキスト長: {len(context)}文字")
            if image_attachments:
                self.logger.error(f"画像添付: {len(image_attachments)}個")
            return {
                "success": False,
                "error": f"ファンクションコールがタイムアウトしました (設定: {self.timeout.total}秒)"
            }
        except Exception as e:
            response_time = asyncio.get_event_loop().time() - start_time
            self.logger.error(f"❌ ファンクションコールリクエスト実行中にエラー: {type(e).__name__}: {str(e)} (レスポンス時間: {response_time:.2f}秒)")
            self.logger.error(f"📋 エラー詳細: {e}")
            
            # エラーのトレースバック情報も含める
            import traceback
            error_traceback = traceback.format_exc()
            self.logger.error(f"📋 トレースバック: {error_traceback}")
            
            return {
                "success": False,
                "error": f"リクエスト実行中にエラー: {type(e).__name__}: {str(e)}"
            }
        
    async def _handle_rate_limit(self, response):
        """レート制限への対応"""
        try:
            # レスポンスヘッダーからレート制限情報を取得
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                delay = int(retry_after)
                self.logger.warning(f"レート制限に達しました。{delay}秒後に再試行します")
                await asyncio.sleep(delay)
                
            # レート制限を動的調整
            self.current_rate_limit = max(10, int(self.current_rate_limit * 0.8))
            self.rate_limiter = AsyncLimiter(
                max_rate=self.current_rate_limit, 
                time_period=60
            )
            self.logger.info(f"レート制限を調整: {self.current_rate_limit}/分")
            
        except Exception as e:
            self.logger.error(f"レート制限処理エラー: {e}")
            
    async def test_connection_fast(self) -> bool:
        """OpenAI APIへの軽量接続テスト（高速チェック用）"""
        if not self.api_key:
            self.logger.error("OpenAI APIキーが設定されていません")
            return False
            
        try:
            self.logger.debug("OpenAI API軽量接続テストを開始...")
            
            # 短いタイムアウトで軽量なテストを実行
            fast_timeout = aiohttp.ClientTimeout(total=5)  # 5秒に短縮
            
            async with aiohttp.ClientSession(timeout=fast_timeout) as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                # 最小限のテストリクエスト（GPT-5の制限に対応）
                test_data = {
                    "model": "gpt-5",
                    "messages": [{"role": "user", "content": "Hi"}],
                    "max_completion_tokens": 10  # GPT-5ではmax_completion_tokensを使用
                }
                
                self.logger.debug(f"軽量テストリクエスト送信中: {self.base_url}/chat/completions")
                
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=test_data
                ) as response:
                    
                    if response.status == 200:
                        self.logger.info("OpenAI API軽量接続テスト成功")
                        return True
                    else:
                        error_text = await response.text()
                        self.logger.error(f"OpenAI API軽量接続テスト失敗 - HTTP {response.status}: {error_text}")
                        return False
                        
        except asyncio.TimeoutError:
            self.logger.error("OpenAI API軽量接続テストがタイムアウトしました")
            return False
        except aiohttp.ClientError as e:
            self.logger.error(f"OpenAI API軽量接続テストでネットワークエラー: {e}")
            return False
        except Exception as e:
            self.logger.error(f"OpenAI API軽量接続テストで予期しないエラー: {e}")
            return False

    async def test_connection(self) -> bool:
        """OpenAI APIへの接続をテスト（従来版、詳細なテスト）"""
        if not self.api_key:
            self.logger.error("OpenAI APIキーが設定されていません")
            return False
            
        try:
            self.logger.debug("OpenAI API接続テストを開始...")
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                headers = {
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
                
                # シンプルなテストリクエスト
                test_data = {
                    "model": "gpt-5",
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_completion_tokens": 10  # GPT-5ではmax_completion_tokensを使用
                }
                
                self.logger.debug(f"テストリクエスト送信中: {self.base_url}/chat/completions")
                
                async with session.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=test_data
                ) as response:
                    
                    if response.status == 200:
                        self.logger.info("OpenAI API接続テスト成功")
                        return True
                    else:
                        error_text = await response.text()
                        self.logger.error(f"OpenAI API接続テスト失敗 - HTTP {response.status}: {error_text}")
                        return False
                        
        except asyncio.TimeoutError:
            self.logger.error("OpenAI API接続テストがタイムアウトしました")
            return False
        except aiohttp.ClientError as e:
            self.logger.error(f"OpenAI API接続テストでネットワークエラー: {e}")
            return False
        except Exception as e:
            self.logger.error(f"OpenAI API接続テストで予期しないエラー: {e}")
            self.logger.error(f"エラータイプ: {type(e).__name__}")
            return False
            
    def get_rate_limit_status(self) -> Dict:
        """現在のレート制限状況を取得"""
        return {
            "current_limit": self.current_rate_limit,
            "time_period": 60,
            "available": self.rate_limiter.max_rate - self.rate_limiter._rate_per_period
        }
        
    async def estimate_tokens(self, text: str) -> int:
        """テキストのトークン数を推定（簡易版）"""
        # GPT-5の正確なトークナイザーがない場合の近似計算
        # 日本語: 約1文字 = 1.5トークン
        # 英語: 約4文字 = 1トークン
        
        japanese_chars = sum(1 for c in text if ord(c) > 127)
        english_chars = len(text) - japanese_chars
        
        estimated_tokens = int(japanese_chars * 1.5 + english_chars * 0.25)
        return max(1, estimated_tokens)
    
    def _update_connection_status(self, success: bool, error_type: str = None, error: str = None):
        """接続状態を更新"""
        import time
        
        if success:
            self.connection_status = "healthy"
            self.last_successful_call = time.time()
            self.consecutive_failures = 0
            self.logger.debug("OpenAI API接続状態: 正常")
        else:
            self.consecutive_failures += 1
            self.logger.warning(f"OpenAI API接続失敗: {error_type} (連続失敗: {self.consecutive_failures})")
            
            if self.consecutive_failures >= self.max_consecutive_failures:
                self.connection_status = "failed"
                self.logger.error(f"OpenAI API接続状態: 失敗 (連続{self.consecutive_failures}回)")
            elif self.consecutive_failures >= 3:
                self.connection_status = "degraded"
                self.logger.warning(f"OpenAI API接続状態: 不安定 (連続失敗: {self.consecutive_failures}回)")
    
    async def _check_connection_health_fast(self) -> bool:
        """高速な接続状態チェック（初回メッセージ送信の遅延を防ぐ）"""
        if self.connection_status == "healthy":
            self.logger.debug("OpenAI API接続状態: 正常（高速チェック）")
            return True
        
        if self.connection_status == "failed":
            # 失敗状態の場合は即座にFalseを返す（自動復元は行わない）
            self.logger.warning("OpenAI API接続状態: 失敗（高速チェック）")
            return False
        
        # 不安定状態の場合は短時間待機
        if self.connection_status == "degraded":
            self.logger.warning("OpenAI API接続状態: 不安定（高速チェック）")
            await asyncio.sleep(1)  # 5秒から1秒に短縮
            return True
        
        # 不明な状態の場合は軽量な接続テストを実行
        if self.connection_status == "unknown":
            self.logger.info("OpenAI API接続状態: 不明 - 軽量接続テストを実行（高速チェック）")
            return await self._attempt_recovery_fast()
        
        return False

    async def _check_connection_health(self) -> bool:
        """接続状態の健全性をチェック（従来版、詳細な復元処理）"""
        if self.connection_status == "healthy":
            self.logger.debug("OpenAI API接続状態: 正常")
            return True
        
        if self.connection_status == "failed":
            # 失敗状態の場合、自動復元を試行
            if self.auto_recovery_enabled:
                self.logger.warning("OpenAI API接続状態: 失敗 - 自動復元を試行中...")
                if await self._attempt_recovery():
                    self.logger.info("OpenAI API接続の自動復元に成功しました")
                    return True
                else:
                    self.logger.error("OpenAI API接続の自動復元に失敗しました")
            else:
                self.logger.error("OpenAI API接続状態: 失敗 - 自動復元が無効です")
            return False
        
        # 不安定状態の場合は、短時間待機してから再試行
        if self.connection_status == "degraded":
            self.logger.warning("OpenAI API接続状態: 不安定 - 短時間待機してから再試行します")
            await asyncio.sleep(5)
            return True
        
        # 不明な状態の場合
        if self.connection_status == "unknown":
            self.logger.info("OpenAI API接続状態: 不明 - 初回接続テストを実行します")
            if await self._attempt_recovery():
                return True
        
        return False
    
    async def _attempt_recovery_fast(self) -> bool:
        """軽量な接続復元を試行（高速チェック用）"""
        try:
            self.logger.info("OpenAI API軽量接続テストを実行中...")
            
            # 軽量な接続テストを実行（短いタイムアウト）
            if await self.test_connection_fast():
                self.connection_status = "healthy"
                self.consecutive_failures = 0
                self.logger.info("OpenAI API接続の軽量復元に成功しました")
                return True
            else:
                self.logger.warning("OpenAI API軽量接続テストに失敗しました")
                return False
                
        except asyncio.TimeoutError:
            self.logger.error("OpenAI API軽量接続テストがタイムアウトしました")
            return False
        except Exception as e:
            self.logger.error(f"OpenAI API接続の軽量復元中にエラー: {e}")
            return False

    async def _attempt_recovery(self) -> bool:
        """接続の自動復元を試行（従来版、詳細な復元処理）"""
        try:
            self.logger.info("OpenAI API接続テストを実行中...")
            
            # 接続テストを実行
            if await self.test_connection():
                self.connection_status = "healthy"
                self.consecutive_failures = 0
                self.logger.info("OpenAI API接続の自動復元に成功しました")
                return True
            else:
                self.logger.warning("OpenAI API接続テストに失敗しました")
                return False
                
        except asyncio.TimeoutError:
            self.logger.error("OpenAI API接続テストがタイムアウトしました")
            return False
        except Exception as e:
            self.logger.error(f"OpenAI API接続の自動復元中にエラー: {e}")
            self.logger.error(f"エラータイプ: {type(e).__name__}")
            self.logger.error(f"エラー詳細: {str(e)}")
            return False
    
    def get_connection_status(self) -> Dict:
        """現在の接続状態を取得"""
        import time
        
        status_info = {
            "status": self.connection_status,
            "consecutive_failures": self.consecutive_failures,
            "auto_recovery_enabled": self.auto_recovery_enabled
        }
        
        if self.last_successful_call:
            status_info["last_successful_call"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", 
                time.localtime(self.last_successful_call)
            )
        
        return status_info
    
    async def process_image_attachments(self, message_attachments: List) -> List[Dict]:
        """Discordメッセージの添付ファイルから画像データを処理（並列処理対応）"""
        if not message_attachments:
            self.logger.info("📝 画像添付なし")
            return []
        
        self.logger.info(f"🔍 画像添付ファイル処理開始: {len(message_attachments)}個の添付ファイル")
        
        # 画像データの収集用リスト
        image_data = []
        
        # 並列処理で画像を処理
        async def process_single_image(attachment):
            self.logger.debug(f"添付ファイル処理中: {attachment.filename}")
            
            # 画像ファイルかチェック
            if self._is_image_file(attachment.filename):
                # 画像の詳細レベルを設定（必要に応じて調整可能）
                detail = "auto"  # "low", "high", "auto"
                
                image_info = {
                    "url": attachment.url,
                    "detail": detail,
                    "filename": attachment.filename,
                    "size": attachment.size,
                    "content_type": getattr(attachment, 'content_type', 'unknown')
                }
                
                self.logger.debug(f"✅ 画像として認識: {attachment.filename}")
                return image_info
            else:
                self.logger.debug(f"❌ 画像として認識されず: {attachment.filename}")
                return None
        
        # 並列処理で画像を処理
        import asyncio
        try:
            # 非同期処理として並列実行
            tasks = [process_single_image(att) for att in message_attachments]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 成功した結果のみを収集
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    self.logger.error(f"画像 {i+1} の処理でエラー: {result}")
                elif result:
                    image_data.append(result)
                    self.logger.info(f"✅ 画像として認識: {result['filename']}")
                    self.logger.info(f"  - URL: {result['url']}")
                    self.logger.info(f"  - サイズ: {result['size']} bytes")
                    self.logger.info(f"  - 詳細レベル: {result['detail']}")
                else:
                    self.logger.info(f"❌ 画像として認識されず: {message_attachments[i].filename}")
                    
        except Exception as e:
            self.logger.error(f"並列画像処理中にエラー: {e}")
            # フォールバック: 従来の逐次処理
            self.logger.info("🔄 並列処理に失敗、従来の逐次処理にフォールバック")
            for i, attachment in enumerate(message_attachments):
                self.logger.info(f"添付ファイル {i+1} を処理中: {attachment.filename}")
                
                if self._is_image_file(attachment.filename):
                    detail = "auto"
                    image_info = {
                        "url": attachment.url,
                        "detail": detail,
                        "filename": attachment.filename,
                        "size": attachment.size,
                        "content_type": getattr(attachment, 'content_type', 'unknown')
                    }
                    image_data.append(image_info)
                    self.logger.info(f"✅ 画像として認識: {attachment.filename}")
                else:
                    self.logger.info(f"❌ 画像として認識されず: {attachment.filename}")
        
        self.logger.info(f"📊 画像処理結果: {len(image_data)}個の画像を認識")
        return image_data
    
    def _is_image_file(self, filename: str) -> bool:
        """ファイル名から画像ファイルかどうかを判定"""
        if not filename:
            self.logger.debug("ファイル名が空のため、画像ファイルとして認識しません")
            return False
        
        # 画像ファイルの拡張子
        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff', '.tga'}
        
        # ファイル名を小文字に変換して拡張子をチェック
        file_lower = filename.lower()
        is_image = any(file_lower.endswith(ext) for ext in image_extensions)
        
        # 詳細ログ出力
        if is_image:
            self.logger.debug(f"✅ 画像ファイルとして認識: {filename} (拡張子: {[ext for ext in image_extensions if file_lower.endswith(ext)]})")
        else:
            self.logger.debug(f"❌ 画像ファイルとして認識されず: {filename}")
            self.logger.debug(f"  - 検出された拡張子: {[ext for ext in image_extensions if file_lower.endswith(ext)]}")
            self.logger.debug(f"  - サポートされている拡張子: {sorted(image_extensions)}")
        
        return is_image
    

    
    async def start_health_monitoring(self):
        """接続状態の継続監視を開始"""
        if not self.auto_recovery_enabled:
            return
        
        self.logger.info("OpenAI API接続状態の継続監視を開始しました")
        
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)
                
                # 接続状態をチェック
                if self.connection_status in ["degraded", "failed"]:
                    self.logger.info("接続状態が不安定です。自動復元を試行中...")
                    await self._attempt_recovery()
                    
            except asyncio.CancelledError:
                self.logger.info("OpenAI API接続状態監視を停止しました")
                break
            except Exception as e:
                self.logger.error(f"接続状態監視中にエラー: {e}")
                await asyncio.sleep(10)  # エラー時は10秒待機
