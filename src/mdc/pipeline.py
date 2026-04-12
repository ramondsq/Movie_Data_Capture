"""Main processing pipeline: scrape metadata, download assets, organize files."""

from __future__ import annotations

import json
import logging
import re
import secrets
from pathlib import Path

from lxml import etree

from mdc import config
from mdc.downloader import (
    actor_photo_download,
    extrafanart_download,
    image_download,
    image_ext,
    small_cover_download,
    trailer_download,
)
from mdc.imaging import add_watermark, cut_image
from mdc.models import MovieData
from mdc.nfo import write_nfo
from mdc.number import is_uncensored
from mdc.organizer import (
    create_output_folder,
    link_multi_part_images,
    move_movie_file,
    move_subtitles,
    move_to_failed,
    render_naming_rule,
)
from mdc.scrapers.registry import search as scraper_search
from mdc.utils import (
    cn_space,
    delete_all_elements_in_list,
    delete_all_elements_in_str,
    file_modification_days,
    load_cookies,
    special_characters_replacement,
)

logger = logging.getLogger(__name__)


def process_movie(
    movie_path: str,
    number: str,
    open_cc=None,
    specified_source: str = "",
    specified_url: str = "",
) -> None:
    """Main pipeline: scrape metadata, download images, write NFO, move files."""
    conf = config.getInstance()

    # --- Scrape metadata ---
    movie = fetch_metadata(number, open_cc, specified_source, specified_url)
    if not movie:
        _move_failed(movie_path)
        return

    # Use normalized number from scraper
    if movie.number != number:
        number = movie.number

    # --- Detect file properties from path ---
    props = _detect_file_properties(movie_path, number, movie)

    suffix_parts = props["suffix_parts"]
    multi_part = props["multi_part"]
    part = props["part"]
    cn_sub = props["cn_sub"]
    leak = props["leak"]
    uncensored = props["uncensored"]
    hack = props["hack"]
    _4k = props["_4k"]
    iso = props["iso"]

    # Clean tags
    tag = list(movie.tag)
    for remove_tag in ("4K", "无码破解"):
        if remove_tag in tag:
            tag.remove(remove_tag)
    movie.tag = tag

    if conf.debug():
        debug_print(movie)

    # --- Image paths ---
    cover = movie.cover
    ext = image_ext(cover)
    fanart_name = f"fanart{ext}"
    poster_name = f"poster{ext}"
    thumb_name = f"thumb{ext}"
    if conf.image_naming_with_number():
        fanart_name = f"{number}{suffix_parts}-fanart{ext}"
        poster_name = f"{number}{suffix_parts}-poster{ext}"
        thumb_name = f"{number}{suffix_parts}-thumb{ext}"

    headers = movie.headers or None
    download_only_missing = conf.download_only_missing_images()
    retry = conf.proxy().retry

    main_mode = conf.main_mode()

    if main_mode == 1:
        _process_mode1(
            conf, movie, movie_path, number, part, multi_part, suffix_parts,
            cn_sub, leak, uncensored, hack, _4k, iso,
            cover, ext, fanart_name, poster_name, thumb_name,
            headers, download_only_missing, retry, open_cc,
        )
    elif main_mode == 2:
        _process_mode2(
            conf, movie, movie_path, number, part, multi_part, suffix_parts,
        )
    elif main_mode == 3:
        _process_mode3(
            conf, movie, movie_path, number, part, multi_part, suffix_parts,
            cn_sub, leak, uncensored, hack, _4k, iso,
            cover, ext, fanart_name, poster_name, thumb_name,
            headers, download_only_missing, retry, open_cc,
        )


