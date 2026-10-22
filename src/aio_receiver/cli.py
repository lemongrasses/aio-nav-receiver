"""Command line.

    aio-receiver                         open the monitor (live)
    aio-receiver --replay FILE.bin       open the monitor replaying a recording
    aio-receiver check FILE.bin          print the 可用 / 不可用 changes of a recording (no window)
    aio-receiver export FILE.bin         write FILE_nav.csv from a recording
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, config, i18n, osutil

log = logging.getLogger(__name__)
SPEEDS = ("1", "2", "5", "10")


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="aio-receiver", description="AIO NAV receiver")
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    ap.add_argument("--replay", type=Path, metavar="FILE", help="open this .bin recording instead of listening")
    ap.add_argument("--speed", choices=SPEEDS, default="1", help="replay speed")
    ap.add_argument("--verbose", action="store_true", help="debug messages in the application log")
    sub = ap.add_subparsers(dest="command")
    c = sub.add_parser("check", help="replay a recording headless and print the verdict changes")
    c.add_argument("file", type=Path)
    c.add_argument("--json", action="store_true", help="machine-readable output")
    e = sub.add_parser("export", help="write the decoded 0x04 packets of a recording as CSV")
    e.add_argument("file", type=Path)
    e.add_argument("-o", "--output", type=Path, help="default: next to the recording, _nav.csv")
    return ap


def _check(path: Path, as_json: bool, settings: config.Settings) -> int:
    from .analysis import analyse
    from .io.recording import Recording

    with Recording(path) as rec:
        rep = analyse(rec, settings.gate_config())
        unix = [rec.unix_time(tr.t) for tr in rep.transitions]
    if as_json:
        json.dump({"file": str(path), "packets": rep.packets, "duration_s": rep.duration,
                   "usable_s": rep.usable_total, "count": vars(rep.count),
                   "transitions": [{"t_s": tr.t - rep.t0, "unix_time": u, "usable": tr.verdict.usable,
                                    "reason": tr.verdict.reason.value, "text": tr.verdict.text}
                                   for tr, u in zip(rep.transitions, unix)]},
                  sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0
    print(i18n.t("cli.summary", name=path.name, n=rep.packets, d=rep.duration, u=rep.usable_total))
    print(i18n.t("cli.counts", **vars(rep.count)))
    for tr in rep.transitions:
        print(f"{tr.t - rep.t0:10.3f}  {tr.verdict.word}  {tr.verdict.text}")
    return 0


def _export(path: Path, out: Optional[Path]) -> int:
    from .io.recording import Recording, export_csv

    out = out or path.with_name(path.stem + "_nav.csv")
    with Recording(path) as rec:
        rows = export_csv(rec, out)
    print(i18n.t("cli.exported", rows=rows, out=out))
    return 0


def main(argv: Optional[List[str]] = None) -> None:
    raw = sys.argv[1:] if argv is None else argv
    if any(a in ("check", "export", "--version", "-h", "--help") for a in raw):
        osutil.attach_console()     # windowed Windows build: show the output in the calling console
    args = _parser().parse_args(argv)
    log_path = osutil.setup_logging(args.verbose)
    settings, problems = config.load()
    i18n.set_language(settings.language)
    if problems:                        # say what was wrong in the language just chosen
        settings, problems = config.load()
    log.info("aio-receiver %s on %s, log %s", __version__, sys.platform, log_path)
    try:
        if args.command == "check":
            sys.exit(_check(args.file, args.json, settings))
        if args.command == "export":
            sys.exit(_export(args.file, args.output))
    except (OSError, ValueError) as e:
        print(f"{args.file}: {e}", file=sys.stderr)
        sys.exit(2)
    from .ui.main_window import run  # tkinter only for the window

    run(settings, problems, args.replay, float(args.speed))
