# Universal Discord AI

Universal Discord AIは、OpenAIのGPT-5モデルを使用した高度なDiscord BOTです。複数の人格設定に対応し、非同期処理による高パフォーマンスな会話体験を提供します。

## 特徴

- 🤖 **GPT-5対応**: 最新のOpenAI GPT-5モデルを使用
- 🎭 **複数人格対応**: 複数の人格設定を動的に切り替え可能
- ⚡ **非同期処理**: 高パフォーマンスな同時メッセージ処理
- 🔄 **連続会話**: 自然な会話の流れを維持
- 📊 **詳細ログ**: 包括的なログ出力とパフォーマンス監視
- 🛡️ **エラー回復**: 自動的なエラー回復とヘルスチェック

## 設定ファイルの詳細説明

### `config/config.json` - 設定ファイル

#### Discord設定 (`discord_settings`)
- `status`: BOTのステータス表示（Discordで表示される活動内容）
- `admin_commands_enabled`: 管理者コマンドの有効化（!status等）
- `enable_auto_status_update`: 自動ステータス更新の有効化
- `command_prefix`: コマンドのプレフィックス（デフォルト: !ai）
- `enable_slash_commands`: スラッシュコマンドの有効化
- `status_check_command`: ステータス確認コマンド（デフォルト: !status）
- `enable_help_command`: ヘルプコマンドの有効化

#### BOT動作設定 (`bot_settings`)
- `continuous_conversation_enabled`: 連続会話の有効化（前のメッセージがBOTの場合も反応）
- `max_conversation_turns`: 最大会話ターン数
- `max_concurrent_messages`: 最大同時処理メッセージ数
- `message_timeout_seconds`: メッセージ処理のタイムアウト時間（秒）
- `enable_task_cleanup`: タスククリーンアップの有効化
- `enable_error_recovery`: エラー回復機能の有効化
- `max_error_retries`: 最大エラーリトライ回数
- `cleanup_interval_seconds`: クリーンアップ実行間隔（秒）
- `enable_performance_metrics`: パフォーマンスメトリクスの有効化

#### 人格設定 (`character_settings`)
- `default_character`: デフォルトで使用する人格
- `character_switching_enabled`: 人格切り替え機能の有効化
- `enable_character_rotation`: 人格ローテーション機能の有効化
- `character_rotation_interval`: 人格ローテーション間隔（秒）

#### 一般設定 (`general_settings`)
- `chat_history_limit`: チャット履歴の取得制限数
- `max_response_length`: 最大レスポンス長
- `enable_streaming`: ストリーミングレスポンスの有効化
- `enable_typing_indicator`: タイピングインジケーターの有効化
- `typing_duration`: タイピング表示時間（秒）
- `streaming_update_interval`: ストリーミング更新間隔（ミリ秒）
- `enable_message_editing`: メッセージ編集機能の有効化

#### OpenAI API設定 (`openai_settings`)
- `model`: 使用するAIモデル（デフォルト: gpt-5）
- `max_completion_tokens`: 最大完了トークン数
- `max_context_tokens`: 最大コンテキストトークン数
- `temperature`: 創造性の度合い（0.0-1.0、GPT-5では1.0固定）
- `timeout_seconds`: API呼び出しのタイムアウト時間（秒）
- `retry_attempts`: リトライ試行回数
- `enable_fallback_model`: フォールバックモデルの有効化
- `health_check_interval`: ヘルスチェック間隔（秒）
- `enable_rate_limit_monitoring`: レート制限監視の有効化

#### ログ設定 (`logging_settings`)
- `log_level`: ログレベル（DEBUG, INFO, WARNING, ERROR, CRITICAL）
- `enable_detailed_logging`: 詳細ログ出力の有効化
- `enable_performance_monitoring`: パフォーマンス監視の有効化
- `enable_memory_monitoring`: メモリ監視の有効化
- `log_to_file`: ファイルログ出力の有効化
- `log_directory`: ログディレクトリ
- `log_to_console`: コンソールログ出力の有効化
- `enable_color_logging`: カラーログ出力の有効化
- `log_rotation`: ログローテーションの有効化
- `log_retention_days`: ログ保持日数
- `max_log_size_mb`: 最大ログファイルサイズ（MB）
- `enable_compression`: ログ圧縮の有効化

## プログラムファイルの説明

### 1. `src/bot.py` - メインBOT実装
- **役割**: Discord BOTのメイン実装クラス
- **機能**: 
  - Discord APIとの通信管理
  - メッセージ処理と人格設定の統合
  - 非同期処理による同時メッセージ対応
  - タスク管理とクリーンアップ
  - 統計情報の収集と管理

### 2. `src/bot_async.py` - 非同期処理最適化版
- **役割**: `bot.py`の非同期処理最適化版
- **機能**: 
  - より効率的な同時処理制御
  - 設定ファイルからの動的パラメータ読み込み
  - パフォーマンスメトリクスの強化
  - エラー回復機能の改善

### 3. `src/character_manager.py` - 人格設定管理
- **役割**: 複数の人格設定ファイルの管理
- **機能**: 
  - Markdown形式の人格設定ファイルの読み込み
  - 人格設定の動的切り替え
  - 人格設定の妥当性検証
  - AIコンテキスト用の人格設定文字列生成

### 4. `src/openai_handler.py` - OpenAI API通信管理
- **役割**: OpenAI APIとの通信を管理
- **機能**: 
  - GPT-5モデルとの通信
  - ストリーミングレスポンスの処理
  - レート制限の管理
  - 接続状態の監視と自動復元
  - エラーハンドリングとリトライ機能

### 5. `src/utils.py` - 共通ユーティリティ
- **役割**: 共通のユーティリティ関数とクラス
- **機能**: 
  - 設定ファイル管理
  - トークン数カウントと制限管理
  - ログ設定と管理
  - 費用計算
  - 詳細ログ出力

## セットアップ

詳細なセットアップ手順は [SETUP.md](SETUP.md) を参照してください。

## 使用方法

1. 環境変数を設定（`env.local`ファイル）
2. 人格設定ファイルを`characters/`ディレクトリに配置
3. `python src/bot.py` または `python src/bot_async.py` で実行

## 人格設定

人格設定は`characters/`ディレクトリ内のMarkdownファイルで管理されます。各ファイルには以下のセクションを含めることができます：

- 基本性格
- 話し方・口調
- 専門分野・得意なこと
- 返答例
- 避けるべき表現・行動
- その他の特徴

## ライセンス

このプロジェクトはMITライセンスの下で公開されています。
