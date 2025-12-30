# Universal Discord AI

OpenRouter経由でGoogle Gemini 2.5 Flash Liteを使用したDiscord BOTプロジェクト。複数の人格を持つAIが、メンション時に自然な会話で返答します。

## 🌟 特徴

- **OpenRouter統合**: OpenRouter経由でGoogle Gemini 2.5 Flash Liteモデルを使用
- **画像処理対応**: 添付画像を認識・分析して返答
- **ストリーミング返答**: リアルタイムでメッセージを更新
- **複数人格対応**: 異なる性格のBOTを並列実行
- **コンテキスト認識**: チャンネル情報と履歴を考慮した返答
- **動的レート制限**: API制限に応じて自動調整
- **Docker対応**: 簡単なデプロイと管理
- **ファンクションコール**: Discord API操作の自動実行
- **チャンネル別並列処理**: 同じチャンネルでの同時メッセージを適切に管理
- **メッセージキューイング**: 処理待ちメッセージを順次処理

## 📋 必要要件

- Docker & Docker Compose
- Discord Bot Token
- OpenRouter API Key

## 🚀 セットアップ

### 1. リポジトリのクローン

```bash
git clone <your-repository-url>
cd UniversalDiscordAI
```

### 2. 環境変数の設定

```bash
# env.local ファイルを編集
cp env.example env.local
```

`env.local` に以下の情報を設定：

```env
DISCORD_BOT_TOKEN=your_discord_bot_token_here
OPENAI_API_KEY=your_openrouter_api_key_here
```

### 3. Discord Bot の作成

