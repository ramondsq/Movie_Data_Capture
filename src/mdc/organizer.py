"""File organization: folder creation, file move/link, subtitle handling."""

from __future__ import annotations

import logging
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

from mdc.models import MovieData

logger = logging.getLogger(__name__)


def render_naming_rule(rule: str, data: MovieData) -> str:
    """Render a naming rule like 'actor+"/"+number' without eval().

    Supports the config format: field names and quoted string literals joined with +.
    """
    field_map = {
        "number": data.number,
        "title": data.title,
        "actor": data.actor,
        "studio": data.studio,
        "year": data.year,
        "series": data.series,
        "director": data.director,
        "label": data.label,
        "release": data.release,
        "runtime": data.runtime,
    }
    parts = []
    for token in rule.split("+"):
        token = token.strip()
        if (token.startswith("'") and token.endswith("'")) or (
            token.startswith('"') and token.endswith('"')
        ):
            parts.append(token[1:-1])
        elif token in field_map:
            parts.append(field_map[token] or "")
        else:
            parts.append(token)
    return "".join(parts)


def create_output_folder(
    movie: MovieData,
    success_folder: str,
    location_rule: str,
    max_title_len: int = 50,
    escape_literals: str = "",
) -> str:
    """Create the output folder for a movie based on the naming rule."""
    location = render_naming_rule(location_rule, movie)

    # Truncate long actor lists
    if "actor" in location_rule and len(movie.actor) > 100:
        short_movie = MovieData(**{**movie.__dict__, "actor": "多人作品"})
        location = render_naming_rule(location_rule, short_movie)

    # Truncate long titles
    if "title" in location_rule and len(movie.title) > max_title_len:
        short_title = movie.title[:max_title_len]
        location = location.replace(movie.title, short_title)

    # Ensure relative path (avoid absolute when actor is empty)
    path = os.path.join(success_folder, f"./{location.strip()}")
    if not os.path.exists(path):
        path = _escape_path(path, escape_literals)
        try:
            os.makedirs(path, exist_ok=True)
        except Exception:
            # Fallback: use number-only path
            path = os.path.join(success_folder, movie.number)
            path = _escape_path(path, escape_literals)
            try:
                os.makedirs(path, exist_ok=True)
            except Exception:
                logger.error("Cannot create folder: %s", path)
                raise

    return os.path.normpath(path)


def move_movie_file(
    filepath: str,
    dest_dir: str,
    number: str,
    suffix_parts: str,
    link_mode: int = 0,
) -> None:
    """Move or link a movie file to the destination directory."""
    filepath_obj = Path(filepath)
    ext = filepath_obj.suffix
    targetpath = os.path.join(dest_dir, f"{number}{suffix_parts}{ext}")

    if os.path.exists(targetpath):
        raise FileExistsError(
            f"File exists at destination, will not overwrite: {targetpath}"
        )

    if link_mode not in (1, 2):
        shutil.move(filepath, targetpath)
        logger.info("Move =>           %s", dest_dir)
    elif link_mode == 2:
        try:
            os.link(filepath, targetpath, follow_symlinks=False)
            logger.info("Hard link =>      %s", dest_dir)
        except Exception:
            _create_symlink(filepath, targetpath, dest_dir)
    elif link_mode == 1:
        _create_symlink(filepath, targetpath, dest_dir)


def _create_symlink(filepath: str, targetpath: str, dest_dir: str) -> None:
    try:
        relpath = os.path.relpath(filepath, dest_dir)
        os.symlink(relpath, targetpath)
    except Exception:
        os.symlink(str(Path(filepath).resolve()), targetpath)
    logger.info("Soft link =>      %s", dest_dir)


def move_to_failed(filepath: str, failed_folder: str, main_mode: int, link_mode: int, failed_move: bool) -> None:
    """Record or move a file to the failed folder."""
    if main_mode == 3 or link_mode:
        ftxt = os.path.abspath(os.path.join(failed_folder, "failed_list.txt"))
        logger.info("Add to Failed List file, see '%s'", ftxt)
        with open(ftxt, "a", encoding="utf-8") as f:
            f.write(f"{filepath}\n")
    elif failed_move and not link_mode:
        failed_name = os.path.join(failed_folder, os.path.basename(filepath))
        mtxt = os.path.abspath(
            os.path.join(failed_folder, "where_was_i_before_being_moved.txt")
        )
        logger.info("Move to Failed folder, see '%s'", mtxt)
        with open(mtxt, "a", encoding="utf-8") as f:
            tmstr = datetime.now().strftime("%Y-%m-%d %H:%M")
            f.write(f"{tmstr} FROM[{filepath}]TO[{failed_name}]\n")
        if os.path.exists(failed_name):
            logger.warning("File already exists in failed folder")
            return
        try:
            shutil.move(filepath, failed_name)
        except Exception:
            logger.error("Moving to failed folder unsuccessful!")


def move_subtitles(
    filepath: str,
    dest_dir: str,
    number: str,
    suffix_parts: str,
    sub_rule: set[str],
    link_mode: int = 0,
    multi_part: bool = False,
    part: str = "",
) -> bool:
    """Find and move/copy subtitle files alongside the movie."""
    filepath_obj = Path(filepath)
    for subfile in filepath_obj.parent.glob("**/*"):
        if not subfile.is_file() or subfile.suffix.lower() not in sub_rule:
            continue
        if multi_part and part.lower() not in subfile.name.lower():
            continue
        if filepath_obj.stem.split(".")[0].lower() != subfile.stem.split(".")[0].lower():
            continue

        sub_target = Path(dest_dir) / f"{number}{suffix_parts}{''.join(subfile.suffixes)}"
        if link_mode not in (1, 2):
            shutil.move(str(subfile), str(sub_target))
            logger.info("Sub Moved!        %s", sub_target.name)
        else:
            shutil.copyfile(str(subfile), str(sub_target))
            logger.info("Sub Copied!       %s", sub_target.name)
        return True
    return False


def link_multi_part_images(
    dest_dir: str,
    number: str,
    part: str,
    suffix_parts: str,
    ext: str,
) -> None:
    """Create hard links for multi-part Jellyfin cover images."""
    if not all(v for v in (dest_dir, number, part, ext)):
        return
    covers = ("-fanart", "-poster", "-thumb")
    normal_prefix = f"{number}{suffix_parts}"
    multi_prefix = f"{number}{part}{suffix_parts}"
    path = Path(dest_dir)
    for cover in covers:
        normal = path / f"{normal_prefix}{cover}{ext}"
        multi = path / f"{multi_prefix}{cover}{ext}"
        if not normal.is_file():
            continue
        if multi.exists():
            if multi.stat().st_nlink > 1:
                continue
            if normal.stat().st_mtime <= multi.stat().st_mtime:
                continue
            multi.unlink(missing_ok=True)
        try:
            os.link(str(normal), str(multi), follow_symlinks=False)
        except Exception:
            shutil.copyfile(str(normal), str(multi))


def _escape_path(path: str, escape_literals: str) -> str:
    for literal in escape_literals:
        path = path.replace("\\" + literal, "")
    return path