def _process_mode1(
    conf, movie, movie_path, number, part, multi_part, suffix_parts,
    cn_sub, leak, uncensored, hack, _4k, iso,
    cover, ext, fanart_name, poster_name, thumb_name,
    headers, download_only_missing, retry, open_cc,
):
    """Mode 1: Full scraping mode — create folder, download, move, write NFO."""
    dest_dir = create_output_folder(
        movie, conf.success_folder(), conf.location_rule(),
        conf.max_title_len(), conf.escape_literals(),
    )

    file_number = number
    if multi_part:
        number = number + part

    # Download small cover for imagecut==3
    if movie.imagecut == 3 and movie.cover_small:
        small_cover_download(
            movie.cover_small, poster_name, dest_dir,
            headers, download_only_missing,
        )

    # Download main cover
    if not image_download(
        cover, fanart_name, thumb_name, dest_dir,
        retry, headers, download_only_missing, conf.jellyfin(),
    ):
        _move_failed(movie_path)
        return

    # Download extras (only for first part)
    if not multi_part or part.lower() == "-cd1":
        _download_extras(conf, movie, dest_dir, number, movie_path, headers, retry)

    # Crop cover to poster
    cut_image(
        movie.imagecut, dest_dir, thumb_name, poster_name,
        skip_face_rec=bool(conf.face_uncensored_only() and not uncensored),
        face_aspect_ratio=conf.face_aspect_ratio(),
        always_imagecut=conf.face_aways_imagecut(),
        download_only_missing=download_only_missing,
    )

    # Jellyfin multi-part cover linking
    if multi_part and conf.jellyfin_multi_part_fanart():
        link_multi_part_images(
            dest_dir, file_number, part, suffix_parts, ext,
        )

    # Move movie file
    try:
        move_movie_file(
            movie_path, dest_dir, number, suffix_parts, conf.link_mode(),
        )
    except FileExistsError as e:
        logger.error("FileExistsError: %s", e)
        _move_failed(movie_path)
        return

    # Move subtitles
    sub_moved = move_subtitles(
        movie_path, dest_dir, number, suffix_parts,
        conf.sub_rule(), conf.link_mode(), multi_part, part,
    )
    if sub_moved:
        cn_sub = True

    # Add watermarks
    if conf.is_watermark():
        add_watermark(
            os.path.join(dest_dir, poster_name),
            os.path.join(dest_dir, thumb_name),
            cn_sub, leak, uncensored, hack, _4k, iso,
            conf.watermark_type(),
        )

    # Write NFO (last step — NFO creation = success marker)
    _write_nfo_file(
        conf, movie, movie_path, dest_dir, number, part, suffix_parts,
        cn_sub, leak, uncensored, hack, _4k, iso,
        fanart_name, poster_name, thumb_name,
    )


def _process_mode2(
    conf, movie, movie_path, number, part, multi_part, suffix_parts,
):
    """Mode 2: Organize only — create folder and move files."""
    dest_dir = create_output_folder(
        movie, conf.success_folder(), conf.location_rule(),
        conf.max_title_len(), conf.escape_literals(),
    )
    if multi_part:
        number = number + part

    try:
        move_movie_file(
            movie_path, dest_dir, number, suffix_parts, conf.link_mode(),
        )
    except FileExistsError as e:
        logger.error("FileExistsError: %s", e)
        return

    move_subtitles(
        movie_path, dest_dir, number, suffix_parts,
        conf.sub_rule(), conf.link_mode(), multi_part, part,
    )


def _process_mode3(
    conf, movie, movie_path, number, part, multi_part, suffix_parts,
    cn_sub, leak, uncensored, hack, _4k, iso,
    cover, ext, fanart_name, poster_name, thumb_name,
    headers, download_only_missing, retry, open_cc,
):
    """Mode 3: Scrape in-place — download metadata/images but don't move files."""
    dest_dir = str(Path(movie_path).parent)

    file_number = number
    if multi_part:
        number = number + part

    # Download small cover for imagecut==3
    if movie.imagecut == 3 and movie.cover_small:
        small_cover_download(
            movie.cover_small, poster_name, dest_dir,
            headers, download_only_missing,
        )

    # Download main cover
    if not image_download(
        cover, fanart_name, thumb_name, dest_dir,
        retry, headers, download_only_missing, conf.jellyfin(),
    ):
        _move_failed(movie_path)
        return

    # Download extras (only for first part)
    if not multi_part or part.lower() == "-cd1":
        _download_extras(conf, movie, dest_dir, number, movie_path, headers, retry)

    # Crop cover
    cut_image(
        movie.imagecut, dest_dir, fanart_name, poster_name,
        skip_face_rec=bool(conf.face_uncensored_only() and not uncensored),
        face_aspect_ratio=conf.face_aspect_ratio(),
        always_imagecut=conf.face_aways_imagecut(),
        download_only_missing=download_only_missing,
    )

    # Watermarks
    if conf.is_watermark():
        add_watermark(
            os.path.join(dest_dir, poster_name),
            os.path.join(dest_dir, fanart_name),
            cn_sub, leak, uncensored, hack, _4k, iso,
            conf.watermark_type(),
        )

    # Jellyfin multi-part cover linking
    if multi_part and conf.jellyfin_multi_part_fanart():
        link_multi_part_images(
            dest_dir, file_number, part, suffix_parts, ext,
        )

    # Write NFO
    _write_nfo_file(
        conf, movie, movie_path, dest_dir, number, part, suffix_parts,
        cn_sub, leak, uncensored, hack, _4k, iso,
        fanart_name, poster_name, thumb_name,
    )


