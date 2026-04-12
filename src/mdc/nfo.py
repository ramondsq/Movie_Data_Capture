"""NFO metadata file generation for Jellyfin/Kodi."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from lxml import etree

from mdc.models import MovieData

logger = logging.getLogger(__name__)


def write_nfo(
    movie: MovieData,
    nfo_path: str | Path,
    naming_rule: str,
    original_naming_rule: str,
    *,
    jellyfin: bool = False,
    actor_only_tag: bool = False,
    show_trailer: bool = False,
    show_director: bool = True,
    cn_sub: bool = False,
    leak: bool = False,
    uncensored: bool = False,
    hack: bool = False,
    _4k: bool = False,
    iso: bool = False,
    fanart_path: str = "",
    poster_path: str = "",
    thumb_path: str = "",
) -> None:
    """Generate an NFO XML file for a movie."""
    nfo_path = Path(nfo_path)
    nfo_path.parent.mkdir(parents=True, exist_ok=True)

    # Try to preserve ratings from existing NFO
    old_userrating = None
    old_rating = None
    old_criticrating = None
    old_ratings_xml = None
    if nfo_path.is_file():
        try:
            old_nfo = etree.parse(str(nfo_path))
            try:
                xur = old_nfo.xpath("//userrating/text()")[0]
                if isinstance(xur, str) and re.match(r"\d+\.?\d*", xur.strip()):
                    old_userrating = xur.strip()
            except Exception:
                pass
            try:
                old_rating = old_nfo.xpath("//rating/text()")[0].strip()
                old_criticrating = old_nfo.xpath("//criticrating/text()")[0].strip()
                old_ratings_xml = old_nfo.xpath("//ratings")[0]
            except Exception:
                pass
        except Exception:
            pass

    # Prepend number to outline for KODI display
    outline = movie.outline
    if outline and movie.source != "pissplay":
        outline = f"{movie.number}#{outline}"

    with open(nfo_path, "w", encoding="UTF-8") as f:
        f.write('<?xml version="1.0" encoding="UTF-8" ?>\n')
        f.write("<movie>\n")

        if jellyfin:
            f.write(f"  <title>{_esc(naming_rule)}</title>\n")
            f.write(f"  <originaltitle>{_esc(original_naming_rule)}</originaltitle>\n")
            f.write(f"  <sorttitle>{_esc(naming_rule)}</sorttitle>\n")
        else:
            f.write(f"  <title><![CDATA[{naming_rule}]]></title>\n")
            f.write(f"  <originaltitle><![CDATA[{original_naming_rule}]]></originaltitle>\n")
            f.write(f"  <sorttitle><![CDATA[{naming_rule}]]></sorttitle>\n")

        f.write("  <customrating>JP-18+</customrating>\n")
        f.write("  <mpaa>JP-18+</mpaa>\n")
        f.write(f"  <set>{_esc(movie.series)}</set>\n")
        f.write(f"  <studio>{_esc(movie.studio)}</studio>\n")
        f.write(f"  <year>{_esc(movie.year)}</year>\n")

        if jellyfin:
            f.write(f"  <outline>{_esc(outline)}</outline>\n")
            f.write(f"  <plot>{_esc(outline)}</plot>\n")
        else:
            f.write(f"  <outline><![CDATA[{outline}]]></outline>\n")
            f.write(f"  <plot><![CDATA[{outline}]]></plot>\n")

        f.write(f"  <runtime>{str(movie.runtime).replace(' ', '')}</runtime>\n")

        if show_director:
            f.write(f"  <director>{_esc(movie.director)}</director>\n")

        f.write(f"  <poster>{_esc(poster_path)}</poster>\n")
        f.write(f"  <thumb>{_esc(thumb_path)}</thumb>\n")
        if not jellyfin:
            f.write(f"  <fanart>{_esc(fanart_path)}</fanart>\n")

        # Actors
        for actor_name in movie.actor_list:
            f.write("  <actor>\n")
            f.write(f"    <name>{_esc(actor_name)}</name>\n")
            photo_url = movie.actor_photo.get(actor_name)
            if photo_url:
                f.write(f"    <thumb>{_esc(photo_url)}</thumb>\n")
            f.write("  </actor>\n")

        f.write(f"  <maker>{_esc(movie.studio)}</maker>\n")
        f.write(f"  <label>{_esc(movie.label)}</label>\n")

        # Tags (not in jellyfin mode)
        if not jellyfin:
            if actor_only_tag:
                for actor_name in movie.actor_list:
                    f.write(f"  <tag>{_esc(actor_name)}</tag>\n")
            else:
                if cn_sub:
                    f.write("  <tag>中文字幕</tag>\n")
                if leak:
                    f.write("  <tag>流出</tag>\n")
                if uncensored:
                    f.write("  <tag>无码</tag>\n")
                if hack:
                    f.write("  <tag>破解</tag>\n")
                if _4k:
                    f.write("  <tag>4k</tag>\n")
                if iso:
                    f.write("  <tag>原盘</tag>\n")
                for t in movie.tag:
                    f.write(f"  <tag>{_esc(t)}</tag>\n")

        # Genres
        if cn_sub:
            f.write("  <genre>中文字幕</genre>\n")
        if leak:
            f.write("  <genre>无码流出</genre>\n")
        if uncensored:
            f.write("  <genre>无码</genre>\n")
        if hack:
            f.write("  <genre>破解</genre>\n")
        if _4k:
            f.write("  <genre>4k</genre>\n")
        for t in movie.tag:
            f.write(f"  <genre>{_esc(t)}</genre>\n")

        f.write(f"  <num>{_esc(movie.number)}</num>\n")
        f.write(f"  <premiered>{_esc(movie.release)}</premiered>\n")
        f.write(f"  <releasedate>{_esc(movie.release)}</releasedate>\n")
        f.write(f"  <release>{_esc(movie.release)}</release>\n")

        # User rating from old NFO
        if old_userrating:
            f.write(f"  <userrating>{old_userrating}</userrating>\n")

        # Ratings from scraper or old NFO
        try:
            f_rating = movie.userrating
            uc = movie.uservotes
            if isinstance(f_rating, (int, float)) and f_rating:
                f.write(f"  <rating>{round(f_rating * 2.0, 1)}</rating>\n")
                f.write(f"  <criticrating>{round(f_rating * 20.0, 1)}</criticrating>\n")
                f.write("  <ratings>\n")
                f.write('    <rating name="javdb" max="5" default="true">\n')
                f.write(f"      <value>{f_rating}</value>\n")
                f.write(f"      <votes>{uc}</votes>\n")
                f.write("    </rating>\n")
                f.write("  </ratings>\n")
            elif old_rating:
                f.write(f"  <rating>{old_rating}</rating>\n")
                if old_criticrating:
                    f.write(f"  <criticrating>{old_criticrating}</criticrating>\n")
                if old_ratings_xml is not None:
                    f.write(
                        "  "
                        + etree.tostring(old_ratings_xml, encoding="unicode", pretty_print=True)
                    )
        except Exception:
            pass

        f.write(f"  <cover>{_esc(movie.cover)}</cover>\n")
        if show_trailer and movie.trailer:
            f.write(f"  <trailer>{_esc(movie.trailer)}</trailer>\n")
        f.write(f"  <website>{_esc(movie.website)}</website>\n")
        f.write("</movie>\n")

    logger.info("Wrote!            %s", nfo_path.name)


def _esc(text) -> str:
    """Escape text for XML. Handle None gracefully."""
    if not text:
        return ""
    if not isinstance(text, str):
        return str(text)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
