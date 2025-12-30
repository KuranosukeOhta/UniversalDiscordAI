#!/bin/bash
set -e

# logsディレクトリの権限を修正
# ボリュームマウントされたディレクトリの権限を確保
# このスクリプトはrootとして実行される

# ログディレクトリが存在しない場合は作成
mkdir -p /app/logs

# appユーザーに所有権を変更
if id "app" &>/dev/null; then
    chown -R app:app /app/logs 2>/dev/null || true
    chmod -R 755 /app/logs 2>/dev/null || true
fi

# appユーザーに切り替えてコマンドを実行
if id "app" &>/dev/null && [ $# -gt 0 ]; then
    # gosuを使用してappユーザーに切り替え（引数を適切に処理）
    exec gosu app "$@"
else
    # appユーザーが存在しない場合、または引数がない場合は、そのまま実行
    exec "$@"
fi