def process_movie_no_net(movie_path: str, number: str) -> None:
    """Mode 3 without network: re-crop covers and re-apply watermarks only."""
    conf = config.getInstance()
    props = _detect_file_properties(movie_path, number, None)
    suffix_parts = props["suffix_parts"]
    multi_part = props["multi_part"]
    part = props["part"]
    cn_sub = props["cn_sub"]
    leak = props["leak"]
    uncensored = props["uncensored"]
    hack = props["hack"]
    _4k = props["_4k"]
    iso = props["iso"]

    path = str(Path(movie_path).parent)
    prestr = f"{number}{suffix_parts}"
    full_nfo = Path(path) / f"{prestr}{part}.nfo"

    if not full_nfo.is_file():
        return

    # Check uncensored tag from NFO
    nfo_text = full_nfo.read_text(encoding="utf-8")
    if "<tag>无码</tag>" in nfo_text:
        uncensored = True

    try:
        nfo_xml = etree.parse(str(full_nfo))
        nfo_fanart_path = nfo_xml.xpath("//fanart/text()")[0]
        ext = Path(nfo_fanart_path).suffix
    except Exception:
        return

    fanart_name = f"fanart{ext}"
    poster_name = f"poster{ext}"
    thumb_name = f"thumb{ext}"
    if conf.image_naming_with_number():
        fanart_name = f"{prestr}-fanart{ext}"
        poster_name = f"{prestr}-poster{ext}"
        thumb_name = f"{prestr}-thumb{ext}"

    full_fanart = os.path.join(path, fanart_name)
    full_thumb = os.path.join(path, thumb_name)
    if not all(os.path.isfile(f) for f in (full_fanart, full_thumb)):
        return

    imagecut = 1
    cut_image(
        imagecut, path, fanart_name, poster_name,
        skip_face_rec=bool(conf.face_uncensored_only() and not uncensored),
        face_aspect_ratio=conf.face_aspect_ratio(),
        always_imagecut=conf.face_aways_imagecut(),
    )

    if conf.is_watermark():
        full_poster = os.path.join(path, poster_name)
        add_watermark(
            full_poster, full_thumb,
            cn_sub, leak, uncensored, hack, _4k, iso,
            conf.watermark_type(),
        )

    if multi_part and conf.jellyfin_multi_part_fanart():
        link_multi_part_images(path, number, part, suffix_parts, ext)


# ========================================================================
# Internal helpers
# ========================================================================

import os


