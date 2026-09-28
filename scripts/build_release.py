#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the release shortcut on top of the RoutineHub 1.5.1 graph.

1.5.1 (tests/fixtures/good-1.5.1.plist, commit c3966fa, RoutineHub iCloud
1e4945fd5e834686b166491329d3928d) is the build users confirmed works. Platforms
confirmed on a real phone are LOCKED (tests/locked-platforms.json): the steps a
locked platform's share runs must stay byte-identical to 1.5.1, and
scripts/test_input.py (run by sign.py) refuses to sign otherwise.

Each release starts from the lock baseline (the last build the user confirmed
on their phone) and adds only what is new. Already in the confirmed 1.7
baseline:

  facebook section  inside 1.5.1's `If userLink contains "facebook.com"`:
                    Threads and Facebook share links (the phone expands them
                    to facebook.com/unsupportedbrowser) are resolved, Threads
                    posts download on the phone, and 1.5.1's Facebook steps
                    are stored the way the Shortcuts app stores them
                    (fb_section.py)
  tiktok photos     inside the TikTok section: slideshows save the photos,
                    not the song (build_v15.patch_tiktok_photos)
  fb fields         the two Facebook embed URLs store their variable natively
                    (build_v15.patch_wrapped_tokens)

New in this release:

  reddit            Reddit /s/ share links, in the sign-in tail of the
                    server-failed branch, which no working share reaches
                    (reddit_tail.py)
  mastodon          posts on any Mastodon server, same place, from the
                    server's public API (reddit_tail.mastodon_block)

1.6 was built from the 1.4 base with build.py and silently dropped 1.5.1's
full a-Shell fallback (24 actions). Do not build releases from 1.4.

    python -X utf8 scripts/build_release.py --version 1.7 --date 2026-09-28
"""
import argparse
import json
import os
import plistlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_v15 as B  # noqa: E402
import fb_section  # noqa: E402,F401  (already in the confirmed baseline)
import reddit_tail  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.path.join(ROOT, "tests", "fixtures", "good-1.5.1.plist")
OUT = os.path.join(ROOT, "shortcut", "fed.unsigned.plist")
LOCK = os.path.join(ROOT, "tests", "locked-platforms.json")
FULL_ASHELL = "AsheKube.app.a-Shell.ExecuteCommandIntent"

COMMENT = """FREE Media Downloader
Version {v}  ({d})
RoutineHub 26384. If the listing is newer than this number, update from there.

Sites: YouTube, YouTube Music, TikTok, Instagram, Facebook, X, Threads, Bluesky, Mastodon, Reddit, Pinterest, LinkedIn, Snapchat, Vimeo, DailyMotion, SoundCloud.

Facebook resolves on the phone in one request: videos and Reels from the video player, photos from the public post embed.
Threads and Facebook shares resolve on the phone too: Threads posts download from the post page, Facebook reels from the video player. No sign-in.

YouTube and Instagram: yt-dlp in a-Shell mini or a-Shell. Video and photos go to Photos. Audio goes to Files.
TikTok: no-watermark when the source lets it. X, Bluesky, Mastodon and Pinterest use the server extractor and the other free backends.
Share a link. Save the file. No key. No paywall. No upgrade nag.
First Photos, Files, and a-Shell prompts: approve once.
A sign-in wall opens Safari or the app. Share again after."""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--date", required=True)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()

    # Start from the build the user last confirmed on their phone (the lock
    # baseline), never from an older base: rebuilding confirmed code would
    # change it. Only additions that are not in it yet are applied.
    lock = json.load(open(LOCK, encoding="utf-8"))
    p = plistlib.load(open(os.path.join(ROOT, lock["baseline"]), "rb"))
    acts = p["WFWorkflowActions"]
    B.find_input_block(acts)
    if sum(x["WFWorkflowActionIdentifier"] == FULL_ASHELL for x in acts) != 3:
        raise SystemExit("baseline lost the 1.5.1 full a-Shell fallback; refusing to build")
    present = {str(x["WFWorkflowActionParameters"].get("WFCommentActionText", ""))[5:].split(":")[0]
               for x in acts if str(x["WFWorkflowActionParameters"].get("WFCommentActionText", "")).startswith("FMD+ ")}
    if "Reddit share links" not in present:
        reddit_tail.patch(acts)
    if "Mastodon posts" not in present:
        reddit_tail.patch_mastodon(acts)
    B.VERSION = a.version
    B.NEW_COMMENT = COMMENT.format(v=a.version, d=a.date)
    B.patch_settings(acts)
    B.patch_comment(acts)

    tmp = a.out + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(p, fh, fmt=plistlib.FMT_XML)
    assert len(plistlib.load(open(tmp, "rb"))["WFWorkflowActions"]) == len(acts)
    os.replace(tmp, a.out)
    print("%s + %s -> %s (%d actions, version %s)"
          % (lock["baseline"], ", ".join(sorted({"Reddit share links", "Mastodon posts"} - present)) or "nothing new",
             a.out, len(acts), a.version))


if __name__ == "__main__":
    sys.exit(main())
