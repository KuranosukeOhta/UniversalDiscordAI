# Universal Discord AI - セットアップガイド

このガイドでは、Universal Discord AIを初回セットアップから運用開始まで詳しく説明します。

## 📋 事前準備チェックリスト

- [ ] Docker がインストールされている
- [ ] Docker Compose がインストールされている  
- [ ] Discord Developer アカウントがある
- [ ] OpenRouter アカウントがある
- [ ] 管理者権限でDiscordサーバーにアクセスできる

## 🔧 詳細セットアップ手順

### Step 1: Discord BOT の作成と設定

#### 1.1 Discord Developer Portal での設定

1. [Discord Developer Portal](https://discord.com/developers/applications) にアクセス
2. 「New Application」をクリック
3. アプリケーション名を入力（例：Universal Discord AI）
4. 「Create」をクリック

#### 1.2 BOT ユーザーの作成

1. 左側メニューから「Bot」を選択
2. 「Add Bot」をクリック
3. 「Yes, do it!」で確認
4. BOT設定を調整：
   - **Username**: Universal Discord AI
   - **Public Bot**: OFF（推奨）
   - **Requires OAuth2 Code Grant**: OFF
   - **Presence Intent**: ON
   - **Server Members Intent**: ON
   - **Message Content Intent**: ON（重要！）

#### 1.3 BOT Token の取得

1. 「Token」セクションで「Copy」をクリック
2. トークンを安全な場所に保存（後で使用）

#### 1.4 BOT の招待設定

1. 左側メニューから「OAuth2」→「URL Generator」を選択
2. **Scopes** で「bot」をチェック
3. **Bot Permissions** で以下をチェック：
   - Send Messages
   - Use Slash Commands  
   - Read Message History
   - Add Reactions
   - Use External Emojis
   - Mention Everyone
4. 生成されたURLをコピー

#### 1.5 サーバーへの招待

1. コピーしたURLをブラウザで開く
2. BOTを招待するサーバーを選択
3. 権限を確認して「認証」をクリック

### Step 2: OpenRouter API の設定

#### 2.1 OpenRouter アカウントの準備

1. [OpenRouter](https://openrouter.ai/) にアクセス
2. アカウントを作成またはログイン
3. 利用制限と課金設定を確認

#### 2.2 API Key の作成

1. [OpenRouter Keys ページ](https://openrouter.ai/keys) にアクセス
2. 「Create Key」をクリック
3. キー名を入力（例：Discord AI Bot）
4. 生成されたキーをコピーして安全に保存

### Step 3: プロジェクトのセットアップ

#### 3.1 ファイルのダウンロード

```bash
# プロジェクトディレクトリに移動
cd /path/to/UniversalDiscordAI

# ファイル構造を確認
ls -la
```

#### 3.2 環境変数の設定

```bash
# .env.local ファイルを作成
cp .env.example .env.local

# エディタで .env.local を編集
nano .env.local
```

`.env.local` ファイルの内容：

```env
# Discord Bot Token（Step 1.3で取得）
DISCORD_BOT_TOKEN=MTIzNDU2Nzg5MDEyMzQ1Njc4.Xxxxxx.xxxxxxxxxxxxxxxxxxxxxxxxxxxx

# OpenRouter API Key（Step 2.2で取得）
# Note: 変数名はOPENAI_API_KEYですが、OpenRouterのAPIキーを設定してください
OPENAI_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Bot Configuration
BOT_NAME=Universal Discord AI
LOG_LEVEL=INFO

# Optional: Custom bot status
BOT_STATUS=Monitoring channels...
BOT_ACTIVITY_TYPE=watching
```

#### 3.3 設定ファイルの調整

`config/config.json` を必要に応じて編集：

```json
{
  "bot_settings": {
    "chat_history_limit": 100,
    "context_token_limit": 125000,
    "rate_limit_adjustment": true,
    "typing_indicator_enabled": true,
    "max_response_length": 2000,
    "stream_update_interval": 0.5
  },
  "character_settings": {
    "default_character": "friendly"
  }
}
```

### Step 4: Docker での起動

#### 4.1 初回ビルドと起動

```bash
# イメージをビルドして起動
docker-compose up --build -d

# 起動状態を確認
docker-compose ps
```

#### 4.2 ログの確認

```bash
# リアルタイムログを表示
docker-compose logs -f discord-ai

# 特定の時間のログを確認
docker-compose logs --since="2024-01-01T00:00:00" discord-ai
```

#### 4.3 正常起動の確認

ログで以下のメッセージを確認：

```
INFO - Universal Discord AI を初期化中...
INFO - 人格設定を読み込みました: ['friendly', 'professional', 'creative']
INFO - BOTインスタンスを作成しました: 3個
INFO - Universal Discord AI として Discord に接続しました
```

### Step 5: 動作テスト

#### 5.1 基本的な返答テスト

1. BOTが参加しているDiscordチャンネルに移動
2. 以下のようにメンションして送信：
   ```
   @Universal Discord AI こんにちは！調子はどう？
   ```

3. BOTからの返答を確認

#### 5.2 人格別テスト

現在の実装では、デフォルト人格（friendly）が使用されます。

#### 5.3 エラーハンドリングテスト

```
@Universal Discord AI 非常に長いテキストを送信してコンテキスト制限をテスト...（2000文字以上のテキスト）
```

### Step 6: 運用開始後の監視

#### 6.1 定期的な監視項目

```bash
# BOTの稼働状況
docker-compose ps

# リソース使用量
docker stats universal-discord-ai

# ディスク使用量
du -sh logs/
```

#### 6.2 ログローテーション設定

`docker-compose.yml` でログローテーションが設定済み：

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
```

#### 6.3 バックアップの設定

重要なファイルの定期バックアップ：

```bash
# 設定ファイルのバックアップ
tar -czf backup_$(date +%Y%m%d).tar.gz config/ characters/ .env.local

# 定期実行の設定（cron）
0 2 * * * cd /path/to/UniversalDiscordAI && tar -czf backup_$(date +\%Y\%m\%d).tar.gz config/ characters/ .env.local
```

## 🔧 カスタマイズガイド

### 人格設定のカスタマイズ

#### 新しい人格の追加

1. `characters/` フォルダに新しい `.md` ファイルを作成
2. 以下のテンプレートを使用：

```markdown
# 人格名: カスタム人格

## 基本性格
ここに基本的な性格を記述

## 話し方の特徴
- 話し方の特徴1
- 話し方の特徴2

## 専門分野・得意なこと
- 専門分野1
- 専門分野2

## 返答例の傾向
- 「例文1」
- 「例文2」

## 避けるべき表現
- 避けるべき表現1
- 避けるべき表現2
```

3. BOTを再起動：
```bash
docker-compose restart discord-ai
```

### 設定の詳細調整

#### レスポンス速度の調整

```json
{
  "bot_settings": {
    "stream_update_interval": 0.3  // 更新間隔を短縮（高速化）
  }
}
```

#### メモリ使用量の調整

```json
{
  "bot_settings": {
    "chat_history_limit": 50  // 履歴取得数を削減
  }
}
```

## 🚨 トラブルシューティング

### 一般的な問題と解決方法

#### BOTが起動しない

**症状**: `docker-compose up` でエラーが発生

**解決方法**:
1. 環境変数を確認：
   ```bash
   cat .env.local
   ```

2. Docker ログを確認：
   ```bash
   docker-compose logs discord-ai
   ```

3. 権限を確認：
   ```bash
   ls -la .env.local
   chmod 600 .env.local
   ```

#### BOTが返答しない

**症状**: メンションしても反応がない

**解決方法**:
1. BOTのオンライン状態を確認
2. メッセージ内容インテントが有効か確認
3. BOTの権限を確認（メッセージ送信権限）
4. ログでエラーを確認

#### OpenRouter API エラー

**症状**: "OpenRouter API エラー" メッセージが表示

**解決方法**:
1. API キーの有効性を確認
2. OpenRouter アカウントの利用制限を確認
3. Gemini モデルへのアクセス権限を確認
4. ネットワーク接続を確認

#### メモリ不足エラー

**症状**: コンテナが頻繁に再起動

**解決方法**:
1. Docker のメモリ制限を確認
2. `chat_history_limit` を削減
3. 不要なログファイルを削除

### 緊急時の対応

#### BOTの緊急停止

```bash
# 即座に停止
docker-compose down

# 強制停止
docker-compose kill
```

#### 設定の初期化

```bash
# 設定ファイルを初期状態に戻す
cp config/config.json.backup config/config.json

# コンテナを再ビルド
docker-compose up --build --force-recreate -d
```

#### ログの緊急確認

```bash
# 最新のエラーログを確認
docker-compose logs --tail=100 discord-ai | grep ERROR

# システムリソースを確認
docker stats --no-stream
```

## 📞 サポート・連絡先

問題が解決しない場合：

1. **GitHub Issues**: 技術的な問題
2. **ログファイル**: `logs/discord_ai.log` を確認
3. **Discord Developer Portal**: BOT設定の確認
4. **OpenRouter Platform**: API使用状況の確認

---

このセットアップガイドに従って、Universal Discord AI を正常に運用開始できます。追加の質問や問題がある場合は、遠慮なくお知らせください。
