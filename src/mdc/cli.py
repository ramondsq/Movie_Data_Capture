"""CLI entry point for Movie Data Capture."""

from __future__ import annotations

import argparse
import logging
import os
import platform
import random
import re
import signal
import sys
import time
from datetime import timedelta
from pathlib import Path

import urllib3

from mdc import __version__
from mdc import config
from mdc.number import get_number
from mdc.pipeline import debug_print, fetch_metadata, process_movie, process_movie_no_net
from mdc.organizer import move_to_failed
from mdc.utils import file_modification_days

logger = logging.getLogger(__name__)


def main():
    """Main CLI entry point."""
    urllib3.disable_warnings()

    conf = config.getInstance()
    args = _parse_args(conf)

    _setup_logging(args.debug)
    _setup_signals()

    logger.info("=" * 54)
    logger.info("Movie Data Capture v%s", __version__)
    logger.info(
        "%s - %s - Python %s",
        platform.platform(), platform.machine(), platform.python_version(),
    )
    logger.info("=" * 54)

    start_time = time.time()
    logger.info("Start at %s", time.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("Config: %s", conf.ini_path)

    if conf.debug():
        logger.info("Debug mode enabled")
    if conf.link_mode() in (1, 2):
        mode_name = "soft" if conf.link_mode() == 1 else "hard"
        logger.info("Link mode: %s", mode_name)

    main_mode = conf.main_mode()
    if main_mode not in (1, 2, 3):
        logger.error("Main mode must be 1, 2 or 3!")
        sys.exit(4)

    logger.info(
        "Mode %d: %s",
        main_mode,
        ["Scraping", "Organizing", "Scraping in-place"][main_mode - 1],
    )

    # Create failed folder
    failed_folder = conf.failed_folder()
    Path(failed_folder).mkdir(parents=True, exist_ok=True)

    # OpenCC converter
    open_cc = _init_opencc(conf)

    # --- Search mode ---
    if args.search:
        _run_search(args.search, open_cc, conf)
        return

    # --- Single file mode ---
    if args.file:
        logger.info("=" * 20 + " Single File " + "=" * 21)
        number = args.number or get_number(conf.debug(), os.path.basename(args.file))
        if number:
            try:
                process_movie(
                    args.file, number, open_cc,
                    args.specified_source, args.specified_url,
                )
            except Exception as err:
                logger.error("[%s] ERROR: %s", args.file, err)
        else:
            logger.error("Could not extract number from filename")
        return

    # --- Batch mode ---
    folder_path = conf.source_folder() or os.path.abspath(".")
    movie_list = _scan_movies(folder_path, args.regexstr, conf)

    count_all = len(movie_list)
    logger.info("Found %d movies.", count_all)

    stop_count = conf.stop_counter()
    if stop_count < 1:
        stop_count = 999999
    else:
        count_all = min(count_all, stop_count)

    for i, movie_path in enumerate(movie_list, 1):
        pct = f"{i / count_all * 100:.1f}%" if count_all > 0 else "0%"
        logger.info(
            "--- %s [%d/%d] --- %s",
            pct, i, count_all, time.strftime("%H:%M:%S"),
        )

        n_number = get_number(conf.debug(), os.path.basename(movie_path))
        movie_path = os.path.abspath(movie_path)

        if args.zero_op:
            logger.info("[%s] %s", n_number, movie_path)
            continue

        if n_number:
            try:
                if args.no_net_op:
                    process_movie_no_net(movie_path, n_number)
                else:
                    process_movie(movie_path, n_number, open_cc)
            except Exception as err:
                logger.error("[%s] ERROR: %s", movie_path, err)
                try:
                    move_to_failed(
                        movie_path, failed_folder,
                        main_mode, conf.link_mode(), conf.failed_move(),
                    )
                except Exception:
                    pass
        else:
            logger.error("Number empty for: %s", movie_path)
            move_to_failed(
                movie_path, failed_folder,
                main_mode, conf.link_mode(), conf.failed_move(),
            )

        if i >= stop_count:
            logger.info("Stop counter triggered!")
            break

        sleep_s = random.randint(conf.sleep(), conf.sleep() + 2)
        time.sleep(sleep_s)

    # Clean up empty folders
    if conf.del_empty_folder() and not args.zero_op:
        _rm_empty_folders(conf.success_folder())
        _rm_empty_folders(failed_folder)
        if folder_path:
            _rm_empty_folders(folder_path)

    elapsed = timedelta(seconds=time.time() - start_time)
    logger.info("Done in %s at %s", str(elapsed).split(".")[0], time.strftime("%Y-%m-%d %H:%M:%S"))


def _parse_args(conf) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="mdc",
        description="Movie Data Capture — scrape and organize movie metadata",
        epilog=f"Config: {conf.ini_path}",
    )
    parser.add_argument("file", default="", nargs="?", help="Single movie file path")
    parser.add_argument("-p", "--path", default="", help="Source folder path")
    parser.add_argument(
        "-m", "--main-mode", default="", help="Mode: 1=Scrape 2=Organize 3=In-place",
    )
    parser.add_argument("-n", "--number", default="", help="Custom file number")
    parser.add_argument(
        "-L", "--link-mode", default="",
        help="Link mode: 0=move 1=symlink 2=hardlink",
    )
    parser.add_argument(
        "-q", "--regex-query", dest="regexstr", default="",
        help="Regex filter for file paths",
    )
    parser.add_argument(
        "-d", "--nfo-skip-days", dest="days", default="",
        help="Skip movies with NFO modified within N days",
    )
    parser.add_argument(
        "-c", "--stop-counter", dest="cnt", default="",
        help="Stop after processing N movies",
    )
    parser.add_argument(
        "-i", "--ignore-failed-list", action="store_true",
        help="Ignore the failed list file",
    )
    parser.add_argument("-a", "--auto-exit", action="store_true", help="Auto exit")
    parser.add_argument("-g", "--debug", action="store_true", help="Debug mode")
    parser.add_argument(
        "-N", "--no-network-operation", dest="no_net_op", action="store_true",
        help="No network (mode 3 only): re-crop covers only",
    )
    parser.add_argument(
        "-w", "--website", dest="site", default="", help="Override source websites",
    )
    parser.add_argument(
        "-D", "--download-images", dest="dnimg", action="store_true",
        help="Force re-download images",
    )
    parser.add_argument(
        "-C", "--config-override", dest="cfgcmd", action="append", nargs=1,
        help="Config override: section:key=value",
    )
    parser.add_argument(
        "-z", "--zero-operation", dest="zero_op", action="store_true",
        help="Dry run: show file list only",
    )
    parser.add_argument("-v", "--version", action="version", version=__version__)
    parser.add_argument("-s", "--search", default="", help="Search number(s)")
    parser.add_argument(
        "-ss", "--specified-source", default="", help="Specified scraper source",
    )
    parser.add_argument(
        "-su", "--specified-url", default="", help="Specified URL for scraper",
    )

    args = parser.parse_args()

    # Apply overrides to config
    def set_num(sk, val):
        if isinstance(val, str) and val.isnumeric() and int(val) >= 0:
            conf.set_override(f"{sk}={val}")

    def set_str(sk, val):
        if isinstance(val, str) and val:
            conf.set_override(f"{sk}={val}")

    def set_bool(sk, val):
        if val:
            conf.set_override(f"{sk}=1")

    set_num("common:main_mode", args.main_mode)
    set_num("common:link_mode", args.link_mode)
    set_str("common:source_folder", args.path)
    set_bool("common:auto_exit", args.auto_exit)
    set_num("common:nfo_skip_days", args.days)
    set_num("advenced_sleep:stop_counter", args.cnt)
    set_bool("common:ignore_failed_list", args.ignore_failed_list)
    set_str("priority:website", args.site)
    if args.dnimg:
        conf.set_override("common:download_only_missing_images=0")
    set_bool("debug_mode:switch", args.debug)
    if isinstance(args.cfgcmd, list):
        for cmd in args.cfgcmd:
            conf.set_override(cmd[0])

    if conf.main_mode() == 3 and args.no_net_op:
        conf.set_override(
            "advenced_sleep:stop_counter=0;advenced_sleep:rerun_delay=0s;face:aways_imagecut=1"
        )

    return args