def fetch_metadata(
    number: str,
    open_cc=None,
    specified_source: str = "",
    specified_url: str = "",
) -> MovieData | None:
    """Fetch and post-process movie metadata from scrapers."""
    conf = config.getInstance()

    # Proxy setup
    proxy_conf = conf.proxy()
    proxies = proxy_conf.proxies() if proxy_conf.enable else None
    ca_cert = conf.cacert_file() or None

    # Javdb cookie handling
    javdb_sites = conf.javdb_sites().split(",")
    javdb_sites = [f"javdb{s}" for s in javdb_sites] + ["javdb"]
    javdb_site = ""
    javdb_cookies = None
    for cj in javdb_sites:
        cookie_json = cj + ".json"
        cookies_dict, cookies_filepath = load_cookies(cookie_json)
        if isinstance(cookies_dict, dict) and isinstance(cookies_filepath, str):
            cdays = file_modification_days(cookies_filepath)
            if cdays < 7:
                javdb_site = cj
                javdb_cookies = cookies_dict
                break
            elif cdays != 9999:
                logger.info(
                    "Cookies %s updated %d days ago, skipping", cookies_filepath, cdays
                )
    if not javdb_site:
        javdb_site = secrets.choice(javdb_sites)

    # Scrape
    movie = scraper_search(
        number,
        conf.sources(),
        proxies=proxies,
        verify=ca_cert,
        dbsite=javdb_site,
        dbcookies=javdb_cookies,
        morestoryline=conf.is_storyline(),
        specifiedSource=specified_source or None,
        specifiedUrl=specified_url or None,
        debug=conf.debug(),
    )

    if not movie:
        logger.warning("Movie number not found: %s", number)
        return None

    # Strict number check
    if movie.number.upper() != number.upper() and not movie.allow_number_change:
        logger.warning(
            "Movie number changed: [%s] -> [%s]", number, movie.number
        )
        return None

    if not movie.title:
        logger.warning("Movie title empty for %s", number)
        return None

    # --- Post-processing ---
    _post_process(movie, conf, open_cc)

    return movie


def _post_process(movie: MovieData, conf, open_cc) -> None:
    """Apply character replacement, translation, CC conversion, naming rules."""
    # Parse actor_list from actor string if needed
    if movie.actor and not movie.actor_list:
        actor_list = [a.strip() for a in movie.actor.strip("[ ]").replace("'", "").split(",")]
        movie.actor_list = actor_list

    # Remove XXXX/xxx from tags
    movie.tag = [t for t in movie.tag if t not in ("XXXX", "xxx", "")]

    # Format actor string
    if movie.source == "pissplay":
        movie.actor = ", ".join(movie.actor_list)
    else:
        movie.actor = ",".join(a.replace(" ", "") for a in movie.actor_list)

    # Replace filesystem-unsafe characters
    movie.actor = special_characters_replacement(movie.actor)
    movie.actor_list = [special_characters_replacement(a) for a in movie.actor_list]
    movie.title = special_characters_replacement(movie.title)
    movie.label = special_characters_replacement(movie.label)
    movie.outline = special_characters_replacement(movie.outline)
    movie.series = special_characters_replacement(movie.series)
    movie.studio = special_characters_replacement(movie.studio)
    movie.director = special_characters_replacement(movie.director)
    movie.tag = [special_characters_replacement(t) for t in movie.tag]
    movie.release = movie.release.replace("/", "-")

    # Clean cover_small
    if movie.cover_small:
        parts = movie.cover_small.split(",")
        if parts:
            movie.cover_small = parts[0].strip("\"'")

    # Uppercase number
    if conf.number_uppercase():
        movie.number = movie.number.upper()

    # Fanza number reformatting
    if movie.source == "fanza":
        movie.number = re.sub(r"(?<=\D)00(?=\d)", "-", movie.number)
        movie.number = re.sub(r"^[0-9]+", "", movie.number)

    # Save original title before translation
    movie.original_title = movie.title

    # Translation
    if conf.is_translate():
        _apply_translation(movie, conf)

    # CC conversion
    if open_cc:
        _apply_cc_conversion(movie, conf, open_cc)

    # Build naming rules
    naming_rule = render_naming_rule(conf.naming_rule(), movie)
    original_movie = MovieData(**{**movie.__dict__, "title": movie.original_title})
    original_naming_rule = render_naming_rule(conf.naming_rule(), original_movie)
    movie.naming_rule = naming_rule
    movie.original_naming_rule = original_naming_rule

    # Javbus headers for image downloads
    if movie.source == "javbus":
        movie.headers = {
            "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Referer": f"https://www.javbus.com/{movie.number}",
        }


