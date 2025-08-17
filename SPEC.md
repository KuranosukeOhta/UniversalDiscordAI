# Universal Discord AI - 仕様書

## プロジェクト概要
Discord BOTを開発し、Docker上に構築する。サーバー上の全チャンネルを常時監視し、メンションされた場合のみOpenAI GPT-5を使用して返答するAIボット。

## 基本仕様

### 1. 環境・構築
- **プラットフォーム**: Docker上に構築
- **言語**: Python
- **名前**: Universal Discord AI

### 2. 監視・返答機能
- **監視対象**: サーバー上の全チャンネル（チャンネル・スレッド両対応）
- **返答条件**: @でメンションされている場合のみ
- **AI モデル**: OpenAI GPT-5
- **コンテキスト制限**: 125K tokens

### 3. 返答処理
- **ストリーミング**: 有効
- **レート制限**: 動的調整機能付き
- **表示方法**: 
  - 1回目の更新編集まで: typing indicatorを有効化
  - その後: コメント編集でテキストを適宜更新

### 4. コンテキスト取得
- **チャット履歴**: 直近100件まで取得（設定ファイルで変更可能）
- **取得内容**: 発言者・発言内容
- **チャンネル情報**: チャンネル名、topic（概要説明）を取得
- **コンテキスト制限チェック**: モデルの125K制限を超えないよう監視
- **取得タイミング**: 発言毎に毎回コンテキストを取得し直す

### 5. 人格設定機能
- **設定ファイル**: character.md形式
- **選択権限**: 管理者のみ
- **並列処理**: 複数の人格を同時に動作させる（複数BOTが常駐）
- **保存方式**: ファイルベース（DB不使用）
- **読み込み**: 実行時に複数のコンテキストファイルから選択

### 6. エラーハンドリング
- **OpenAI API利用不可時**: チャットにエラーメッセージを送信
- **Discord API制限時**: チャットにエラーメッセージを送信

## 技術仕様

### API認証情報
```
OPENAI_API_KEY: GPT-5 API用
DISCORD_BOT_TOKEN: Discord BOT用
```

### 設定ファイル
- **.env.example**: 環境変数テンプレート
- **.env.local**: 実際のAPIキー配置用
- **config.json**: BOT動作設定（チャット履歴取得件数等）

### プロジェクト構造
```
UniversalDiscordAI/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── .env.local
├── config/
│   └── config.json
├── characters/
│   ├── friendly.md
│   ├── professional.md
│   └── creative.md
├── src/
│   ├── bot.py
│   ├── character_manager.py
│   ├── openai_handler.py
│   └── utils.py
├── requirements.txt
└── SPEC.md
```

## 動作フロー

1. **起動時**
   - 複数の人格設定を読み込み
   - 各人格に対応するBOTインスタンスを起動
   - Discord接続確立

2. **メッセージ受信時**
   - 全チャンネルを監視
   - メンション検知
   - 該当する人格のBOTが応答

3. **返答生成時**
   - typing indicator開始
   - チャンネル情報取得（名前・topic）
   - 直近100件のチャット履歴取得
   - コンテキスト制限チェック
   - GPT-5にストリーミングリクエスト
   - レート制限を動的調整
   - 初回編集まで typing indicator維持
   - 以降はメッセージ編集で更新

4. **エラー発生時**
   - エラーメッセージをチャットに送信
   - ログ出力

## 設定項目

### config.json
```json
{
  "chat_history_limit": 100,
  "context_token_limit": 125000,
  "rate_limit_adjustment": true,
  "typing_indicator_enabled": true
}
```

### 人格設定ファイル例
```markdown
# 人格名: フレンドリー

## 基本性格
親しみやすく、明るい性格で返答します。

## 話し方
- 敬語は使わず、親しみやすい口調
- 絵文字を適度に使用
- 相手の気持ちに寄り添う

## 専門分野
- 雑談
- 相談
- エンターテイメント
```

## 制約事項
- データベースは使用しない
- ファイルベースでの設定管理
- 複数BOTの並列処理に対応
- コンテキスト制限内での動作保証