def _setup_logging(debug: bool = False):
    """Configure logging."""
    level = logging.DEBUG if debug else logging.INFO
    fmt = "[%(levelname).1s] %(message)s"
    logging.basicConfig(level=level, format=fmt, stream=sys.stdout)
    # Quiet noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)


def _setup_signals():
    """Setup signal handlers."""
    def handler(*_args):
        logger.info("Ctrl+C detected, exiting.")
        sys.exit(9)

    signal.signal(signal.SIGINT, handler)


def _init_opencc(conf):
    """Initialize OpenCC converter if configured."""
    ccm = conf.cc_convert_mode()
    if ccm == 0:
        return None
    try:
        from opencc import OpenCC
        return OpenCC("t2s.json" if ccm == 1 else "s2t.json")
    except Exception:
        try:
            from opencc import OpenCC
            return OpenCC("t2s" if ccm == 1 else "s2t")
        except Exception:
            logger.warning("OpenCC not available, skipping CC conversion")
            return None


def _run_search(search_str: str, open_cc, conf):
    """Search mode: fetch and display metadata for given numbers."""
    for number in search_str.split(","):
        number = number.strip()
        if not number:
            continue
        movie = fetch_metadata(number, open_cc)
        if movie:
            debug_print(movie)
        else:
            logger.warning("Not found: %s", number)
        time.sleep(conf.sleep())


