#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HubSign the unsigned plist and write Google Drive → My Drive."""
import json
import plistlib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "FREE Media Downloader"
DOCS = Path(r"H:\My Drive")

xml = (ROOT / "shortcut" / "fed.unsigned.plist").read_bytes()
# round-trip to prove it still parses
plistlib.loads(xml)
body = json.dumps({"shortcutName": NAME, "shortcut": xml.decode("utf-8")}).encode("utf-8")
req = urllib.request.Request(
    "https://hubsign.routinehub.services/sign",
    data=body,
    headers={
        "Content-Type": "application/json",
        "User-Agent": "cherri/1.0",
        "Origin": "https://routinehub.co",
        "Referer": "https://routinehub.co/",
    },
    method="POST",
)
with urllib.request.urlopen(req, timeout=90) as resp:
    signed = resp.read()
if signed[:4] != b"AEA1":
    raise SystemExit("HubSign did not return AEA1")
DOCS.mkdir(parents=True, exist_ok=True)
dest = DOCS / f"{NAME}.shortcut"
dest.write_bytes(signed)
print("wrote", dest, dest.stat().st_size)