1. [Discord Developer Portal](https://discord.com/developers/applications) にアクセス
2. 新しいアプリケーションを作成
3. BOTセクションでBOTユーザーを作成
4. TOKENをコピーして `env.local` に設定
5. BOTをサーバーに招待（必要な権限: メッセージ送信、メッセージ履歴読み取り、メンション確認）

### 4. OpenRouter API Key の取得

1. [OpenRouter](https://openrouter.ai/) にアクセス
2. アカウントを作成またはログイン
3. API Keysセクションで新しいAPI Keyを作成
4. KEYをコピーして `env.local` の `OPENAI_API_KEY` に設定
   - 注: 環境変数名は `OPENAI_API_KEY` ですが、OpenRouterのAPIキーを設定してください

### 5. Docker でのビルドと実行

```bash
# ビルドと起動
docker-compose up --build -d

# ログの確認
docker-compose logs -f discord-ai

# 停止
docker-compose down
```

## ⚙️ 設定

### config/config.json

```json
{
  "bot_settings": {
    "max_concurrent_messages": 20,      // 全体の最大同時処理数
    "max_concurrent_per_channel": 3,    // チャンネル別の最大同時処理数
    "chat_history_limit": 500,          // 取得するチャット履歴数
    "max_response_length": 16000,       // 最大レスポンス長
    "enable_typing_indicator": true     // タイピング表示
  },
  "openai_settings": {
    "model": "google/gemini-2.5-flash-lite",  // 使用するモデル
    "max_completion_tokens": 16000,           // 最大トークン数
    "temperature": 1.0,                       // 創造性レベル
    "timeout_seconds": 120,                   // APIタイムアウト（秒）
    "function_call_timeout": 30               // ファンクションコールタイムアウト（秒）
  }
}
```

## 🖼️ 画像処理機能

AIが添付された画像を認識・分析し、画像の内容に基づいた返答を生成します。

### 対応画像形式

- **JPEG/JPG**: 一般的な写真形式
- **PNG**: 透過対応画像
- **GIF**: アニメーション画像
- **WebP**: 高圧縮画像
- **BMP**: ビットマップ画像
- **TIFF**: 高品質画像
- **TGA**: Targa画像

### 使用方法

1. 画像を添付してメッセージを送信
2. BOTをメンション（@BOT名）
3. AIが画像を分析して適切な返答を生成

### 設定

```json
{
  "openai_settings": {
    "vision_model": "google/gemini-2.5-flash-lite",
    "image_processing_enabled": true,
    "max_image_size_mb": 20
  }
}
```

## 🚀 並列処理機能

### チャンネル別並列処理制御

同じチャンネルで同時に複数のメッセージが送信された場合、適切に並列処理を行います：

- **チャンネル別セマフォ**: 各チャンネルで最大3件まで同時処理
- **グローバル制限**: 全体で最大20件まで同時処理
- **自動キューイング**: 制限に達した場合、メッセージをキューに追加

### メッセージキューイングシステム

処理待ちのメッセージを適切に管理します：

- **順次処理**: キュー内のメッセージを順番に処理
- **ユーザー通知**: キューに追加されたことをユーザーに通知
- **自動管理**: キュー処理タスクの自動開始・終了

### 設定例

```json
{
  "bot_settings": {
    "max_concurrent_messages": 20,      // 全体の最大同時処理数
    "max_concurrent_per_channel": 3     // チャンネル別の最大同時処理数
  }
}
```

### 動作例

1. **チャンネルA**で3件のメッセージが同時に送信
   - 1件目: 即座に処理開始
   - 2件目: 即座に処理開始  
   - 3件目: 即座に処理開始
   - 4件目以降: キューに追加、順番待ち

2. **チャンネルB**で2件のメッセージが同時に送信
   - 1件目: 即座に処理開始
   - 2件目: 即座に処理開始
   - 3件目以降: キューに追加、順番待ち

これにより、各チャンネルでの処理が適切に分散され、ユーザー体験が向上します。

## 🔧 ファンクションコール機能

AIが自然言語の指示を理解し、Discord API操作を自動実行します。

### 利用可能な操作

- **スレッド名変更**: 「スレッド名を〜に変えておいて」
- **チャンネル名変更**: 「チャンネル名を〜に変更して」

### 使用方法

1. 管理者権限を持つユーザーがAIに指示
2. AIが自動的に適切な関数を呼び出し
3. Discord APIで操作を実行
4. 結果をチャットに報告

### 設定

```json
{
  "function_call_settings": {
    "enabled": true,
    "allowed_operations": ["edit_thread", "edit_channel"],
    "require_admin": true
  }
}
```

### コマンド

- `!ai functions`: 利用可能な機能一覧を表示

## 🎭 人格設定

`characters/` フォルダに Markdown 形式で人格を定義：

### 例: characters/friendly.md

```markdown
# 人格名: フレンドリー

## 基本性格
親しみやすく、明るい性格で返答します。

## 話し方の特徴
- 敬語は使わず、親しみやすい口調
- 絵文字を適度に使用
- 相手の気持ちに寄り添う

## 専門分野・得意なこと
- 雑談・日常会話
- 悩み相談・メンタルサポート
```

### デフォルト人格

- **friendly**: 親しみやすい性格
- **professional**: 専門的で丁寧
- **creative**: 創造的でアーティスティック

## 🔧 使用方法

1. BOTをDiscordサーバーに招待
2. チャンネルでBOTをメンション: `@Universal Discord AI こんにちは！`
3. BOTが人格設定に従って返答

## 📊 監視とログ

### ログファイル

- `logs/discord_ai.log`: 全ての動作ログ
- Docker logs: `docker-compose logs discord-ai`

### ヘルスチェック

```bash
# BOTの状態確認
docker-compose ps

# 詳細なヘルスチェック
docker exec universal-discord-ai python -c "import asyncio; print('Bot is running')"
```

## 🛠️ 開発・カスタマイズ

### プロジェクト構造

```
UniversalDiscordAI/
├── src/
│   ├── bot.py                 # メインBOTロジック
│   ├── character_manager.py   # 人格管理
│   ├── openai_handler.py      # OpenAI API処理
│   └── utils.py              # ユーティリティ
├── characters/               # 人格設定ファイル
├── config/                  # 設定ファイル
├── logs/                    # ログファイル
├── docker-compose.yml       # Docker設定
└── Dockerfile              # コンテナ設定
```

### 新しい人格の追加

1. `characters/new_personality.md` を作成
2. Markdown形式で人格を定義
3. BOTを再起動

### 設定の変更

1. `config/config.json` を編集
2. BOTを再起動

## 🔍 トラブルシューティング

### よくある問題

**BOTが返答しない**
- BOTが正しくメンションされているか確認
- Discord BOTの権限を確認
- ログでエラーを確認: `docker-compose logs discord-ai`

**OpenRouter API エラー**
- API Keyが正しく設定されているか確認
- OpenRouterアカウントの利用制限を確認
- Geminiモデルへのアクセス権限を確認

**コンテキスト制限エラー**
- `chat_history_limit` を減らす
- 長すぎるメッセージを避ける

### デバッグモード

```bash
# 開発モードで起動
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# ログレベルをDEBUGに変更
# config/config.json の logging.level を "DEBUG" に設定
```

## 📝 ライセンス

このプロジェクトはMITライセンスの下で公開されています。

## 🤝 コントリビューション

1. このリポジトリをフォーク
2. フィーチャーブランチを作成
3. 変更をコミット
4. プルリクエストを作成

## 📞 サポート

問題や質問がある場合は、GitHubのIssuesページでお知らせください。

---

**Universal Discord AI** - OpenRouter経由でGoogle Gemini 2.5 Flash Liteを使用した次世代Discord BOT

