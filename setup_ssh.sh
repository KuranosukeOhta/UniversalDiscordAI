#!/bin/bash

# Universal Discord AI - SSH環境セットアップスクリプト
# このスクリプトはSSH環境でリポジトリをクローンしてDockerを起動します

set -e  # エラーが発生したら停止

echo "=========================================="
echo "Universal Discord AI - SSH環境セットアップ"
echo "=========================================="
echo ""

# リポジトリURL
REPO_URL="https://github.com/KuranosukeOhta/UniversalDiscordAI.git"
REPO_NAME="UniversalDiscordAI"

# 1. リポジトリのクローン
echo "[1/4] リポジトリをクローン中..."
if [ -d "$REPO_NAME" ]; then
    echo "  既に $REPO_NAME ディレクトリが存在します。"
    read -p "  削除して再クローンしますか？ (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$REPO_NAME"
        git clone "$REPO_URL"
    else
        echo "  既存のディレクトリを使用します。"
    fi
else
    git clone "$REPO_URL"
fi

cd "$REPO_NAME"
echo "  ✓ クローン完了"
echo ""

# 2. 環境変数ファイルの確認
echo "[2/4] 環境変数ファイルを確認中..."
if [ ! -f "env.local" ]; then
    echo "  env.localが存在しません。env.exampleから作成します..."
    cp env.example env.local
    echo "  ✓ env.localを作成しました"
    echo ""
    echo "  ⚠️  重要: env.localを編集して、以下を設定してください:"
    echo "     - DISCORD_BOT_TOKEN"
    echo "     - OPENAI_API_KEY"
    echo ""
    echo "  編集コマンド例:"
    echo "    nano env.local"
    echo "    または"
    echo "    vi env.local"
    echo ""
    read -p "  今すぐ編集しますか？ (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        ${EDITOR:-nano} env.local
    fi
else
    echo "  ✓ env.localが存在します"
fi
echo ""

# 3. DockerとDocker Composeの確認
echo "[3/4] Docker環境を確認中..."
if ! command -v docker &> /dev/null; then
    echo "  ✗ Dockerがインストールされていません"
    echo "    インストール方法:"
    echo "      Ubuntu/Debian: sudo apt-get install -y docker.io"
    echo "      CentOS/RHEL: sudo yum install -y docker"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "  ✗ Docker Composeがインストールされていません"
    echo "    インストール方法:"
    echo "      Ubuntu/Debian: sudo apt-get install -y docker-compose"
    echo "      CentOS/RHEL: sudo yum install -y docker-compose"
    exit 1
fi

echo "  ✓ Docker環境が確認できました"
echo ""

# 4. Docker Composeでビルドと起動
echo "[4/4] Docker Composeでビルドと起動中..."
echo ""

# env.localの内容を確認（トークンは表示しない）
if grep -q "your_discord_bot_token_here\|your_openai_api_key_here" env.local; then
    echo "  ⚠️  警告: env.localにデフォルト値が残っています"
    echo "      DISCORD_BOT_TOKENとOPENAI_API_KEYを正しく設定してください"
    echo ""
    read -p "  続行しますか？ (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "  セットアップを中断しました。env.localを編集してから再実行してください。"
        exit 1
    fi
fi

echo "  Docker Composeでビルドと起動を実行します..."
docker-compose up --build -d

echo ""
echo "=========================================="
echo "セットアップ完了！"
echo "=========================================="
echo ""
echo "以下のコマンドで状態を確認できます:"
echo "  docker-compose ps              # コンテナの状態"
echo "  docker-compose logs -f discord-ai  # ログの確認"
echo ""
echo "BOTが正常に起動しているか確認してください。"
echo ""

