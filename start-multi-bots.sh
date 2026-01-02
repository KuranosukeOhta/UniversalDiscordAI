#!/bin/bash

# Universal Discord AI - Multi-Character Bot Startup Script
# このスクリプトは複数のキャラクターBOTを同時起動します

set -e

echo "=========================================="
echo "Universal Discord AI - Multi-Character Bot"
echo "=========================================="
echo ""

# env.localファイルの存在確認
if [ ! -f "env.local" ]; then
    echo "❌ エラー: env.local ファイルが見つかりません"
    echo "📝 env.example をコピーして env.local を作成してください:"
    echo "   cp env.example env.local"
    echo ""
    echo "   編集して以下の環境変数を設定してください:"
    echo "   - DISCORD_BOT_TOKEN_FRIENDLY"
    echo "   - DISCORD_BOT_TOKEN_PROFESSIONAL"
    echo "   - OPENROUTER_API_KEY"
    exit 1
fi

# 必要な環境変数の確認
# set -a を使って環境変数をエクスポート
set -a
source env.local
set +a

if [ -z "$DISCORD_BOT_TOKEN_FRIENDLY" ]; then
    echo "⚠️  警告: DISCORD_BOT_TOKEN_FRIENDLY が設定されていません"
fi

if [ -z "$DISCORD_BOT_TOKEN_PROFESSIONAL" ]; then
    echo "⚠️  警告: DISCORD_BOT_TOKEN_PROFESSIONAL が設定されていません"
fi

# OpenRouter または OpenAI API Key のチェック
if [ -z "$OPENROUTER_API_KEY" ] && [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ エラー: OPENROUTER_API_KEY または OPENAI_API_KEY が設定されていません"
    exit 1
fi

if [ -n "$OPENROUTER_API_KEY" ]; then
    echo "✅ OpenRouter API Key が設定されています"
elif [ -n "$OPENAI_API_KEY" ]; then
    echo "✅ OpenAI API Key が設定されています"
fi

# ログディレクトリの作成
echo "📁 ログディレクトリを作成中..."
mkdir -p logs/friendly logs/professional logs/creative

# Docker Composeでビルド・起動
echo ""
echo "🚀 Docker Compose でBOTを起動中..."
echo ""

# 既存のコンテナを停止・削除
docker-compose down

# イメージをビルド
docker-compose build

# コンテナを起動
docker-compose up -d

echo ""
echo "✅ BOTの起動が完了しました！"
echo ""
echo "📊 起動中のコンテナ:"
docker-compose ps

echo ""
echo "📋 ログを確認するには:"
echo "   全体: docker-compose logs -f"
echo "   Friendly: docker-compose logs -f bot-friendly"
echo "   Professional: docker-compose logs -f bot-professional"
echo ""
echo "🛑 停止するには:"
echo "   docker-compose down"
echo ""

