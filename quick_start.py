#!/usr/bin/env python3
"""
Quick start script for image processing with OpenAI API
"""

import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.append(str(Path(__file__).parent / "src"))

def main():
    """Quick start example"""
    
    print("🚀 OpenAI API 画像処理 クイックスタート")
    print("=" * 50)
    
    # Check OpenAI API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ OPENAI_API_KEY 環境変数が設定されていません")
        print("以下のコマンドで設定してください：")
        print("export OPENAI_API_KEY='your-api-key-here'")
        return
    
    try:
        from image_processor import create_image_processor
        
        # Create image processor
        print("✅ 画像プロセッサーを初期化中...")
        processor = create_image_processor()
        
        # Check if we have a sample image
        sample_image = "sample_image.jpg"
        if os.path.exists(sample_image):
            print(f"📸 サンプル画像を発見: {sample_image}")
            
            # Get image metadata
            print("📊 画像メタデータを取得中...")
            metadata = processor.get_image_metadata(sample_image)
            if metadata:
                print(f"   幅: {metadata['width']}px")
                print(f"   高さ: {metadata['height']}px")
                print(f"   チャンネル数: {metadata['channels']}")
            
            # Analyze image
            print("🔍 OpenAI APIで画像を分析中...")
            analysis = processor.analyze_image_with_openai(
                sample_image,
                prompt="この画像に何が写っていますか？簡潔に説明してください。",
                max_tokens=200
            )
            
            if analysis:
                print("📝 分析結果:")
                print(f"   {analysis}")
            else:
                print("❌ 画像の分析に失敗しました")
                
        else:
            print(f"📸 サンプル画像が見つかりません: {sample_image}")
            print("画像ファイルを配置してから再実行してください")
            
        print("\n🎉 クイックスタート完了！")
        print("\n次のステップ:")
        print("1. examples/image_analysis_example.py で詳細な例を確認")
        print("2. docs/image_processing_guide.md で使用方法を学習")
        print("3. 独自の画像でテスト")
        
    except ImportError as e:
        print(f"❌ インポートエラー: {e}")
        print("依存関係をインストールしてください: pip install -r requirements.txt")
    except Exception as e:
        print(f"❌ エラーが発生しました: {e}")


if __name__ == "__main__":
    main()