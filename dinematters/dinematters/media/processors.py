# Copyright (c) 2026, Hetvi Patel and contributors
# For license information, please see license.txt

"""
Media processing utilities for images and videos
"""

import os
import subprocess
from PIL import Image
import frappe
from dinematters.dinematters.utils.common import safe_log_error


class ImageProcessor:
	"""Process images - resize, optimize, convert to WebP"""
	
	def __init__(self, source_path, output_dir):
		self.source_path = source_path
		self.output_dir = output_dir
	
	def generate_blur_placeholder(self):
		"""
		Generate tiny blurred placeholder for progressive image loading (Instagram-style)
		
		Creates a small, blurred version that preserves the actual image colors and content
		
		Returns:
			Base64 encoded data URI of blurred placeholder (~1-2KB)
		"""
		try:
			import base64
			from io import BytesIO
			from PIL import ImageFilter, ImageOps
			
			with Image.open(self.source_path) as img:
				# Normalize orientation based on EXIF
				try:
					img = ImageOps.exif_transpose(img)
				except:
					pass
				
				# Convert to RGB if needed
				if img.mode in ('RGBA', 'LA', 'P'):
					background = Image.new('RGB', img.size, (255, 255, 255))
					if img.mode == 'P':
						img = img.convert('RGBA')
					background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
					img = background
				elif img.mode != 'RGB':
					img = img.convert('RGB')
				
				# Create small version maintaining aspect ratio (40px on longest side)
				# Larger than before to preserve more detail before blur
				img.thumbnail((40, 40), Image.Resampling.LANCZOS)
				
				# Apply moderate Gaussian blur (less aggressive than before)
				img = img.filter(ImageFilter.GaussianBlur(radius=2))
				
				# Save to bytes with low quality but not too aggressive
				buffer = BytesIO()
				img.save(buffer, format='JPEG', quality=40, optimize=True)
				
				# Convert to base64 data URI
				img_data = base64.b64encode(buffer.getvalue()).decode()
				data_uri = f"data:image/jpeg;base64,{img_data}"
				
				return data_uri
		
		except Exception as e:
			safe_log_error("Blur Placeholder Error", str(e))
			return None
	
	def create_variant(self, variant_name, max_size, quality=75):
		"""
		Create image variant
		
		Args:
			variant_name: Name of variant (e.g., 'thumb', 'md', 'lg')
			max_size: Maximum dimension (width or height)
			quality: WebP quality (1-100)
		
		Returns:
			Path to created variant file
		"""
		try:
			with Image.open(self.source_path) as img:
				# Convert RGBA to RGB if needed
				if img.mode in ('RGBA', 'LA', 'P'):
					# Create white background
					background = Image.new('RGB', img.size, (255, 255, 255))
					if img.mode == 'P':
						img = img.convert('RGBA')
					background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
					img = background
				elif img.mode != 'RGB':
					img = img.convert('RGB')
				
				# Normalize orientation based on EXIF
				try:
					from PIL import ImageOps
					img = ImageOps.exif_transpose(img)
				except:
					pass
				
				# Calculate new size maintaining aspect ratio
				width, height = img.size
				if width > height:
					new_width = min(width, max_size)
					new_height = int(height * (new_width / width))
				else:
					new_height = min(height, max_size)
					new_width = int(width * (new_height / height))
				
				# Resize
				img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
				
				# Save as WebP
				output_path = os.path.join(self.output_dir, f"{variant_name}.webp")
				img.save(
					output_path,
					"WEBP",
					quality=quality,
					method=6,  # Slowest but best compression
					optimize=True
				)
				
				return output_path
		
		except Exception as e:
			safe_log_error(f"Image Processing Error - {variant_name}", str(e))
			return None


