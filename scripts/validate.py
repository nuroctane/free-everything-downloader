#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate the unsigned shortcut: structure, version gates and required strings.

This is the guard rail for hand- or script-generated action graphs. It fails on
grouping imbalance, duplicate UUIDs, malformed control flow, the aggregator's
client-version gate moving, and any site path going missing.
"""
from collections import defaultdict
from pathlib import Path
import plistlib
import re

ROOT = Path(__file__).resolve().parents[1]
p = plistlib.loads((ROOT / "shortcut" / "fed.unsigned.plist").read_bytes())
actions = p["WFWorkflowActions"]

bad = 0

# --- 1. control-flow grouping balance (order sensitive) ------------------
stack = defaultdict(list)
order = []
for i, a in enumerate(actions):
    prm = a.get("WFWorkflowActionParameters") or {}
    g = prm.get("GroupingIdentifier")
    mode = prm.get("WFControlFlowMode")
    if g is None or mode is None:
        continue
    if mode == 0:
        stack[g].append("open")
        order.append([g, i])
    elif mode == 1:
        if not order or order[-1][0] != g:
            bad += 1
            print("OTHERWISE does not match the open branch at", i, g[:8])
    elif mode == 2:
        stack[g].append("end")
        if not order or order[-1][0] != g:
            bad += 1
            print("END does not match the open branch at", i, g[:8])
        else:
            order.pop()
if order:
    bad += 1
    print("UNCLOSED control flow at end of shortcut:", [(g[:8], i) for g, i in order])
for g, ev in stack.items():
    if ev.count("open") != ev.count("end"):
        bad += 1
        print("UNBALANCED", g[:8], ev)

# --- 2. duplicate uuids ---------------------------------------------------
seen = defaultdict(int)
for a in actions:
    u = (a.get("WFWorkflowActionParameters") or {}).get("UUID")
    if u:
        seen[u] += 1
dupes = [u for u, n in seen.items() if n > 1]
if dupes:
    bad += 1
    print("DUPLICATE UUIDs", dupes[:5])

# --- 3. actions must be well formed --------------------------------------
for i, a in enumerate(actions):
    ident = a.get("WFWorkflowActionIdentifier")
    prm = a.get("WFWorkflowActionParameters")
    if not ident or not isinstance(prm, dict):
        bad += 1
        print("MALFORMED ACTION", i, ident)
        continue
    if ident == "is.workflow.actions.text.match" and "WFMatchTextPattern" not in prm:
        bad += 1
        print("MATCH without pattern at", i)
    if ident == "is.workflow.actions.text.match.getgroup":
        if prm.get("WFGetGroupType") not in ("Group At Index", "All Groups"):
            bad += 1
            print("GETGROUP without type at", i)
    if ident == "is.workflow.actions.text.replace":
        for k in ("WFReplaceTextFind", "WFReplaceTextReplace", "WFInput"):
            if k not in prm:
                bad += 1
                print("REPLACE missing", k, "at", i)
    if ident == "is.workflow.actions.conditional":
        if "WFControlFlowMode" not in prm or "GroupingIdentifier" not in prm:
            bad += 1
            print("CONDITIONAL missing flow keys at", i)
        elif prm["WFControlFlowMode"] == 0:
            inp = prm.get("WFInput")
            if not (isinstance(inp, dict) and inp.get("Type") == "Variable"
                    and "Variable" in inp):
                bad += 1
                print("CONDITIONAL input is not the app's variable wrapper at", i)
    if ident == "is.workflow.actions.getvalueforkey":
        inp = prm.get("WFInput")
        if not (isinstance(inp, dict) and inp.get("WFSerializationType")
                == "WFTextTokenAttachment"):
            bad += 1
            print("GETVALUE input is not a plain attachment at", i)
        if "WFDictionaryKey" not in prm:
            bad += 1
            print("GETVALUE without key at", i)
    if ident == "is.workflow.actions.repeat.each":
        if "WFControlFlowMode" not in prm or "GroupingIdentifier" not in prm:
            bad += 1
            print("REPEAT missing flow keys at", i)

# --- 4. version gates ----------------------------------------------------
def settings_dict():
    for a in actions:
        prm = a.get("WFWorkflowActionParameters") or {}
        if (a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.dictionary"
                and prm.get("CustomOutputName") == "Settings"):
            return prm
    return None


def token_text(v):
    if isinstance(v, str):
        return v
    if isinstance(v, dict) and isinstance(v.get("Value"), dict):
        return v["Value"].get("string")
    return None


def sub_items(item):
    """Items of a nested WFDictionaryFieldValue, however deep the wrapper is."""
    v = item.get("WFValue")
    for _ in range(4):
        if not isinstance(v, dict):
            return []
        if "WFDictionaryFieldValueItems" in v:
            return v["WFDictionaryFieldValueItems"]
        v = v.get("Value")
    return []


sets = settings_dict()
if sets is None:
    raise SystemExit("missing Settings dictionary")
gate = None
user_version = None
for it in sets["WFItems"]["Value"]["WFDictionaryFieldValueItems"]:
    k = token_text(it.get("WFKey"))
    if k == "version":
        user_version = token_text(it.get("WFValue"))
    elif k == "shortcut":
        for it2 in sub_items(it):
            if token_text(it2.get("WFKey")) == "version":
                gate = token_text(it2.get("WFValue"))
if gate != "9.0.0":
    bad += 1
    print("AGGREGATOR GATE MOVED: shortcut.version =", gate,
          "(must stay 9.0.0 or every server extraction returns HTTP 426)")
if user_version is None:
    bad += 1
    print("Settings.version missing")

blob = str(actions)
mv = re.search(r"Version (\d+\.\d+(?:\.\d+)?)\s+\(", blob)
version = mv.group(1) if mv else None
if not version:
    bad += 1
    print("missing Version comment")
elif user_version != version:
    bad += 1
    print("Settings.version %r does not match the comment %r" % (user_version, version))
if re.search(r"Version 1\.[0-4]\b", blob):
    bad += 1
    print("stale version string still in the plist")

# --- 5. required content per site path -----------------------------------
required = {
    # app + engine
    "a-Shell mini": "yt-dlp app name",
    "yt-dlp": "engine",
    "yt-dlp-ejs": "YouTube JS helper install",
    "yt-dlp-apple-webkit-jsi": "Apple WebKit JS helper install",
    "AsheKube.app.a-Shell-mini.GetFileIntent": "pull the file back into Shortcuts",
    # per-site fast paths (Facebook is always present in 1.5+)
    "facebookexternalhit": "Facebook crawler UA",
    "video/embed?video_id=": "Facebook player fast path",
    "plugins/post.php": "Facebook photo fast path",
    "Saved from Facebook.": "Facebook notice",
    "instagram.com": "Instagram",
    "youtu": "YouTube",
    # aggregator fallback
    "allmediadownloader": "server extractor fallback",
    "api.twirrl.app": "X/Bluesky/Mastodon last-resort backend",
    # notices
    "Saved to Photos.": "photos notice",
    "Couldn't grab a file from that link": "honest failure notice",
    # listing copy
    "FREE Media Downloader": "display name",
    "SoundCloud": "sites list in comment",
}
for needle, why in required.items():
    if needle not in blob:
        bad += 1
        print("MISSING %-42s (%s)" % (needle, why))

# Optional per-site fast paths: if a feature is in the build, it must be whole.
per_feature = {
    "api.fxtwitter.com": ["Saved from X.", "fxtwitter"],
    "getPostThread": ["com.atproto.sync.getBlob"],
    "api/v1/statuses/": ["Saved from Mastodon."],
    "pin_ids=": ["Saved from Pinterest."],
}
for probe, needles in per_feature.items():
    if probe not in blob:
        continue
    for needle in needles:
        if needle not in blob:
            bad += 1
            print("FEATURE %s present but missing %s" % (probe, needle))

forbidden = {
    "Free EVERYTHING Downloader": "old display name",
    "bestvideo+bestaudio": "YouTube merge that needs ffmpeg",
    "photos.createalbum": "Create Album is forbidden; Save to Camera Roll only",
    "tvdl.app/upgrade": "pro nag",
}
for needle, why in forbidden.items():
    if needle in blob:
        bad += 1
        print("FORBIDDEN %-40s (%s)" % (needle, why))

# --- 6. fallback tuning --------------------------------------------------
delays = [(a.get("WFWorkflowActionParameters") or {}).get("WFDelayTime")
          for a in actions if a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.delay"]
numbers = [str((a.get("WFWorkflowActionParameters") or {}).get("WFNumberActionNumber"))
           for a in actions if a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.number"]
# A string here is silently blanked by iOS, leaving Wait with no duration.
if (len(delays) != 1 or isinstance(delays[0], bool)
        or not isinstance(delays[0], (int, float)) or delays[0] <= 0):
    bad += 1
    print("Wait duration must be a positive NUMBER, not a string:", delays)
if "60" not in numbers:
    bad += 1
    print("expected the poll ceiling of 60, got numbers", numbers)
if isinstance(numbers[0] if numbers else None, float):
    bad += 1
    print("poll ceiling should stay a string like the rest of the file:", numbers[:3])

print("actions %d | groups %d | unbalanced %d | problems %d"
      % (len(actions), len(stack), sum(1 for e in stack.values() if e.count("open") != e.count("end")), bad))
if bad:
    raise SystemExit(1)
print("OK")
