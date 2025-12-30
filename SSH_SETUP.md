# SSH環境でのセットアップ手順

このドキュメントでは、SSH環境にリポジトリをクローンしてDockerで起動する手順を説明します。

## 前提条件

- SSH環境にDockerとDocker Composeがインストールされていること
- Discord Bot TokenとOpenAI API Keyを準備していること

## セットアップ手順

### 1. リポジトリのクローン

```bash
# 正しいURLでクローン（#は含めない）
git clone https://github.com/KuranosukeOhta/UniversalDiscordAI.git
cd UniversalDiscordAI
```

### 2. 環境変数ファイルの作成

```bash
# env.exampleをコピーしてenv.localを作成
cp env.example env.local

# env.localを編集（nano、vi、vimなど使用）
nano env.local
```

`env.local` に以下の情報を設定：

```env
# Discord Bot Token
DISCORD_BOT_TOKEN=your_actual_discord_bot_token_here

# OpenAI API Key
OPENAI_API_KEY=your_actual_openai_api_key_here

# Bot Configuration
BOT_NAME=Universal Discord AI
LOG_LEVEL=INFO

# Optional: Custom bot status
BOT_STATUS=Monitoring channels...
BOT_ACTIVITY_TYPE=watching
```

### 3. Docker Composeでビルドと起動

```bash
# イメージをビルドしてバックグラウンドで起動
docker-compose up --build -d

# 起動状態を確認
docker-compose ps

# ログを確認（リアルタイム）
docker-compose logs -f discord-ai
```

### 4. 正常起動の確認

ログで以下のメッセージが表示されることを確認：

```
INFO - Universal Discord AI を初期化中...
INFO - 人格設定を読み込みました: ['friendly', 'professional', 'creative']
INFO - BOTインスタンスを作成しました: 3個
INFO - Universal Discord AI として Discord に接続しました
```

## よくあるコマンド

### ログの確認

```bash
# リアルタイムログ
docker-compose logs -f discord-ai

# 最新100行のログ
docker-compose logs --tail=100 discord-ai

# エラーログのみ
docker-compose logs discord-ai | grep ERROR
```

### コンテナの管理

```bash
# 停止
docker-compose down

# 再起動
docker-compose restart discord-ai

# 強制再ビルド
docker-compose up --build --force-recreate -d
```

### 状態確認

```bash
# コンテナの状態
docker-compose ps

# リソース使用量
docker stats universal-discord-ai

# ヘルスチェック
docker exec universal-discord-ai python -c "import asyncio; print('Bot is running')"
```

## トラブルシューティング

### Dockerがインストールされていない場合

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y docker.io docker-compose

# CentOS/RHEL
sudo yum install -y docker docker-compose

# Dockerサービスの起動
sudo systemctl start docker
sudo systemctl enable docker
```

### 権限エラーの場合

```bash
# ユーザーをdockerグループに追加
sudo usermod -aG docker $USER

# 再ログインが必要
exit
# SSHで再接続
```

### 環境変数が読み込まれない場合

```bash
# env.localの存在確認
ls -la env.local

# ファイルの内容確認（トークンは表示されないように注意）
cat env.local | grep -v TOKEN | grep -v KEY

# 権限の確認
chmod 600 env.local
```

## 完全なセットアップスクリプト

以下のコマンドを順番に実行することで、一括でセットアップできます：

```bash
# 1. リポジトリのクローン
git clone https://github.com/KuranosukeOhta/UniversalDiscordAI.git
cd UniversalDiscordAI

# 2. 環境変数ファイルの作成
cp env.example env.local

# 3. env.localを編集（手動でトークンとAPIキーを設定）
echo "env.localを編集して、DISCORD_BOT_TOKENとOPENAI_API_KEYを設定してください"
echo "編集後、docker-compose up --build -d を実行してください"

# 4. Docker Composeで起動（env.localを編集した後）
# docker-compose up --build -d
```

