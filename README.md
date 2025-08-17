# Universal Discord AI

GPT-5を使用したDiscord BOTプロジェクト。複数の人格を持つAIが、メンション時に自然な会話で返答します。

## 🌟 特徴

- **GPT-5 統合**: 最新のOpenAI GPT-5モデルを使用
- **ストリーミング返答**: リアルタイムでメッセージを更新
- **複数人格対応**: 異なる性格のBOTを並列実行
- **コンテキスト認識**: チャンネル情報と履歴を考慮した返答
- **動的レート制限**: API制限に応じて自動調整
- **Docker対応**: 簡単なデプロイと管理

## 📋 必要要件

- Docker & Docker Compose
- Discord Bot Token
- OpenAI API Key (GPT-5対応)

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
OPENAI_API_KEY=your_openai_api_key_here
```

### 3. Discord Bot の作成

1. [Discord Developer Portal](https://discord.com/developers/applications) にアクセス
2. 新しいアプリケーションを作成
3. BOTセクションでBOTユーザーを作成
4. TOKENをコピーして `env.local` に設定
5. BOTをサーバーに招待（必要な権限: メッセージ送信、メッセージ履歴読み取り、メンション確認）

### 4. OpenAI API Key の取得

1. [OpenAI Platform](https://platform.openai.com/api-keys) にアクセス
2. 新しいAPI Keyを作成
3. KEYをコピーして `env.local` に設定

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
    "chat_history_limit": 500,          // 取得するチャット履歴数
    "max_response_length": 16000,       // 最大レスポンス長
    "enable_typing_indicator": true     // タイピング表示
  },
  "openai_settings": {
    "model": "gpt-5",                   // 使用するモデル
    "max_completion_tokens": 16000,     // 最大トークン数
    "temperature": 1.0                  // 創造性レベル
  }
}
```

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

**OpenAI API エラー**
- API Keyが正しく設定されているか確認
- OpenAIアカウントの利用制限を確認
- GPT-5へのアクセス権限を確認

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

**Universal Discord AI** - GPT-5を使用した次世代Discord BOT