def _apply_translation(movie: MovieData, conf) -> None:
    """Apply translation to configured fields."""
    from mdc.translate import translate

    translate_values = conf.translate_values().split(",")
    for field_name in translate_values:
        value = getattr(movie, field_name, "")
        if not value:
            continue

        # Try c_number.json lookup for title
        if field_name == "title":
            try:
                title_path = Path.home() / ".local" / "share" / "mdc" / "c_number.json"
                if title_path.is_file():
                    title_dict = json.loads(title_path.read_text(encoding="utf-8"))
                    if movie.number in title_dict:
                        setattr(movie, field_name, title_dict[movie.number])
                        continue
            except Exception:
                pass

        engine = conf.get_translate_engine()
        if engine == "azure":
            continue  # Azure translation disabled in original code

        if isinstance(value, str) and value:
            translated = translate(special_characters_replacement(value))
            if translated:
                setattr(movie, field_name, translated)
        elif isinstance(value, list):
            cleaned = [special_characters_replacement(v) for v in value]
            joined = ",".join(cleaned)
            translated = translate(joined)
            if translated:
                setattr(movie, field_name, translated.split(","))


def _apply_cc_conversion(movie: MovieData, conf, open_cc) -> None:
    """Apply OpenCC traditional/simplified Chinese conversion."""
    ccm = conf.cc_convert_mode()
    cc_vars = conf.cc_convert_vars().split(",")

    # Load mapping tables
    try:
        actor_mapping = etree.parse(
            str(Path.home() / ".local" / "share" / "mdc" / "mapping_actor.xml")
        )
        info_mapping = etree.parse(
            str(Path.home() / ".local" / "share" / "mdc" / "mapping_info.xml")
        )
    except Exception:
        actor_mapping = etree.fromstring("<html></html>", etree.HTMLParser())
        info_mapping = etree.fromstring("<html></html>", etree.HTMLParser())

    lang_map = {1: "zh_cn", 2: "zh_tw", 3: "jp"}
    language = lang_map.get(ccm, "zh_cn")

    def convert_single(mapping, lang, value):
        results = mapping.xpath(
            'a[contains(@keyword, $name)]/@' + lang, name=f",{value},"
        )
        if results:
            return results[0]
        raise IndexError("not found")

    def convert_list_values(mapping, lang, values):
        result = []
        for v in values:
            matches = mapping.xpath(
                'a[contains(@keyword, $name)]/@' + lang, name=f",{v},"
            )
            result.append(matches[0] if matches else v)
        return result

    for cc_field in cc_vars:
        value = getattr(movie, cc_field, "")
        if not value or (isinstance(value, (list, str)) and len(value) == 0):
            continue

        if cc_field == "actor":
            try:
                movie.actor_list = convert_list_values(
                    actor_mapping, language, movie.actor_list
                )
                movie.actor = convert_single(actor_mapping, language, movie.actor)
            except Exception:
                movie.actor_list = [open_cc.convert(a) for a in movie.actor_list]
                movie.actor = open_cc.convert(movie.actor)
        elif cc_field == "tag":
            try:
                movie.tag = convert_list_values(info_mapping, language, movie.tag)
                movie.tag = delete_all_elements_in_list("删除", movie.tag)
            except Exception:
                movie.tag = [open_cc.convert(t) for t in movie.tag]
        else:
            try:
                val = convert_single(info_mapping, language, getattr(movie, cc_field))
                val = delete_all_elements_in_str("删除", val)
                setattr(movie, cc_field, val)
            except IndexError:
                setattr(movie, cc_field, open_cc.convert(getattr(movie, cc_field)))
            except Exception:
                pass


def _detect_file_properties(
    movie_path: str, number: str, movie: MovieData | None
) -> dict:
    """Detect multi-part, subtitle, leak, hack, 4k, iso from filename."""
    multi_part = False
    part = ""
    c_word = ""
    cn_sub = False
    leak = False
    leak_word = ""
    hack = False
    hack_word = ""
    _4k = False
    iso = False

    if re.search(r"[-_]CD\d+", movie_path, re.IGNORECASE):
        multi_part = True
        part = re.findall(r"[-_]CD\d+", movie_path, re.IGNORECASE)[0].upper()

    if (
        re.search(r"[-_]C(\.\w+$|-\w+)|\d+ch(\.\w+$|-\w+)", movie_path, re.I)
        or "中文" in movie_path
        or "字幕" in movie_path
        or ".chs" in movie_path
        or ".cht" in movie_path
    ):
        cn_sub = True
        c_word = "-C"

    if re.search(r"[-_]UC(\.\w+$|-\w+)", movie_path, re.I):
        cn_sub = True
        hack_word = "-UC"
        hack = True

    if re.search(r"[-_]U(\.\w+$|-\w+)", movie_path, re.I):
        hack = True
        hack_word = "-U"

    # Determine uncensored status
    uncensored = is_uncensored(number)
    if movie and movie.uncensored:
        uncensored = True

    if "流出" in movie_path or "uncensored" in movie_path.lower():
        leak = True
        leak_word = "-无码流出"

    if "hack" in movie_path.upper() or "破解" in movie_path:
        hack = True
        hack_word = "-hack"

    if "4K" in movie_path.upper() or "4k" in movie_path:
        _4k = True

    if ".iso" in movie_path.lower():
        iso = True

    suffix_parts = f"{leak_word}{c_word}{hack_word}"

    return {
        "multi_part": multi_part,
        "part": part,
        "cn_sub": cn_sub,
        "c_word": c_word,
        "leak": leak,
        "leak_word": leak_word,
        "hack": hack,
        "hack_word": hack_word,
        "uncensored": uncensored,
        "_4k": _4k,
        "iso": iso,
        "suffix_parts": suffix_parts,
    }


