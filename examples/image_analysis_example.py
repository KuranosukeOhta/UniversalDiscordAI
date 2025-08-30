#!/usr/bin/env python3
"""
Example script demonstrating image processing and OpenAI API integration
"""

import os
import sys
import logging
from pathlib import Path

# Add src directory to path
sys.path.append(str(Path(__file__).parent.parent / "src"))

from image_processor import ImageProcessor, create_image_processor

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Main function demonstrating image processing capabilities"""
    
    # Check if OpenAI API key is available
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable not set")
        logger.info("Please set your OpenAI API key:")
        logger.info("export OPENAI_API_KEY='your-api-key-here'")
        return
    
    # Create image processor
    processor = create_image_processor()
    
    # Example 1: Analyze image from file
    logger.info("=== Example 1: Analyzing image from file ===")
    
    # You can replace this with your own image path
    image_path = "sample_image.jpg"
    
    if os.path.exists(image_path):
        # Get image metadata
        metadata = processor.get_image_metadata(image_path)
        if metadata:
            logger.info(f"Image metadata: {metadata}")
        
        # Analyze image with OpenAI
        analysis = processor.analyze_image_with_openai(
            image_path,
            prompt="Describe this image in detail. What do you see?",
            max_tokens=500
        )
        
        if analysis:
            logger.info(f"Image analysis: {analysis}")
        else:
            logger.error("Failed to analyze image")
    else:
        logger.warning(f"Sample image not found: {image_path}")
        logger.info("Please place an image file named 'sample_image.jpg' in the examples directory")
    
    # Example 2: Extract text from image
    logger.info("\n=== Example 2: Extracting text from image ===")
    
    if os.path.exists(image_path):
        extracted_text = processor.extract_text_from_image(image_path)
        if extracted_text:
            logger.info(f"Extracted text: {extracted_text}")
        else:
            logger.error("Failed to extract text from image")
    
    # Example 3: Describe image with different detail levels
    logger.info("\n=== Example 3: Image descriptions with different detail levels ===")
    
    if os.path.exists(image_path):
        for detail in ["low", "high"]:
            description = processor.describe_image(image_path, detail_level=detail)
            if description:
                logger.info(f"{detail.capitalize()} detail description: {description}")
            else:
                logger.error(f"Failed to get {detail} detail description")
    
    # Example 4: Process image from URL
    logger.info("\n=== Example 4: Processing image from URL ===")
    
    # Example image URL (replace with your own)
    sample_url = "https://example.com/sample-image.jpg"
    
    try:
        # Get metadata from URL
        metadata = processor.get_image_metadata(sample_url)
        if metadata:
            logger.info(f"URL image metadata: {metadata}")
        
        # Analyze image from URL
        analysis = processor.analyze_image_with_openai(
            sample_url,
            prompt="What's in this image?",
            max_tokens=300
        )
        
        if analysis:
            logger.info(f"URL image analysis: {analysis}")
        else:
            logger.error("Failed to analyze image from URL")
            
    except Exception as e:
        logger.warning(f"Could not process image from URL (this is expected for the example URL): {e}")
    
    # Example 5: Image preprocessing
    logger.info("\n=== Example 5: Image preprocessing ===")
    
    if os.path.exists(image_path):
        # Load image
        image = processor.load_image(image_path)
        if image is not None:
            logger.info(f"Original image shape: {image.shape}")
            
            # Resize image
            resized = processor.resize_image(image, max_size=512)
            logger.info(f"Resized image shape: {resized.shape}")
            
            # Save resized image
            output_path = "examples/resized_sample_image.jpg"
            if processor.save_image(resized, output_path):
                logger.info(f"Resized image saved to: {output_path}")
            else:
                logger.error("Failed to save resized image")


def interactive_mode():
    """Interactive mode for testing image processing"""
    
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("OPENAI_API_KEY environment variable not set")
        return
    
    processor = create_image_processor()
    
    logger.info("=== Interactive Image Processing Mode ===")
    logger.info("Enter 'quit' to exit")
    
    while True:
        try:
            # Get user input
            user_input = input("\nEnter image path/URL or 'quit': ").strip()
            
            if user_input.lower() == 'quit':
                break
            
            if not user_input:
                continue
            
            # Check if it's a URL
            if user_input.startswith(('http://', 'https://')):
                logger.info(f"Processing image from URL: {user_input}")
                image_source = user_input
            else:
                # Check if file exists
                if not os.path.exists(user_input):
                    logger.error(f"File not found: {user_input}")
                    continue
                logger.info(f"Processing image file: {user_input}")
                image_source = user_input
            
            # Get user prompt
            prompt = input("Enter analysis prompt (or press Enter for default): ").strip()
            if not prompt:
                prompt = "Describe this image in detail"
            
            # Process image
            logger.info("Processing image...")
            result = processor.analyze_image_with_openai(image_source, prompt)
            
            if result:
                logger.info(f"Result: {result}")
            else:
                logger.error("Failed to process image")
                
        except KeyboardInterrupt:
            logger.info("\nExiting...")
            break
        except Exception as e:
            logger.error(f"Error: {e}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Image processing and OpenAI API integration example")
    parser.add_argument("--interactive", "-i", action="store_true", 
                       help="Run in interactive mode")
    
    args = parser.parse_args()
    
    if args.interactive:
        interactive_mode()
    else:
        main()