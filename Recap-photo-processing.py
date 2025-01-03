import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw
import piexif
from iptcinfo3 import IPTCInfo

# Constants
STYLING = {
    "GREEN": "\033[92m",
    "RED": "\033[91m",
    "BLUE": "\033[94m",
    "BOLD": "\033[1m",
    "RESET": "\033[0m",
}

OUTPUT_SETTINGS = {
    "DEFAULT_OUTPUT_FORMAT": "JPEG",
    "JPEG_QUALITY": 80,
}

# Configure Logger
class ColorFormatter(logging.Formatter):
    def format(self, record):
        message = super().format(record)
        color = {
            logging.INFO: STYLING["GREEN"],
            logging.ERROR: STYLING["RED"],
        }.get(record.levelno, "")
        if "Finished processing" in record.msg:
            color = STYLING["BLUE"] + STYLING["BOLD"]
        return f"{color}{message}{STYLING['RESET']}"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
handler = logger.handlers[0]
handler.setFormatter(ColorFormatter('%(asctime)s - %(levelname)s - %(message)s'))

# Paths
PHOTO_FOLDER = Path('Photos/post/')
BEREAL_FOLDER = Path('Photos/bereal')
OUTPUT_FOLDER = Path('Photos/post/__processed')
COMBINED_FOLDER = Path('Photos/post/__combined')
OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)
COMBINED_FOLDER.mkdir(parents=True, exist_ok=True)

# Utilities
def get_unique_filename(path):
    """Ensure the filename is unique by appending a counter if needed."""
    counter = 1
    unique_path = path
    while unique_path.exists():
        unique_path = path.with_name(f"{path.stem}_{counter}{path.suffix}")
        counter += 1
    return unique_path

def count_files(folder, ext='*.webp'):
    """Count files with the given extension in a folder."""
    return len(list(Path(folder).glob(ext)))

def remove_backup_files(directory):
    """Remove temporary backup files."""
    for backup_file in Path(directory).glob('*~'):
        try:
            backup_file.unlink()
            logger.info(f"Removed backup file: {backup_file}")
        except Exception as e:
            logger.error(f"Error removing {backup_file}: {e}")

# Image Operations
def convert_webp_to_jpg(image_path):
    """Convert WEBP image to JPEG."""
    jpg_path = image_path.with_suffix('.jpg')
    try:
        with Image.open(image_path) as img:
            img.convert('RGB').save(jpg_path, OUTPUT_SETTINGS["DEFAULT_OUTPUT_FORMAT"], quality=OUTPUT_SETTINGS["JPEG_QUALITY"])
        logger.info(f"Converted {image_path} to JPEG.")
        return jpg_path
    except Exception as e:
        logger.error(f"Error converting {image_path} to JPEG: {e}")
        return None

def combine_images(primary_path, secondary_path, output_path):
    """Combine primary and secondary images with overlay and rounded corners."""
    primary_img = Image.open(primary_path)
    secondary_img = Image.open(secondary_path).resize(
        (primary_img.width // 3, primary_img.height // 3), Image.LANCZOS
    )

    mask = Image.new("L", secondary_img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, *secondary_img.size], radius=30, fill=255)

    secondary_img.putalpha(mask)

    primary_img.paste(secondary_img, (50, 50), secondary_img)
    primary_img.save(output_path, OUTPUT_SETTINGS["DEFAULT_OUTPUT_FORMAT"])

# Metadata Management
def update_metadata(image_path, datetime_taken, caption=None, location=None):
    """Update EXIF and IPTC metadata."""
    try:
        exif = piexif.load(image_path.as_posix())
        exif["Exif"][piexif.ExifIFD.DateTimeOriginal] = datetime_taken.strftime("%Y:%m:%d %H:%M:%S")

        if location:
            exif["GPS"] = {
                piexif.GPSIFD.GPSLatitude: location["latitude"],
                piexif.GPSIFD.GPSLongitude: location["longitude"],
            }

        piexif.insert(piexif.dump(exif), image_path.as_posix())
    except Exception as e:
        logger.error(f"Failed to update EXIF data for {image_path}: {e}")

    try:
        iptc = IPTCInfo(image_path.as_posix(), force=True)
        if caption:
            iptc["caption/abstract"] = caption
        iptc.save()
    except Exception as e:
        logger.error(f"Failed to update IPTC data for {image_path}: {e}")

# Main Processing
def process_files():
    """Main logic to process files from JSON."""
    try:
        with open("posts.json", encoding="utf8") as f:
            data = json.load(f)
    except FileNotFoundError:
        logger.error("JSON file not found. Exiting.")
        return

    for entry in data:
        try:
            primary = PHOTO_FOLDER / Path(entry["primary"]["path"]).name
            secondary = PHOTO_FOLDER / Path(entry["secondary"]["path"]).name
            taken_at = datetime.strptime(entry["takenAt"], "%Y-%m-%dT%H:%M:%S.%fZ")

            # Convert, rename, and save primary/secondary
            for image_path in [primary, secondary]:
                if not image_path.exists():
                    continue
                new_path = get_unique_filename(OUTPUT_FOLDER / image_path.name)
                if image_path.suffix == ".webp":
                    converted = convert_webp_to_jpg(image_path)
                    if converted:
                        new_path = get_unique_filename(new_path.with_suffix(".jpg"))
                        shutil.move(converted, new_path)
                else:
                    shutil.copy2(image_path, new_path)
                update_metadata(new_path, taken_at, entry.get("caption"))

            # Combine images
            combined_path = get_unique_filename(COMBINED_FOLDER / f"{taken_at.strftime('%Y%m%d_%H%M%S')}_combined.jpg")
            combine_images(primary, secondary, combined_path)
            update_metadata(combined_path, taken_at, entry.get("caption"))

        except Exception as e:
            logger.error(f"Error processing entry {entry}: {e}")

    remove_backup_files(OUTPUT_FOLDER)
    remove_backup_files(COMBINED_FOLDER)

# Run Script
if __name__ == "__main__":
    process_files()