def _download_extras(conf, movie, dest_dir, number, movie_path, headers, retry):
    """Download trailer, extrafanart, actor photos."""
    try:
        if conf.is_trailer() and movie.trailer:
            suffix = f"{number}-trailer.mp4"
            trailer_download(movie.trailer, dest_dir, suffix, retry)

        if conf.is_extrafanart() and movie.extrafanart:
            extrafanart_download(
                movie.extrafanart, dest_dir, number,
                conf.get_extrafanart(),
                conf.extrafanart_thread_pool_download(),
                headers,
                conf.download_only_missing_images(),
            )

        if conf.download_actor_photo_for_kodi() and movie.actor_photo:
            actor_photo_download(
                movie.actor_photo, dest_dir, number,
                conf.extrafanart_thread_pool_download() or 5,
                conf.download_only_missing_images(),
            )
    except Exception:
        pass


def _write_nfo_file(
    conf, movie, movie_path, dest_dir, number, part, suffix_parts,
    cn_sub, leak, uncensored, hack, _4k, iso,
    fanart_name, poster_name, thumb_name,
):
    """Write NFO metadata file."""
    if conf.main_mode() == 3:
        nfo_path = str(Path(movie_path).with_suffix(".nfo"))
    else:
        nfo_path = os.path.join(
            dest_dir, f"{number}{part}{suffix_parts}.nfo"
        )

    try:
        write_nfo(
            movie, nfo_path,
            movie.naming_rule, movie.original_naming_rule,
            jellyfin=conf.jellyfin(),
            actor_only_tag=conf.actor_only_tag(),
            show_trailer=conf.is_trailer(),
            show_director=conf.get_direct() is not False,
            cn_sub=cn_sub,
            leak=leak,
            uncensored=bool(uncensored),
            hack=hack,
            _4k=_4k,
            iso=iso,
            fanart_path=fanart_name,
            poster_path=poster_name,
            thumb_path=thumb_name,
        )
    except Exception as e:
        logger.error("NFO write failed: %s", e)
        _move_failed(movie_path)


def _move_failed(filepath: str) -> None:
    """Move file to failed folder using config settings."""
    conf = config.getInstance()
    move_to_failed(
        filepath,
        conf.failed_folder(),
        conf.main_mode(),
        conf.link_mode(),
        conf.failed_move(),
    )


def debug_print(movie: MovieData) -> None:
    """Print movie metadata in debug format."""
    logger.info("------- DEBUG INFO -------")
    fields = [
        "number", "title", "studio", "year", "runtime", "director",
        "actor", "release", "cover", "cover_small", "trailer", "website",
        "series", "label", "source", "imagecut", "uncensored",
        "userrating", "uservotes",
    ]
    for field in fields:
        val = getattr(movie, field, "")
        if field == "outline":
            logger.info("  - %-19s : %d characters", field, len(str(val)))
        else:
            logger.info("  - %-19s : %s", field, val)
    if movie.tag:
        logger.info("  - %-19s : %s", "tag", ", ".join(movie.tag))
    if movie.extrafanart:
        logger.info("  - %-19s : %d links", "extrafanart", len(movie.extrafanart))
    logger.info("------- DEBUG INFO -------")