class VideoProcessor:
	"""Process videos - transcode, generate poster"""
	
	def __init__(self, source_path, output_dir):
		self.source_path = source_path
		self.output_dir = output_dir
	
	def get_metadata(self):
		"""Get video metadata using ffprobe"""
		try:
			cmd = [
				'ffprobe',
				'-v', 'error',
				'-select_streams', 'v:0',
				'-show_entries', 'stream=width,height,duration',
				'-of', 'json',
				self.source_path
			]
			
			result = subprocess.run(cmd, capture_output=True, text=True, check=True)
			
			import json
			data = json.loads(result.stdout)
			
			if 'streams' in data and len(data['streams']) > 0:
				stream = data['streams'][0]
				return {
					'width': stream.get('width'),
					'height': stream.get('height'),
					'duration': float(stream.get('duration', 0))
				}
			
			return {}
		
		except Exception as e:
			safe_log_error("Video Metadata Error", str(e))
			return {}
	
	def create_720p_variant(self):
		"""Create 720p MP4 variant"""
		try:
			output_path = os.path.join(self.output_dir, "video_720p.mp4")
			
			cmd = [
				'ffmpeg',
				'-i', self.source_path,
				'-vf', 'scale=-2:720',  # -2 maintains aspect ratio with even width
				'-c:v', 'libx264',
				'-crf', '28',
				'-preset', 'fast',
				'-c:a', 'aac',
				'-b:a', '128k',
				'-movflags', '+faststart',  # Enable progressive streaming
				'-y',  # Overwrite output
				output_path
			]
			
			subprocess.run(cmd, check=True, capture_output=True)
			
			return output_path
		
		except subprocess.CalledProcessError as e:
			safe_log_error("Video Processing Error - FFmpeg", e.stderr.decode() if e.stderr else str(e))
			return None
		except Exception as e:
			safe_log_error("Video Processing Error", str(e))
			return None
	
	def create_poster(self, timestamp=1.0):
		"""
		Create poster image from video
		
		Args:
			timestamp: Time in seconds to extract frame from
		
		Returns:
			Path to poster image
		"""
		try:
			temp_poster = os.path.join(self.output_dir, "poster_temp.jpg")
			output_path = os.path.join(self.output_dir, "poster.webp")
			
			# Extract frame
			cmd = [
				'ffmpeg',
				'-ss', str(timestamp),
				'-i', self.source_path,
				'-vframes', '1',
				'-q:v', '2',
				'-y',
				temp_poster
			]
			
			subprocess.run(cmd, check=True, capture_output=True)
			
			# Convert to WebP and optimize
			with Image.open(temp_poster) as img:
				# Resize to reasonable poster size
				max_size = 800
				width, height = img.size
				if width > height:
					new_width = min(width, max_size)
					new_height = int(height * (new_width / width))
				else:
					new_height = min(height, max_size)
					new_width = int(width * (new_height / height))
				
				img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
				
				# Convert to RGB if needed
				if img.mode != 'RGB':
					img = img.convert('RGB')
				
				img.save(output_path, "WEBP", quality=80, method=6)
			
			# Clean up temp file
			if os.path.exists(temp_poster):
				os.remove(temp_poster)
			
			return output_path
		
		except subprocess.CalledProcessError as e:
			safe_log_error("Video Poster Error - FFmpeg", e.stderr.decode() if e.stderr else str(e))
			return None
		except Exception as e:
			safe_log_error("Video Poster Error", str(e))
			return None


def process_image(source_path, output_dir, variants_config):
	"""
	Standalone function to process image
	
	Args:
		source_path: Path to source image
		output_dir: Directory to save variants
		variants_config: List of variant configs with name, size, quality
	
	Returns:
		List of created variant paths
	"""
	processor = ImageProcessor(source_path, output_dir)
	
	variant_paths = []
	for config in variants_config:
		variant_path = processor.create_variant(
			variant_name=config["name"],
			max_size=config["size"],
			quality=config.get("quality", 75)
		)
		if variant_path:
			variant_paths.append(variant_path)
	
	return variant_paths


def process_video(source_path, output_dir):
	"""
	Standalone function to process video
	
	Args:
		source_path: Path to source video
		output_dir: Directory to save outputs
	
	Returns:
		dict with video_path, poster_path, metadata
	"""
	processor = VideoProcessor(source_path, output_dir)
	
	metadata = processor.get_metadata()
	video_path = processor.create_720p_variant()
	poster_path = processor.create_poster()
	
	return {
		"video_path": video_path,
		"poster_path": poster_path,
		"metadata": metadata
	}
