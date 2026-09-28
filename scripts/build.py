#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build fed.unsigned.plist from a known-good base with a chosen feature set.

Why this exists: build a selected set of on-device fast paths from the clean
1.4 graph. Keeping the site list explicit makes it possible to ship and test a
single platform without reintroducing a regression in another branch.

    python -X utf8 scripts/build.py --base <plist> --version 1.6 \
        --sites facebook,threads --out shortcut/fed.unsigned.plist
"""
import argparse
import os
import plistlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_v15 as B  # noqa: E402  (reuses the per-site action builders)
from wf import Graph  # noqa: E402

SITE_BUILDERS = {
    "facebook": B.facebook,
    "threads": B.threads,
    "x": B.x_branch,
    "mastodon": B.mastodon,
    "bluesky": B.bluesky,
    "pinterest": B.pinterest,
}

COMMENT = """FREE Media Downloader
Version {v}  ({d})
RoutineHub 26384. If the listing is newer than this number, update from there.

Sites: YouTube, YouTube Music, TikTok, Instagram, Facebook, X, Threads, Bluesky, Mastodon, Reddit, Pinterest, LinkedIn, Snapchat, Vimeo, DailyMotion, SoundCloud.

Facebook and Threads public media resolve on the phone without a server job. Facebook videos and Reels come from the video player; photos come from the public post embed.
Threads public videos and images come from the post page. Private or login-gated posts open Threads or the default browser with a clear retry instruction.
{extras}
YouTube and Instagram: yt-dlp in a-Shell mini. Video and photos go to Photos. Audio goes to Files.
TikTok: no-watermark when the source lets it. X, Bluesky, Mastodon and Pinterest use the server extractor and the other free backends.
Share a link. Save the file. No key. No paywall. No upgrade nag.
First Photos, Files, and a-Shell prompts: approve once.
If a post is private, the shortcut opens Threads when installed, or your default browser. Sign in there, then share the post again."""

EXTRA = {
    "x": "X, Bluesky, Mastodon and Pinterest also resolve on the phone in one request.",
    "mastodon": "X, Bluesky, Mastodon and Pinterest also resolve on the phone in one request.",
    "bluesky": "X, Bluesky, Mastodon and Pinterest also resolve on the phone in one request.",
    "pinterest": "X, Bluesky, Mastodon and Pinterest also resolve on the phone in one request.",
}


def build_sites(sites):
    g = Graph()
    for name in sites:
        SITE_BUILDERS[name](g)
    g.close()
    assert not g._stack, "unbalanced control flow in %s" % sites
    return [a.d for a in g.actions]


def main():
    if "--i-know-this-drops-1.5.1" not in sys.argv:
        raise SystemExit("build.py starts from the 1.4 base and drops 1.5.1's full a-Shell fallback "
                         "(that is how 1.6 broke). Release builds: scripts/build_release.py")
    sys.argv.remove("--i-know-this-drops-1.5.1")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="plist to start from (known-good)")
    ap.add_argument("--version", required=True)
    ap.add_argument("--date", default="2026-09-26")
    ap.add_argument("--sites", required=True, help="comma list: facebook,threads,x,mastodon,bluesky,pinterest")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    sites = [s.strip() for s in a.sites.split(",") if s.strip()]
    unknown = [s for s in sites if s not in SITE_BUILDERS]
    if unknown:
        raise SystemExit("unknown site(s): %s" % unknown)

    p = plistlib.loads(open(a.base, "rb").read())
    acts = p["WFWorkflowActions"]
    blob = str(acts)
    for probe, name in (("api.fxtwitter.com", "x"), ("pin_ids=", "pinterest"),
                        ("getPostThread", "bluesky"), ("api/v1/statuses/", "mastodon"),
                        ("video/embed?video_id=", "facebook")):
        if probe in blob:
            raise SystemExit("base already contains the %s fast path; pass a clean base" % name)

    B.VERSION = a.version
    B.NEW_COMMENT = COMMENT.format(v=a.version, d=a.date,
                                   extras=EXTRA.get(sites[0], "") if len(sites) == 1 else "")
    new = build_sites(sites)

    idx = B.find_aggregator(acts)
    before = len(acts)
    acts[idx:idx] = new
    B.patch_settings(acts)
    B.patch_comment(acts)
    changed = B.patch_poll(acts)
    notice = B.patch_failure_notice(acts)
    signin = B.patch_signin_copy(acts)
    assert changed["delay"] and changed["number"], "poll cadence not found"
    assert notice, "failure notice not found"
    assert signin, "sign-in copy not found"

    tmp = a.out + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(p, fh, fmt=plistlib.FMT_XML)
    check = plistlib.loads(open(tmp, "rb").read())
    assert len(check["WFWorkflowActions"]) == len(acts), "round-trip lost actions"
    os.replace(tmp, a.out)
    print("sites=%s  inserted=%d actions at %d (%d -> %d)"
          % (",".join(sites), len(new), idx, before, len(acts)))
    print("wrote %s (%d bytes)" % (a.out, os.path.getsize(a.out)))


if __name__ == "__main__":
    sys.exit(main())
