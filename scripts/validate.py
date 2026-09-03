#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate unsigned shortcut grouping and required strings."""
from collections import defaultdict
from pathlib import Path
import plistlib

ROOT = Path(__file__).resolve().parents[1]
p = plistlib.loads((ROOT / "shortcut" / "fed.unsigned.plist").read_bytes())
actions = p["WFWorkflowActions"]
stack = defaultdict(list)
for i, a in enumerate(actions):
    prm = a.get("WFWorkflowActionParameters") or {}
    g = prm.get("GroupingIdentifier")
    mode = prm.get("WFControlFlowMode")
    if g is None or mode is None:
        continue
    if mode == 0:
        stack[g].append("open")
    elif mode == 2:
        stack[g].append("end")
bad = 0
for g, ev in stack.items():
    if ev.count("open") != ev.count("end"):
        bad += 1
        print("UNBALANCED", g[:8], ev)
blob = str(actions)
print("n", len(actions), "groups", len(stack), "unbalanced", bad)
for s in [
    "yt-dlp",
    "a-Shell mini",
    "instagram.com",
    "youtu",
    "tikwm",
    "waittoreturn",
    "tvdl.app/upgrade",
    "AMD Key",
    "Version 1.4",
    "SoundCloud",
    "FREE Media Downloader",
    "yt-dlp-ejs",
    "yt-dlp-apple-webkit-jsi",
]:
    print(repr(s), blob.count(s))
if "Version 1.4" not in blob:
    raise SystemExit("missing Version 1.4 comment")
if "bestvideo+bestaudio" in blob:
    raise SystemExit("YouTube command still requires an ffmpeg merge")
if "yt-dlp-apple-webkit-jsi" not in blob:
    raise SystemExit("missing Apple WebKit JS helper install")
if "photos.createalbum" in blob:
    raise SystemExit("Create Album is forbidden; use Save to Camera Roll only")
if "GetFileIntent" not in blob:
    raise SystemExit("yt-dlp path never pulls the file back into Shortcuts")
if "Saved to Photos." not in blob:
    raise SystemExit("missing Saved to Photos notice")
if "SoundCloud" not in blob:
    raise SystemExit("missing sites list in comment")
if "FREE Media Downloader" not in blob:
    raise SystemExit("missing new display name")
if "Free EVERYTHING Downloader" in blob:
    raise SystemExit("old display name still in plist")
if bad:
    raise SystemExit(1)
