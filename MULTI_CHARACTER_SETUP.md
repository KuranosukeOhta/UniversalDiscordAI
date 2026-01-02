# 複数キャラクター同時起動セットアップガイド

このガイドでは、Universal Discord AIで複数のキャラクターを同時に異なるBOTアカウントで起動する方法を説明します。

## 📋 目次

1. [概要](#概要)
2. [前提条件](#前提条件)
3. [セットアップ手順](#セットアップ手順)
4. [起動方法](#起動方法)
5. [管理コマンド](#管理コマンド)
6. [トラブルシューティング](#トラブルシューティング)

---

## 🎯 概要

Docker Composeを使用して、複数のキャラクター（friendly, professionalなど）をそれぞれ独立したBOTアカウントとして同時起動します。

### メリット

- ✅ 各キャラクターが完全に独立したBOTアカウント
- ✅ 異なるサーバー・チャンネルで同時に動作可能
- ✅ 1つのキャラクターがクラッシュしても他に影響なし
- ✅ リソース管理が明確
- ✅ スケーラビリティが高い

---

## 📦 前提条件

### 必要なもの

1. **Docker & Docker Compose**
   ```bash
   # インストール確認
   docker --version
   docker-compose --version
   ```

2. **Discord BOTアカウント（各キャラクター分）**
   - [Discord Developer Portal](https://discord.com/developers/applications) で作成
   - 必要な権限:
     - Read Messages/View Channels
     - Send Messages
     - Read Message History
     - Add Reactions
     - Use Slash Commands
     - Mention Everyone（オプション）

3. **OpenRouter API Key または OpenAI API Key**
   - [OpenRouter](https://openrouter.ai/) (推奨)
   - または [OpenAI](https://platform.openai.com/)

---

## 🛠️ セットアップ手順

### 1. Discord BOTの作成

各キャラクターごとに異なるBOTアカウントを作成します。

#### Friendly Character BOT

1. [Discord Developer Portal](https://discord.com/developers/applications) にアクセス
2. `New Application` をクリック
3. 名前: `UniversalAI-Friendly` (任意)
4. `Bot` タブから BOT を作成
5. `TOKEN` をコピー → `DISCORD_BOT_TOKEN_FRIENDLY` として保存

#### Professional Character BOT

1. 同様に新しいアプリケーションを作成
2. 名前: `UniversalAI-Professional` (任意)
3. `Bot` タブから BOT を作成
4. `TOKEN` をコピー → `DISCORD_BOT_TOKEN_PROFESSIONAL` として保存

### 2. BOTをサーバーに招待

各BOTをDiscordサーバーに招待します。

```
https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=274877958144&scope=bot
```

`YOUR_CLIENT_ID` を各BOTのClient IDに置き換えてください。

### 3. 環境変数の設定

```bash
# env.example をコピー
cp env.example env.local

# env.local を編集
nano env.local  # または vim, code など
```

#### env.local の設定例

```bash
# Friendly Character Bot Token
DISCORD_BOT_TOKEN_FRIENDLY=YOUR_FRIENDLY_BOT_TOKEN_HERE

# Professional Character Bot Token
DISCORD_BOT_TOKEN_PROFESSIONAL=YOUR_PROFESSIONAL_BOT_TOKEN_HERE

# OpenRouter API Key
OPENROUTER_API_KEY=YOUR_OPENROUTER_API_KEY_HERE

# オプション: OpenAI API Key
# OPENAI_API_KEY=YOUR_OPENAI_API_KEY_HERE
```

### 4. 設定の確認

```bash
# ディレクトリ構造の確認
ls -la
# 以下のファイルが存在することを確認:
# - docker-compose.yml
# - Dockerfile
# - env.local
# - start-multi-bots.sh
```

---

## 🚀 起動方法

### 簡単起動（推奨）

```bash
# 起動スクリプトを使用
./start-multi-bots.sh
```

このスクリプトは以下を自動的に実行します:
1. 環境変数のチェック
2. ログディレクトリの作成
3. Docker イメージのビルド
4. コンテナの起動

### 手動起動

```bash
# 1. ログディレクトリを作成
mkdir -p logs/friendly logs/professional

# 2. 既存のコンテナを停止（存在する場合）
docker-compose down

# 3. イメージをビルド
docker-compose build

# 4. コンテナを起動
docker-compose up -d
```

### 起動確認

```bash
# コンテナの状態を確認
docker-compose ps

# ログを確認
docker-compose logs -f
```

正常に起動すると以下のような表示が出ます:

```
bot-friendly        | ✅ Universal Discord AI を初期化中... (キャラクター: friendly)
bot-professional    | ✅ Universal Discord AI を初期化中... (キャラクター: professional)
bot-friendly        | ✅ キャラクターBOTを作成しました: friendly
bot-professional    | ✅ キャラクターBOTを作成しました: professional
```

---

## 🎮 管理コマンド

### ログの確認

```bash
# 全BOTのログを表示（リアルタイム）
docker-compose logs -f

# 特定のBOTのログのみ表示
docker-compose logs -f bot-friendly
docker-compose logs -f bot-professional

# 直近100行のログを表示
docker-compose logs --tail=100
```

### BOTの停止

```bash
# 全BOTを停止
docker-compose down

# 特定のBOTのみ停止
docker-compose stop bot-friendly
docker-compose stop bot-professional
```

### BOTの再起動

```bash
# 全BOTを再起動
docker-compose restart

# 特定のBOTのみ再起動
docker-compose restart bot-friendly
docker-compose restart bot-professional
```

### BOTのステータス確認

```bash
# コンテナの状態確認
docker-compose ps

# リソース使用状況の確認
docker stats
```

### ログファイルの確認

```bash
# Friendlyのログ
tail -f logs/friendly/discord_ai.log

# Professionalのログ
tail -f logs/professional/discord_ai.log
```

---

## 🐛 トラブルシューティング

### BOTが起動しない

#### 1. 環境変数の確認

```bash
# env.localが存在するか確認
ls -la env.local

# 環境変数が正しく設定されているか確認
source env.local
echo $DISCORD_BOT_TOKEN_FRIENDLY
echo $DISCORD_BOT_TOKEN_PROFESSIONAL
echo $OPENROUTER_API_KEY
```

#### 2. Dockerログの確認

```bash
# エラーメッセージを確認
docker-compose logs bot-friendly | grep -i error
docker-compose logs bot-professional | grep -i error
```

#### 3. コンテナの再ビルド

```bash
# キャッシュを使わずに再ビルド
docker-compose build --no-cache
docker-compose up -d
```

### BOTがDiscordに接続できない

#### トークンの確認

```bash
# トークンの形式確認（実際のトークンは表示しない）
source env.local
if [[ $DISCORD_BOT_TOKEN_FRIENDLY =~ ^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$ ]]; then
    echo "✅ FRIENDLY トークン形式OK"
else
    echo "❌ FRIENDLY トークン形式エラー"
fi
```

#### ネットワークの確認

```bash
# Dockerネットワークの確認
docker network ls | grep discord-ai-network

# コンテナがネットワークに接続されているか確認
docker network inspect discord-ai-network
```

### 1つのBOTだけ起動したい

```bash
# Friendlyのみ起動
docker-compose up -d bot-friendly

# Professionalのみ起動
docker-compose up -d bot-professional
```

### キャラクター設定を変更したい

```bash
# 1. characters/ ディレクトリのファイルを編集
nano characters/friendly.md

# 2. BOTを再起動（設定が再読み込みされる）
docker-compose restart bot-friendly
```

### メモリ不足エラー

`docker-compose.yml` のリソース制限を調整:

```yaml
deploy:
  resources:
    limits:
      memory: 2G  # 1G → 2G に増やす
      cpus: '1.0'  # 0.5 → 1.0 に増やす
```

### ログが大きくなりすぎる

ログローテーションの設定を調整:

```yaml
logging:
  driver: "json-file"
  options:
    max-size: "5m"   # 10m → 5m に減らす
    max-file: "2"    # 3 → 2 に減らす
```

---

## 📊 モニタリング

### リソース使用状況の確認

```bash
# リアルタイムでリソース使用状況を表示
docker stats

# 特定のコンテナのみ
docker stats discord-ai-friendly discord-ai-professional
```

### ヘルスチェック

```bash
# ヘルスチェックの状態確認
docker-compose ps

# 詳細なヘルスチェック情報
docker inspect discord-ai-friendly | grep -A 10 Health
```

---

## 🔧 高度な設定

### 新しいキャラクターの追加

1. **キャラクターファイルを作成**
   ```bash
   # characters/creative.md を作成
   cp characters/friendly.md characters/creative.md
   nano characters/creative.md
   ```

2. **docker-compose.yml に追加**
   ```yaml
   bot-creative:
     build:
       context: .
       dockerfile: Dockerfile
     container_name: discord-ai-creative
     restart: unless-stopped
     environment:
       - CHARACTER_NAME=creative
       - DISCORD_BOT_TOKEN=${DISCORD_BOT_TOKEN_CREATIVE}
       - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
     volumes:
       - ./config:/app/config:ro
       - ./characters:/app/characters:ro
       - ./logs/creative:/app/logs:rw
     networks:
       - discord-ai-network
   ```

3. **env.local に追加**
   ```bash
   DISCORD_BOT_TOKEN_CREATIVE=your_token_here
   ```

4. **起動**
   ```bash
   docker-compose up -d bot-creative
   ```

### 本番環境での推奨設定

```yaml
# docker-compose.prod.yml
services:
  bot-friendly:
    restart: always  # unless-stopped → always
    deploy:
      resources:
        limits:
          memory: 2G
          cpus: '1.0'
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "10"
```

起動:
```bash
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 📚 参考情報

- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [Discord.py Documentation](https://discordpy.readthedocs.io/)
- [OpenRouter API Documentation](https://openrouter.ai/docs)

---

## 💡 Tips

1. **開発環境では単一BOTで十分**
   - `python src/bot_async.py` で直接起動
   - 環境変数 `CHARACTER_NAME` で切り替え可能

2. **本番環境ではDocker Composeを推奨**
   - 安定性が高い
   - ログ管理が容易
   - 自動再起動機能

3. **リソース監視を忘れずに**
   ```bash
   # CPU/メモリ使用率の定期確認
   watch -n 5 'docker stats --no-stream'
   ```

---

## 🤝 サポート

問題が発生した場合:

1. ログを確認: `docker-compose logs -f`
2. GitHub Issues で報告
3. ドキュメントを再確認

---

**作成日**: 2026年1月2日  
**バージョン**: 1.0.0

