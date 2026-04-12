"""Cover image cropping and watermark overlay."""

from __future__ import annotations

import logging
import os
import shutil
from io import BytesIO
from pathlib import Path

from PIL import Image

from mdc.utils import file_not_exist_or_empty

logger = logging.getLogger(__name__)

# Watermark PNG filenames by mode index
_WATERMARK_FILES = {
    1: "SUB.png",
    2: "LEAK.png",
    3: "UNCENSORED.png",
    4: "HACK.png",
    5: "4K.png",
    6: "ISO.png",
}


def cut_image(
    imagecut: int,
    path: str,
    fanart_path: str,
    poster_path: str,
    skip_face_rec: bool = False,
    face_aspect_ratio: float = 2.0,
    always_imagecut: bool = False,
    download_only_missing: bool = False,
    face_locations_model: str = "hog",
) -> None:
    """Crop fanart to create poster image.

    imagecut modes:
        0 = copy fanart as poster
        1 = crop (face detection if available, else right-side crop)
        3 = poster already downloaded separately (skip)
        4 = always use face detection crop
    """
    fullpath_fanart = os.path.join(path, fanart_path)
    fullpath_poster = os.path.join(path, poster_path)

    if always_imagecut:
        imagecut = 1
    elif download_only_missing and not file_not_exist_or_empty(fullpath_poster):
        return

    if imagecut == 3:
        return

    if imagecut in (1, 4):
        try:
            img = Image.open(fullpath_fanart)
            width, height = img.size
            if width / height > 2 / 3:
                if imagecut == 4 or not skip_face_rec:
                    crop_box = _face_crop_width(
                        fullpath_fanart, width, height,
                        face_aspect_ratio, face_locations_model,
                    )
                else:
                    # Default right-side crop for censored content
                    crop_box = (
                        width - int(height / 3) * face_aspect_ratio,
                        0, width, height,
                    )
                img2 = img.crop(crop_box)
            elif width / height < 2 / 3:
                crop_box = _face_crop_height(
                    fullpath_fanart, width, height, face_locations_model,
                )
                img2 = img.crop(crop_box)
            else:
                img2 = img
            img2.save(fullpath_poster)
            logger.info("Image Cutted!     %s", Path(fullpath_poster).name)
        except Exception as e:
            logger.error("Cover cut failed: %s", e)
    elif imagecut == 0:
        shutil.copyfile(fullpath_fanart, fullpath_poster)
        logger.info("Image Copied!     %s", Path(fullpath_poster).name)


def add_watermark(
    poster_path: str,
    thumb_path: str,
    cn_sub: bool = False,
    leak: bool = False,
    uncensored: bool = False,
    hack: bool = False,
    _4k: bool = False,
    iso: bool = False,
    watermark_start_pos: int = 0,
) -> None:
    """Add watermark badges to poster and thumb images."""
    marks = []
    if cn_sub:
        marks.append((1, "字幕"))
    if leak:
        marks.append((2, "无码流出"))
    if uncensored:
        marks.append((3, "无码"))
    if hack:
        marks.append((4, "破解"))
    if _4k:
        marks.append((5, "4k"))
    if iso:
        marks.append((6, "iso"))

    if not marks:
        return

    for pic_path in (thumb_path, poster_path):
        if not os.path.isfile(pic_path):
            continue
        _apply_marks(pic_path, marks, watermark_start_pos)

    label = ",".join(m[1] for m in marks)
    logger.info("Add Mark:         %s", label)


def _apply_marks(pic_path: str, marks: list[tuple[int, str]], start_pos: int) -> None:
    """Apply watermark badges to a single image file."""
    size = 9
    img = Image.open(pic_path)
    count = start_pos
    for mode, _label in marks:
        _paste_watermark(pic_path, img, size, count, mode)
        count = (count + 1) % 4
    img.close()


def _paste_watermark(
    pic_path: str, img: Image.Image, size: int, position: int, mode: int
) -> None:
    """Paste a single watermark badge onto an image."""
    png_name = _WATERMARK_FILES.get(mode)
    if not png_name:
        return

    pngpath = f"Img/{png_name}"

    # Look for watermark image in package directory, then download
    mark_img = None
    pkg_dir = Path(__file__).resolve().parent.parent.parent
    local_path = pkg_dir / pngpath
    if local_path.is_file():
        mark_img = Image.open(str(local_path))
    else:
        try:
            from mdc.scrapers import httprequest

            data = httprequest.get(
                "https://raw.githubusercontent.com/yoshiko2/AV_Data_Capture/master/"
                + pngpath,
                return_type="content",
            )
            if data:
                mark_img = Image.open(BytesIO(data))
        except Exception:
            logger.debug("Failed to download watermark image: %s", png_name)
            return

    if mark_img is None:
        return

    scroll_high = int(img.height / size)
    scroll_wide = int(scroll_high * mark_img.width / mark_img.height)
    mark_img = mark_img.resize((scroll_wide, scroll_high), Image.LANCZOS)
    r, g, b, a = mark_img.split()

    # Four corner positions: top-left, top-right, bottom-right, bottom-left
    positions = [
        (0, 0),
        (img.width - scroll_wide, 0),
        (img.width - scroll_wide, img.height - scroll_high),
        (0, img.height - scroll_high),
    ]
    img.paste(mark_img, positions[position], mask=a)
    img.save(pic_path, quality=95)


def _face_crop_width(
    filename: str,
    width: int,
    height: int,
    aspect_ratio: float = 2.0,
    model: str = "hog",
) -> tuple[int, int, int, int]:
    """Crop width based on face detection, fallback to right-side crop."""
    crop_half = int(height / 3)
    try:
        center, _top = _detect_face_center(filename, model)
        if center:
            left = center - crop_half
            right = center + crop_half
            if left < 0:
                left = 0
                right = int(crop_half * aspect_ratio)
            elif right > width:
                left = width - int(crop_half * aspect_ratio)
                right = width
            return (left, 0, right, height)
    except Exception:
        logger.debug("Face not found: %s", filename)
    # Default: right-side crop
    return (width - int(crop_half * aspect_ratio), 0, width, height)


def _face_crop_height(
    filename: str,
    width: int,
    height: int,
    model: str = "hog",
) -> tuple[int, int, int, int]:
    """Crop height based on face detection, fallback to top crop."""
    crop_height = int(width * 3 / 2)
    try:
        _center, top = _detect_face_center(filename, model)
        if top:
            crop_top = top
            crop_bottom = crop_height + top
            if crop_bottom > height:
                crop_top = 0
                crop_bottom = crop_height
            return (0, crop_top, width, crop_bottom)
    except Exception:
        logger.debug("Face not found: %s", filename)
    return (0, 0, width, crop_height)


def _detect_face_center(filename: str, model: str = "hog") -> tuple[int, int]:
    """Detect face center using face_recognition library (optional dependency)."""
    try:
        import face_recognition

        image = face_recognition.load_image_file(filename)
        locations = face_recognition.face_locations(image, model=model)
        if locations:
            top, right, bottom, left = locations[0]
            center_x = (left + right) // 2
            return center_x, top
    except ImportError:
        logger.debug("face_recognition not installed, using default crop")
    except Exception as e:
        logger.debug("Face detection error: %s", e)
    return 0, 0
