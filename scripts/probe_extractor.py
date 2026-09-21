#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Which sites does the shipped server-extractor route actually serve?

The 1.5.1 build resolves Facebook on device and sends everything else to
api.allmediadownloader.com (job API) with api.twirrl.app as the X/Bluesky/
Mastodon last resort. This probes that route per site, with the query strings a
pasted link really carries (?s=20&t=, ?utm_source=, ?_r=1) because the share
sheet strips them and a paste does not.

    python -X utf8 scripts/probe_extractor.py [--only x,reddit] [--budget 120]
"""
import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.allmediadownloader.com/download"
VERSION = "9.0.0"  # the client gate 1.4/1.5 send

CASES = [
    ("X video", "https://x.com/NASA/status/1732824684683784516", ""),
    ("X video (pasted params)", "https://x.com/NASA/status/1732824684683784516?s=20&t=AbCdEf", ""),
    ("X photo", "https://x.com/wexler/status/501860042338213889", ""),
    ("X photo (photo/1 form)", "https://twitter.com/wexler/status/501860042338213889/photo/1", ""),
    ("Facebook video", "https://www.facebook.com/watch/?v=815233250817277", "device resolves this"),
    ("Facebook reel", "https://www.facebook.com/reel/815233250817277", "device resolves this"),
    ("Reddit image", "https://www.reddit.com/r/pics/comments/1abcde/title/", ""),
    ("Reddit (pasted params)", "https://www.reddit.com/r/pics/comments/1abcde/title/?utm_source=share&utm_name=ios", ""),
    ("Threads post", "https://www.threads.net/@natgeo/post/C8abcDefGhi", ""),
    ("Pinterest pin", "https://www.pinterest.com/pin/93660867247422713/", ""),
    ("SoundCloud track", "https://soundcloud.com/forss/flickermood", ""),
    ("Vimeo video", "https://vimeo.com/76979871", ""),
    ("DailyMotion video", "https://www.dailymotion.com/video/x8n4jzh", ""),
    ("Bluesky post", "https://bsky.app/profile/jay.bsky.team/post/3mvorbgjaks24", ""),
    ("LinkedIn post", "https://www.linkedin.com/posts/x_y-activity-7123456789", ""),
    ("Snapchat spotlight", "https://www.snapchat.com/spotlight/abc123", ""),
    ("Mastodon status", "https://mastodon.social/@mastodon/117303445557305921", ""),
    ("Instagram post", "https://www.instagram.com/p/Cabcdefghij/", "device yt-dlp"),
]


def post(url):
    body = json.dumps({"url": url}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Content-Type": "application/json", "x-shortcut-version": VERSION})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:200].decode("utf-8", "replace")


def poll(jid):
    req = urllib.request.Request(API + "/" + jid, headers={"x-shortcut-version": VERSION})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--budget", type=int, default=150, help="seconds for the whole run")
    ap.add_argument("--polls", type=int, default=10)
    a = ap.parse_args()
    only = set(a.only.split(",")) if a.only else None
    t0 = time.time()
    print("%-26s %-8s %-9s %s" % ("case", "status", "seconds", "result"))
    for label, url, note in CASES:
        key = label.split()[0].lower()
        if only and key not in only:
            continue
        if time.time() - t0 > a.budget:
            print("%-26s %-8s %-9s %s" % (label, "-", "-", "budget reached, skipped"))
            continue
        try:
            st, d = post(url)
        except Exception as e:  # noqa: BLE001
            print("%-26s %-8s %-9s %s" % (label, "ERR", "-", type(e).__name__))
            continue
        if st != 201 or not isinstance(d, dict) or not d.get("id"):
            print("%-26s %-8s %-9s %s" % (label, st, "0.0",
                                          str(d)[:90] + ("  [%s]" % note if note else "")))
            continue
        jid = d["id"]
        result, start = "no terminal status", time.time()
        for _ in range(a.polls):
            time.sleep(1)
            try:
                j = poll(jid)
            except Exception:  # noqa: BLE001
                continue
            s = j.get("status")
            if s in ("completed", "failed"):
                items = (j.get("result") or {}).get("items") or []
                if s == "completed" and items:
                    kinds = ",".join(sorted({str(i.get("type")) for i in items}))
                    result = "completed: %d item(s) [%s]" % (len(items), kinds)
                else:
                    result = "%s: %s" % (s, j.get("error") or "no items")
                break
        print("%-26s %-8s %-9.1f %s" % (label, st, time.time() - start,
                                        result + ("  [%s]" % note if note else "")))


if __name__ == "__main__":
    main()