def _scan_movies(source_folder: str, regexstr: str, conf) -> list[str]:
    """Scan source folder for movie files to process."""
    main_mode = conf.main_mode()
    debug = conf.debug()
    nfo_skip_days = conf.nfo_skip_days()
    link_mode = conf.link_mode()
    file_types = set(conf.media_type().lower().split(","))
    trailer_re = re.compile(r"-trailer\.", re.IGNORECASE)
    cli_re = None
    if regexstr:
        try:
            cli_re = re.compile(regexstr, re.IGNORECASE)
        except Exception:
            pass

    # Load failed list
    failed_list_path = Path(conf.failed_folder()).resolve() / "failed_list.txt"
    failed_set = set()
    if (main_mode == 3 or link_mode) and not conf.ignore_failed_list():
        try:
            failed_set = set(failed_list_path.read_text(encoding="utf-8").splitlines())
        except Exception:
            pass

    source = Path(source_folder)
    if not source.is_dir():
        logger.error("Source folder not found: %s", source_folder)
        return []

    source = source.resolve()
    escape_folders = set(re.split(r"[,，]", conf.escape_folder()))
    total = []
    skip_failed = 0
    skip_nfo = 0

    for full_name in source.glob("**/*"):
        if main_mode != 3 and set(full_name.parent.parts) & escape_folders:
            continue
        if not full_name.is_file():
            continue
        if full_name.suffix.lower() not in file_types:
            continue

        absf = str(full_name)
        if absf in failed_set:
            skip_failed += 1
            if debug:
                logger.debug("Skip failed: %s", absf)
            continue

        is_sym = full_name.is_symlink()
        if main_mode != 3 and (
            is_sym or (full_name.stat().st_nlink > 1 and not conf.scan_hardlink())
        ):
            continue

        if cli_re and not cli_re.search(absf):
            continue
        if trailer_re.search(full_name.name):
            continue

        if main_mode == 3:
            nfo = full_name.with_suffix(".nfo")
            if not nfo.is_file():
                if debug:
                    logger.debug("NFO not found for: %s", absf)
            elif nfo_skip_days > 0 and file_modification_days(str(nfo)) <= nfo_skip_days:
                skip_nfo += 1
                if debug:
                    logger.debug("Skip (NFO recent): %s", absf)
                continue

        total.append(absf)

    if skip_failed:
        logger.info("Skipped %d movies in failed list.", skip_failed)
    if skip_nfo:
        logger.info("Skipped %d movies with recent NFO.", skip_nfo)

    # For link mode, also skip movies already processed in success folder
    if nfo_skip_days > 0 and link_mode and main_mode != 3:
        skip_numbers = set()
        success = Path(conf.success_folder()).resolve()
        for f in success.glob("**/*.nfo"):
            if file_modification_days(str(f)) > nfo_skip_days:
                continue
            n = get_number(False, f.stem)
            if n:
                skip_numbers.add(n.lower())

        before = len(total)
        total = [
            f for f in total
            if not (
                (n := get_number(False, os.path.basename(f)))
                and n.lower() in skip_numbers
            )
        ]
        skipped = before - len(total)
        if skipped:
            logger.info("Skipped %d already-processed movies.", skipped)

    return total


def _rm_empty_folders(path: str):
    """Remove empty folders recursively."""
    if not path or not os.path.isdir(path):
        return
    abspath = os.path.abspath(path)
    deleted = set()
    for current_dir, subdirs, files in os.walk(abspath, topdown=False):
        try:
            has_subdirs = any(
                os.path.join(current_dir, s) not in deleted for s in subdirs
            )
            if not files and not has_subdirs and not os.path.samefile(path, current_dir):
                os.rmdir(current_dir)
                deleted.add(current_dir)
                logger.info("Deleted empty folder: %s", current_dir)
        except Exception:
            pass
