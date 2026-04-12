"""Image, trailer, and extrafanart download utilities."""

from __future__ import annotations

import logging
import os
import re
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from mdc.utils import file_not_exist_or_empty

logger = logging.getLogger(__name__)


def download_file(url: str, dest_path: str, headers: dict | None = None) -> bool:
    """Download a single file. Returns True on success."""
    from mdc.scrapers import httprequest

    dest = Path(dest_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = httprequest.get(url, return_type="content", extra_headers=headers)
        if not data:
            logger.warning("Download returned empty data: %s", url)
            return False
        dest.write_bytes(data)
        return True
    except Exception as e:
        logger.debug("Download failed %s: %s", url, e)
        return False


def download_with_retry(
    url: str, dest_path: str, retry: int = 3, headers: dict | None = None
) -> bool:
    """Download a file with retry on failure."""
    for i in range(retry):
        if download_file(url, dest_path, headers):
            if not file_not_exist_or_empty(dest_path):
                return True
        logger.debug("Download retry %d/%d: %s", i + 1, retry, url)
    return False


def parallel_download_files(
    url_path_pairs: list[tuple[str, str | Path]],
    parallel: int = 5,
    headers: dict | None = None,
) -> list[bool]:
    """Download multiple files in parallel. Returns list of success booleans."""
    if not url_path_pairs:
        return []

    def _download(pair):
        url, path = pair
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return download_file(url, str(path), headers)

    with ThreadPoolExecutor(max_workers=parallel) as pool:
        return list(pool.map(_download, url_path_pairs))


def image_download(
    cover_url: str,
    fanart_path: str,
    thumb_path: str,
    dest_dir: str,
    retry: int = 3,
    headers: dict | None = None,
    download_only_missing: bool = False,
    jellyfin: bool = False,
) -> bool:
    """Download the cover image as thumb; copy to fanart unless jellyfin mode."""
    full_thumb = os.path.join(dest_dir, thumb_path)
    if download_only_missing and not file_not_exist_or_empty(full_thumb):
        return True

    if not download_with_retry(cover_url, full_thumb, retry, headers):
        return False

    logger.info("Downloaded!       %s", Path(full_thumb).name)
    if not jellyfin:
        full_fanart = os.path.join(dest_dir, fanart_path)
        shutil.copyfile(full_thumb, full_fanart)
    return True


def small_cover_download(
    cover_small_url: str,
    poster_path: str,
    dest_dir: str,
    headers: dict | None = None,
    download_only_missing: bool = False,
) -> bool:
    """Download small cover as poster (for imagecut==3)."""
    full_path = os.path.join(dest_dir, poster_path)
    if download_only_missing and not file_not_exist_or_empty(full_path):
        return True
    if download_file(cover_small_url, full_path, headers):
        logger.info("Downloaded!       %s", Path(full_path).name)
        return True
    return False


def trailer_download(
    trailer_url: str,
    dest_dir: str,
    filename: str,
    retry: int = 3,
) -> bool:
    """Download a movie trailer."""
    dest = os.path.join(dest_dir, filename)
    if download_with_retry(trailer_url, dest, retry):
        logger.info("Trailer Downloaded! %s", filename)
        return True
    return False


def extrafanart_download(
    url_list: list[str],
    dest_dir: str,
    number: str,
    extrafanart_folder: str = "extrafanart",
    parallel: int = 0,
    headers: dict | None = None,
    download_only_missing: bool = False,
) -> None:
    """Download extrafanart images."""
    if not url_list:
        return
    fanart_dir = Path(dest_dir) / extrafanart_folder
    dn_list = []
    for i, url in enumerate(url_list, start=1):
        jpg_path = fanart_dir / f"extrafanart-{i}.jpg"
        if download_only_missing and not file_not_exist_or_empty(str(jpg_path)):
            continue
        dn_list.append((url, str(jpg_path)))
    if not dn_list:
        return

    if parallel > 0:
        workers = min(len(dn_list), parallel)
        results = parallel_download_files(dn_list, workers, headers)
        failed = sum(1 for r in results if not r)
        if failed:
            logger.warning(
                "Failed %d/%d extrafanart for [%s]", failed, len(results), number
            )
        else:
            logger.info("Downloaded %d extrafanarts.", len(results))
    else:
        for url, path in dn_list:
            if not download_with_retry(url, path, headers=headers):
                logger.warning("Extrafanart download failed: %s", url)
                return
            logger.info("Downloaded!       %s", Path(path).name)


def actor_photo_download(
    actors: dict[str, str],
    dest_dir: str,
    number: str,
    parallel: int = 5,
    download_only_missing: bool = False,
) -> None:
    """Download actor photos to .actors/ directory."""
    if not isinstance(actors, dict) or not actors or not dest_dir:
        return
    save_dir = Path(dest_dir)
    if not save_dir.is_dir():
        return

    actors_dir = save_dir / ".actors"
    dn_list = []
    for actor_name, url in actors.items():
        res = re.match(r"^http.*(\.\w+)$", url, re.A)
        if not res:
            continue
        ext = res.group(1)
        pic_path = actors_dir / f"{actor_name}{ext}"
        if download_only_missing and not file_not_exist_or_empty(str(pic_path)):
            continue
        dn_list.append((url, str(pic_path)))

    if not dn_list:
        return
    workers = min(len(dn_list), parallel)
    results = parallel_download_files(dn_list, workers)
    failed = sum(1 for r in results if not r)
    if failed:
        logger.warning(
            "Failed %d/%d actor photos for [%s]", failed, len(results), number
        )
    else:
        logger.info("Downloaded %d actor photos.", len(results))


def image_ext(url: str) -> str:
    """Extract image extension from URL, default to .jpg."""
    try:
        ext = os.path.splitext(url)[-1]
        if ext in {".jpg", ".jpeg", ".bmp", ".png", ".gif"}:
            return ext
    except Exception:
        pass
    return ".jpg"
