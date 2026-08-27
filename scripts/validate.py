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
]:
    print(repr(s), blob.count(s))
if bad:
    raise SystemExit(1)
