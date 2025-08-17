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


class OpenAIHandler:
    """OpenAI API通信ハンドラー"""
    
    def __init__(self):
        self.api_key = os.getenv('OPENAI_API_KEY')
        self.base_url = "https://api.openai.com/v1"
        self.logger = logging.getLogger(__name__)
        
        # レート制限設定（動的調整対応）
        self.rate_limiter = AsyncLimiter(max_rate=50, time_period=60)  # 60秒間に50リクエスト
        self.current_rate_limit = 50
        
        # リクエスト設定
        self.timeout = aiohttp.ClientTimeout(total=30)
        self.max_retries = 3
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
        max_completion_tokens: int = 2000,
        temperature: float = 1.0,  # GPT-5はtemperature=1のみサポート
        function_definitions: List[Dict] = None
    ) -> AsyncGenerator[str, None]:
        """ストリーミングレスポンスを生成"""
        
        if not self.api_key:
            yield "エラー: OpenAI APIキーが設定されていません"
            return
        
        # 接続状態をチェック（自動復元を試行）
        connection_attempts = 0
        max_connection_attempts = 3
        
        while connection_attempts < max_connection_attempts:
            if await self._check_connection_health():
                break
            
            connection_attempts += 1
            if connection_attempts < max_connection_attempts:
                self.logger.warning(f"OpenAI API接続が不安定です。自動復元を試行中... (試行 {connection_attempts}/{max_connection_attempts})")
                yield f"接続が不安定です。自動復元を試行中... (試行 {connection_attempts}/{max_connection_attempts})"
                await asyncio.sleep(2)  # 2秒待機してから再試行
            else:
                self.logger.error("OpenAI API接続の自動復元に失敗しました。手動での再試行をお願いします。")
                yield "エラー: OpenAI APIへの接続が不安定です。しばらく待ってから再試行してください。"
                return
            
        # システムプロンプトを構築
        system_prompt = self._build_system_prompt(character_data)
        
        # リクエストデータを構築
        request_data = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            "max_completion_tokens": max_completion_tokens,  # GPT-5では max_completion_tokens を使用
            "stream": True
        }
        
        # ファンクションコールが有効な場合、関数定義を追加
        if function_definitions:
            request_data["tools"] = function_definitions
            request_data["tool_choice"] = "auto"
        
        # GPT-5では temperature=1 がデフォルトなので、1以外の場合のみ指定
        if temperature != 1.0:
            request_data["temperature"] = temperature
        
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
                self.logger.error("OpenAI API タイムアウト")
                self._update_connection_status(success=False, error_type="timeout")
                retry_count += 1
                if retry_count >= self.max_retries:
                    yield "エラー: OpenAI APIがタイムアウトしました"
                    return
                await asyncio.sleep(self.retry_delay * retry_count)
                
            except Exception as e:
                self.logger.error(f"OpenAI API 呼び出しエラー: {e}")
                self._update_connection_status(success=False, error_type="exception", error=str(e))
                retry_count += 1
                if retry_count >= self.max_retries:
                    yield f"エラー: OpenAI API呼び出し中に問題が発生しました: {str(e)}"
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
        max_completion_tokens: int = 2000,
        temperature: float = 1.0
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
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": context}
            ],
            "max_completion_tokens": max_completion_tokens,
            "tools": function_definitions,
            "tool_choice": "auto"
        }
        
        # GPT-5では temperature=1 がデフォルトなので、1以外の場合のみ指定
        if temperature != 1.0:
            request_data["temperature"] = temperature
        
        try:
            # レート制限チェック
            await self.rate_limiter.acquire()
            
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
                        return {
                            "success": True,
                            "response": response_data,
                            "choices": response_data.get("choices", [])
                        }
                    else:
                        error_text = await response.text()
                        return {
                            "success": False,
                            "error": f"OpenAI API エラー - HTTP {response.status}: {error_text}"
                        }
                        
        except Exception as e:
            return {
                "success": False,
                "error": f"リクエスト実行中にエラー: {str(e)}"
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
            
    async def test_connection(self) -> bool:
        """OpenAI APIへの接続をテスト"""
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
                    "max_completion_tokens": 5
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
    
    async def _check_connection_health(self) -> bool:
        """接続状態の健全性をチェック"""
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
    
    async def _attempt_recovery(self) -> bool:
        """接続の自動復元を試行"""
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
