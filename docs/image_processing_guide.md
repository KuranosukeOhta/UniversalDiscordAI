# 画像処理とOpenAI API統合ガイド

このガイドでは、画像処理とOpenAI APIを使用して画像を認識・処理する方法について説明します。

## 概要

`ImageProcessor`クラスは、以下の機能を提供します：

- 画像ファイルの読み込み（ローカルファイル、URL）
- 画像の前処理（リサイズ、形式変換）
- OpenAI Vision APIを使用した画像分析
- テキスト抽出
- 画像の詳細説明生成
- 画像メタデータの取得

## セットアップ

### 1. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 2. OpenAI APIキーの設定

環境変数にOpenAI APIキーを設定してください：

```bash
export OPENAI_API_KEY="your-api-key-here"
```

または、`.env`ファイルに記述：

```env
OPENAI_API_KEY=your-api-key-here
```

## 基本的な使用方法

### ImageProcessorの初期化

```python
from src.image_processor import create_image_processor

# 環境変数からAPIキーを自動取得
processor = create_image_processor()

# または、直接APIキーを指定
processor = create_image_processor("your-api-key-here")
```

### 画像の読み込み

```python
# ローカルファイルから読み込み
image = processor.load_image("path/to/image.jpg")

# URLから読み込み
image = processor.load_image_from_url("https://example.com/image.jpg")

# 画像が正常に読み込まれたかチェック
if image is not None:
    print(f"画像サイズ: {image.shape}")
else:
    print("画像の読み込みに失敗しました")
```

### 画像の分析

```python
# 基本的な画像分析
analysis = processor.analyze_image_with_openai(
    "path/to/image.jpg",
    prompt="この画像に何が写っていますか？",
    max_tokens=500
)

if analysis:
    print(f"分析結果: {analysis}")
```

### テキスト抽出

```python
# 画像からテキストを抽出
extracted_text = processor.extract_text_from_image("path/to/image.jpg")

if extracted_text:
    print(f"抽出されたテキスト: {extracted_text}")
```

### 画像の詳細説明

```python
# 高詳細レベルの説明
description = processor.describe_image("path/to/image.jpg", detail_level="high")

if description:
    print(f"詳細説明: {description}")
```

### 画像の前処理

```python
# 画像の読み込み
image = processor.load_image("path/to/image.jpg")

if image is not None:
    # リサイズ（最大1024ピクセル）
    resized = processor.resize_image(image, max_size=1024)
    
    # 保存
    processor.save_image(resized, "output/resized_image.jpg")
```

### 画像メタデータの取得

```python
metadata = processor.get_image_metadata("path/to/image.jpg")

if metadata:
    print(f"幅: {metadata['width']}")
    print(f"高さ: {metadata['height']}")
    print(f"チャンネル数: {metadata['channels']}")
    print(f"アスペクト比: {metadata['aspect_ratio']}")
    print(f"総ピクセル数: {metadata['total_pixels']}")
```

## 高度な使用方法

### カスタムプロンプトでの分析

```python
# 特定の目的に特化したプロンプト
custom_prompt = """
この画像を分析して、以下の観点から評価してください：
1. 視覚的な要素
2. 感情的な印象
3. 技術的な品質
4. 改善の提案
"""

analysis = processor.analyze_image_with_openai(
    "path/to/image.jpg",
    prompt=custom_prompt,
    max_tokens=800
)
```

### バッチ処理

```python
import os
from pathlib import Path

# ディレクトリ内の全画像を処理
image_dir = Path("images")
image_files = list(image_dir.glob("*.jpg")) + list(image_dir.glob("*.png"))

for image_file in image_files:
    print(f"処理中: {image_file.name}")
    
    # 画像分析
    analysis = processor.analyze_image_with_openai(
        str(image_file),
        prompt="この画像の内容を簡潔に説明してください"
    )
    
    if analysis:
        print(f"結果: {analysis}")
    else:
        print("分析に失敗しました")
```

### エラーハンドリング

```python
import logging

# ログレベルの設定
logging.basicConfig(level=logging.INFO)

try:
    # 画像処理
    result = processor.analyze_image_with_openai("path/to/image.jpg")
    
    if result:
        print(f"成功: {result}")
    else:
        print("画像の分析に失敗しました")
        
except Exception as e:
    logging.error(f"エラーが発生しました: {e}")
```

## サポートされている画像形式

- **入力形式**: JPEG, PNG, BMP, TIFF, WebP
- **出力形式**: JPEG, PNG
- **推奨形式**: JPEG（ファイルサイズと品質のバランスが良い）

## パフォーマンスの最適化

### 画像サイズの制限

OpenAI APIでは、画像の最大サイズが制限されています。`resize_image`メソッドを使用して、適切なサイズに調整してください：

```python
# 大きな画像を自動的にリサイズ
image = processor.load_image("large_image.jpg")
resized = processor.resize_image(image, max_size=1024)
```

### バッチ処理の効率化

```python
# 複数の画像を並行処理
import asyncio
import aiofiles

async def process_image_async(processor, image_path):
    """非同期で画像を処理"""
    return processor.analyze_image_with_openai(image_path)

async def process_multiple_images(processor, image_paths):
    """複数の画像を並行処理"""
    tasks = [process_image_async(processor, path) for path in image_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results
```

## トラブルシューティング

### よくある問題

1. **OpenAI APIキーが設定されていない**
   ```
   Error: OpenAI client not initialized
   ```
   → 環境変数`OPENAI_API_KEY`を設定してください

2. **画像ファイルが見つからない**
   ```
   Error: Image file not found: path/to/image.jpg
   ```
   → ファイルパスが正しいか確認してください

3. **画像の読み込みに失敗**
   ```
   Error: Failed to load image: path/to/image.jpg
   ```
   → ファイルが破損していないか、サポートされている形式か確認してください

4. **API制限エラー**
   ```
   Error: Rate limit exceeded
   ```
   → APIの使用制限を確認し、必要に応じて待機してください

### デバッグのヒント

```python
import logging

# 詳細なログを有効化
logging.basicConfig(level=logging.DEBUG)

# 画像処理の各段階でログを出力
processor = create_image_processor()
image = processor.load_image("path/to/image.jpg")

if image is not None:
    print(f"画像読み込み成功: {image.shape}")
    
    # メタデータを確認
    metadata = processor.get_image_metadata(image)
    print(f"メタデータ: {metadata}")
    
    # リサイズ
    resized = processor.resize_image(image, max_size=1024)
    print(f"リサイズ後: {resized.shape}")
```

## サンプルコード

完全なサンプルコードは`examples/image_analysis_example.py`を参照してください。

### インタラクティブモード

```bash
python examples/image_analysis_example.py --interactive
```

このモードでは、画像パスやURLを入力して、リアルタイムで画像分析をテストできます。

## ライセンス

このプロジェクトは既存のプロジェクトのライセンスに従います。

## サポート

問題が発生した場合や質問がある場合は、以下の方法でサポートを受けることができます：

1. ログファイルの確認
2. エラーメッセージの詳細な分析
3. サンプルコードとの比較
4. 依存関係のバージョン確認