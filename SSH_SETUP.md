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
# .env.exampleをコピーして.env.localを作成
cp .env.example .env.local

# .env.localを編集（nano、vi、vimなど使用）
nano .env.local
```

`.env.local` に以下の情報を設定：

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

**重要**: Dockerの権限エラーが発生する場合は、以下のいずれかの方法を使用してください。

#### 方法A: sudoを使用（推奨：即座に使用可能）

```bash
# sudoを使用してビルドと起動
sudo docker-compose up --build -d

# 起動状態を確認
sudo docker-compose ps

# ログを確認（リアルタイム）
sudo docker-compose logs -f discord-ai
```

#### 方法B: dockerグループに追加（推奨：再ログイン後）

```bash
# ユーザーをdockerグループに追加
sudo usermod -aG docker $USER

# 再ログインが必要（SSH接続を切断して再接続）
exit

# SSHで再接続後、sudoなしで実行可能
docker-compose up --build -d
docker-compose ps
docker-compose logs -f discord-ai
```

#### 方法C: 通常のコマンド（権限が設定済みの場合）

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

**注意**: 権限エラーが発生する場合は、すべてのコマンドに`sudo`を付けてください。

```bash
# リアルタイムログ
docker-compose logs -f discord-ai
# または
sudo docker-compose logs -f discord-ai

# 最新100行のログ
docker-compose logs --tail=100 discord-ai
# または
sudo docker-compose logs --tail=100 discord-ai

# エラーログのみ
docker-compose logs discord-ai | grep ERROR
# または
sudo docker-compose logs discord-ai | grep ERROR
```

### コンテナの管理

```bash
# 停止
docker-compose down
# または
sudo docker-compose down

# 再起動
docker-compose restart discord-ai
# または
sudo docker-compose restart discord-ai

# 強制再ビルド
docker-compose up --build --force-recreate -d
# または
sudo docker-compose up --build --force-recreate -d
```

### 状態確認

```bash
# コンテナの状態
docker-compose ps
# または
sudo docker-compose ps

# リソース使用量
docker stats universal-discord-ai
# または
sudo docker stats universal-discord-ai

# ヘルスチェック
docker exec universal-discord-ai python -c "import asyncio; print('Bot is running')"
# または
sudo docker exec universal-discord-ai python -c "import asyncio; print('Bot is running')"
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

### 権限エラーの場合（Permission denied）

**症状**: `PermissionError: [Errno 13] Permission denied` が発生

#### 解決方法1: sudoを使用（即座に解決）

```bash
# すべてのdocker-composeコマンドにsudoを付ける
sudo docker-compose up --build -d
sudo docker-compose ps
sudo docker-compose logs -f discord-ai
sudo docker-compose down
```

#### 解決方法2: dockerグループに追加（推奨）

```bash
# 現在のユーザーをdockerグループに追加
sudo usermod -aG docker $USER

# グループの変更を確認
groups

# 重要: 再ログインが必要
exit

# SSHで再接続後、sudoなしで実行可能
docker-compose up --build -d
```

#### 解決方法3: Dockerソケットの権限を確認

```bash
# Dockerソケットの権限を確認
ls -la /var/run/docker.sock

# 一時的に権限を変更（非推奨、セキュリティ上の問題あり）
# sudo chmod 666 /var/run/docker.sock
```

**注意**: 解決方法2を推奨しますが、再ログインが必要です。すぐに使用したい場合は解決方法1（sudo）を使用してください。

### 環境変数が読み込まれない場合

```bash
# .env.localの存在確認
ls -la .env.local

# ファイルの内容確認（トークンは表示されないように注意）
cat .env.local | grep -v TOKEN | grep -v KEY

# 権限の確認
chmod 600 .env.local
```

### ログファイルの権限エラー（Permission denied: '/app/logs/discord_ai.log'）

**症状**: コンテナ起動時に `[Errno 13] Permission denied: '/app/logs/discord_ai.log'` エラーが発生

**原因**: ボリュームマウントされた`logs`ディレクトリの所有権がコンテナ内の`app`ユーザーと一致していない

**解決方法**:

1. **ホスト側でlogsディレクトリの権限を修正**（推奨）:
   ```bash
   # logsディレクトリを作成（存在しない場合）
   mkdir -p logs
   
   # 書き込み可能な権限を付与
   chmod 777 logs
   ```

2. **コンテナを再ビルド**:
   ```bash
   # 最新のDockerfileにはエントリポイントスクリプトが含まれており、
   # 起動時に自動的に権限を修正します
   sudo docker-compose down
   sudo docker-compose up --build -d
   ```

3. **手動で権限を修正**:
   ```bash
   # コンテナ内で権限を修正
   sudo docker exec -u root universal-discord-ai chown -R app:app /app/logs
   sudo docker exec -u root universal-discord-ai chmod -R 755 /app/logs
   ```

**注意**: 最新のDockerfileにはエントリポイントスクリプトが含まれており、起動時に自動的に権限を修正します。コンテナを再ビルドすることで、この問題は解決されます。

## 完全なセットアップスクリプト

### 自動セットアップスクリプトを使用（推奨）

```bash
# スクリプトをダウンロードして実行
curl -O https://raw.githubusercontent.com/KuranosukeOhta/UniversalDiscordAI/main/setup_ssh.sh
chmod +x setup_ssh.sh
./setup_ssh.sh
```

このスクリプトは以下を自動で実行します：
- リポジトリのクローン
- 環境変数ファイルの作成
- Docker環境の確認
- 権限チェック（sudoが必要な場合は自動検出）
- Docker Composeでのビルドと起動

### 手動セットアップ

以下のコマンドを順番に実行することで、一括でセットアップできます：

```bash
# 1. リポジトリのクローン
git clone https://github.com/KuranosukeOhta/UniversalDiscordAI.git
cd UniversalDiscordAI

# 2. 環境変数ファイルの作成
cp env.example env.local

# 3. env.localを編集（手動でトークンとAPIキーを設定）
nano env.local
# DISCORD_BOT_TOKENとOPENAI_API_KEYを設定

# 4. Docker Composeで起動
# 権限エラーが発生する場合は、sudoを付けて実行
docker-compose up --build -d
# または
sudo docker-compose up --build -d
```

