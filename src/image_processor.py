"""
Image processing utilities for OpenAI API integration
"""

import os
import base64
import io
import logging
from typing import Optional, Union, List, Dict, Any
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import requests
from openai import OpenAI

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Image processing utilities for OpenAI API integration"""
    
    def __init__(self, openai_client: Optional[OpenAI] = None):
        """
        Initialize ImageProcessor
        
        Args:
            openai_client: OpenAI client instance (optional)
        """
        self.openai_client = openai_client
        
    def load_image(self, image_path: Union[str, Path]) -> Optional[np.ndarray]:
        """
        Load image from file path
        
        Args:
            image_path: Path to image file
            
        Returns:
            Loaded image as numpy array or None if failed
        """
        try:
            if not os.path.exists(image_path):
                logger.error(f"Image file not found: {image_path}")
                return None
                
            image = cv2.imread(str(image_path))
            if image is None:
                logger.error(f"Failed to load image: {image_path}")
                return None
                
            # Convert BGR to RGB (OpenCV loads as BGR)
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            return image_rgb
            
        except Exception as e:
            logger.error(f"Error loading image {image_path}: {e}")
            return None
    
    def load_image_from_url(self, url: str) -> Optional[np.ndarray]:
        """
        Load image from URL
        
        Args:
            url: URL of the image
            
        Returns:
            Loaded image as numpy array or None if failed
        """
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            
            # Convert to numpy array
            image_array = np.frombuffer(response.content, dtype=np.uint8)
            image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
            
            if image is None:
                logger.error(f"Failed to decode image from URL: {url}")
                return None
                
            # Convert BGR to RGB
            image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
            return image_rgb
            
        except Exception as e:
            logger.error(f"Error loading image from URL {url}: {e}")
            return None
    
    def resize_image(self, image: np.ndarray, max_size: int = 1024) -> np.ndarray:
        """
        Resize image while maintaining aspect ratio
        
        Args:
            image: Input image as numpy array
            max_size: Maximum dimension size
            
        Returns:
            Resized image
        """
        height, width = image.shape[:2]
        
        if height <= max_size and width <= max_size:
            return image
            
        # Calculate scaling factor
        scale = min(max_size / height, max_size / width)
        new_height = int(height * scale)
        new_width = int(width * scale)
        
        # Resize image
        resized = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)
        return resized
    
    def encode_image_to_base64(self, image: np.ndarray, format: str = "JPEG", quality: int = 95) -> Optional[str]:
        """
        Encode image to base64 string for OpenAI API
        
        Args:
            image: Input image as numpy array
            format: Image format (JPEG, PNG)
            quality: JPEG quality (1-100)
            
        Returns:
            Base64 encoded image string or None if failed
        """
        try:
            # Convert numpy array to PIL Image
            pil_image = Image.fromarray(image)
            
            # Create buffer
            buffer = io.BytesIO()
            
            if format.upper() == "JPEG":
                pil_image.save(buffer, format="JPEG", quality=quality, optimize=True)
            else:
                pil_image.save(buffer, format=format)
            
            # Get base64 string
            buffer.seek(0)
            image_bytes = buffer.getvalue()
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            
            return base64_string
            
        except Exception as e:
            logger.error(f"Error encoding image to base64: {e}")
            return None
    
    def save_image(self, image: np.ndarray, output_path: Union[str, Path], format: str = "JPEG") -> bool:
        """
        Save image to file
        
        Args:
            image: Input image as numpy array
            output_path: Output file path
            format: Image format
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert RGB to BGR for OpenCV
            if len(image.shape) == 3:
                image_bgr = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
            else:
                image_bgr = image
                
            # Ensure directory exists
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            
            # Save image
            success = cv2.imwrite(str(output_path), image_bgr)
            return success
            
        except Exception as e:
            logger.error(f"Error saving image to {output_path}: {e}")
            return False
    
    def analyze_image_with_openai(
        self, 
        image: Union[np.ndarray, str, Path], 
        prompt: str = "Describe this image in detail",
        model: str = "gpt-4-vision-preview",
        max_tokens: int = 300
    ) -> Optional[str]:
        """
        Analyze image using OpenAI Vision API
        
        Args:
            image: Input image (numpy array, file path, or URL)
            prompt: Text prompt for image analysis
            model: OpenAI model to use
            max_tokens: Maximum tokens in response
            
        Returns:
            Analysis result or None if failed
        """
        if not self.openai_client:
            logger.error("OpenAI client not initialized")
            return None
            
        try:
            # Load and process image
            if isinstance(image, (str, Path)):
                if image.startswith(('http://', 'https://')):
                    image_array = self.load_image_from_url(str(image))
                else:
                    image_array = self.load_image(image)
            else:
                image_array = image
                
            if image_array is None:
                logger.error("Failed to load image")
                return None
            
            # Resize if too large
            image_array = self.resize_image(image_array, max_size=1024)
            
            # Encode to base64
            base64_image = self.encode_image_to_base64(image_array)
            if not base64_image:
                logger.error("Failed to encode image")
                return None
            
            # Prepare message for OpenAI API
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]
            
            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"Error analyzing image with OpenAI: {e}")
            return None
    
    def extract_text_from_image(
        self, 
        image: Union[np.ndarray, str, Path],
        prompt: str = "Extract all text visible in this image. If there's no text, say 'No text found'."
    ) -> Optional[str]:
        """
        Extract text from image using OpenAI Vision API
        
        Args:
            image: Input image
            prompt: Prompt for text extraction
            
        Returns:
            Extracted text or None if failed
        """
        return self.analyze_image_with_openai(image, prompt)
    
    def describe_image(
        self, 
        image: Union[np.ndarray, str, Path],
        detail_level: str = "high"
    ) -> Optional[str]:
        """
        Generate detailed description of image
        
        Args:
            image: Input image
            detail_level: Detail level (low, high)
            
        Returns:
            Image description or None if failed
        """
        prompt = f"Provide a {detail_level} detail description of this image. Include visual elements, objects, people, actions, colors, and any notable details."
        return self.analyze_image_with_openai(image, prompt)
    
    def get_image_metadata(self, image: Union[np.ndarray, str, Path]) -> Optional[Dict[str, Any]]:
        """
        Get basic image metadata
        
        Args:
            image: Input image
            
        Returns:
            Dictionary with image metadata or None if failed
        """
        try:
            if isinstance(image, (str, Path)):
                if image.startswith(('http://', 'https://')):
                    image_array = self.load_image_from_url(str(image))
                else:
                    image_array = self.load_image(image)
            else:
                image_array = image
                
            if image_array is None:
                return None
            
            height, width = image_array.shape[:2]
            channels = image_array.shape[2] if len(image_array.shape) > 2 else 1
            
            metadata = {
                "width": width,
                "height": height,
                "channels": channels,
                "aspect_ratio": width / height,
                "total_pixels": width * height
            }
            
            return metadata
            
        except Exception as e:
            logger.error(f"Error getting image metadata: {e}")
            return None


def create_image_processor(openai_api_key: Optional[str] = None) -> ImageProcessor:
    """
    Factory function to create ImageProcessor with OpenAI client
    
    Args:
        openai_api_key: OpenAI API key (optional, can use environment variable)
        
    Returns:
        ImageProcessor instance
    """
    if openai_api_key:
        client = OpenAI(api_key=openai_api_key)
    else:
        # Try to get from environment variable
        client = OpenAI()
        
    return ImageProcessor(client)