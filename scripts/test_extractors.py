#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live verification of every extraction recipe the shortcut implements.

Each recipe mirrors, step for step, what the Shortcut does with
"Get Contents of URL" + "Match Text" actions, so a PASS here means the
action graph in shortcut/fed.unsigned.plist is exercising a live path.

    python -X utf8 scripts/test_extractors.py           # everything
    python -X utf8 scripts/test_extractors.py --only fb,x
    python -X utf8 scripts/test_extractors.py --list

Exit code is non-zero if any *required* case fails.
"""
import argparse
import json
import os
import plistlib
import re
import sys
import urllib.parse
import urllib.request

CRAWLER_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")

TIMEOUT = 30


def get(url, ua=None, headers=None, raw=False, method="GET", body=None):
    h = {"User-Agent": ua or MOBILE_UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, method=method, data=body)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        data = r.read()
        return {
            "status": r.status,
            "ct": r.headers.get("Content-Type", ""),
            "len": len(data),
            "text": None if raw else data.decode("utf-8", "replace"),
            "bytes": data,
            "url": r.geturl(),
        }


def head(url, ua=None, headers=None):
    """Small ranged GET - cheaper and more reliable than HEAD on CDNs."""
    h = {"User-Agent": ua or MOBILE_UA, "Range": "bytes=0-262143"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        b = r.read()
        return {"status": r.status, "ct": r.headers.get("Content-Type", ""),
                "len": len(b), "total": r.headers.get("Content-Range")}


# ---------------------------------------------------------------- facebook
FB_HOSTS = ("facebook.com", "fb.watch", "fb.gg", "m.facebook.com", "fb.com")

FB_ID_PATTERNS = [
    r"/reels?/(\d{6,})",
    r"/videos?/(?:[^/?#]+/)?(\d{6,})",
    r"[?&]v=(\d{6,})",
    r"/video\.php\?v=(\d{6,})",
    r"/posts/(\d{6,})",
    r"[?&](?:fbid|story_fbid)=(\d{6,})",
]


def fb_video_id(url):
    for p in FB_ID_PATTERNS:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def fb_sniff_id(url):
    """Fetch the page the way the shortcut does and look for video_id."""
    r = get(url, ua=CRAWLER_UA)
    m = re.search(r'"video_id":"(\d{6,})"', r["text"] or "")
    return m.group(1) if m else None


def fb_video(url):
    """Reel / video: embed page -> hd_src|sd_src -> direct mp4."""
    vid = fb_video_id(url)
    if not vid:
        vid = fb_sniff_id(url)
    if not vid:
        return []
    r = get("https://www.facebook.com/video/embed?video_id=%s" % vid, ua=CRAWLER_UA)
    html = r["text"] or ""
    out = []
    for key in ("hd_src", "sd_src",
                "browser_native_hd_url", "browser_native_sd_url", "playable_url"):
        m = re.search(r'"%s":"([^"]+)"' % key, html)
        if m:
            out.append(m.group(1).replace("\\/", "/").replace("\\u0025", "%"))
            break
    return out


def _lookaside(urls):
    """Keep lookaside media images, drop the page avatar."""
    return re.findall(r'src="(https://lookaside\.fbsbx\.com/lookaside/crawler/media/\?media_id=\d+)"', urls)


def fb_photo(url):
    """Photo / multi-photo / photo post: plugins/post.php -> lookaside media."""
    q = urllib.parse.quote(url, safe="")
    r = get("https://www.facebook.com/plugins/post.php?href=%s" % q, ua=CRAWLER_UA)
    html = r["text"] or ""
    # primary: the article media img (class _1p6f*) instead of the page avatar
    out = re.findall(r'class="_1p6f[^"]*"[^>]*\bsrc="([^"]+)"', html)
    if out:
        return [u.replace("&amp;", "&") for u in out]
    out = re.findall(r'src="(https://lookaside\.fbsbx\.com/lookaside/crawler/media/\?media_id=\d+)"[^>]*style="max-width', html)
    if out:
        return [u.replace("&amp;", "&") for u in out]
    # last resort: every lookaside except the one in the page-header link
    avatar = re.search(r'<a href="https://www\.facebook\.com/[^"/]+/\?ref=embed_post"[^>]*>\s*<img[^>]*src="([^"]+)"', html)
    allm = _lookaside(html)
    if avatar:
        allm = [u for u in allm if u != avatar.group(1)]
    return allm


def fb(url):
    """Facebook entry point: video first (poster-only for video posts), then photo."""
    got = fb_video(url)
    if got:
        return got
    return fb_photo(url)


# ------------------------------------------------------------------- X / twitter
X_ID = [r"(?:twitter|x)\.com/(?:[^/]+|i)/(?:status|statuses)/(\d{6,})",
        r"(?:twitter|x)\.com/i/web/status/(\d{6,})"]


def x_id(url):
    for p in X_ID:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


def x_media(url):
    sid = x_id(url)
    if not sid:
        return []
    out = []
    try:
        r = get("https://api.fxtwitter.com/i/status/%s" % sid,
                headers={"Accept": "application/json"})
        d = json.loads(r["text"])
        for m in (d.get("tweet", {}).get("media", {}) or {}).get("all", []) or []:
            if m.get("url"):
                out.append(m["url"])
    except Exception:
        pass
    if not out:
        try:
            r = get("https://api.vxtwitter.com/i/status/%s" % sid,
                    headers={"Accept": "application/json"})
            d = json.loads(r["text"])
            out = list(d.get("mediaURLs") or [])
        except Exception:
            pass
    return out


# ---------------------------------------------------------------- tiktok
def tiktok(url):
    r = get("https://www.tikwm.com/api/?url=%s&hd=1" % urllib.parse.quote(url, safe=""))
    d = json.loads(r["text"])
    data = d.get("data") or {}
    out = []
    for k in ("hdplay", "play"):
        if data.get(k):
            out.append(data[k])
            break
    if not out:
        out = list(data.get("images") or [])
    return out


# ---------------------------------------------------------------- mastodon
MASTODON = [r"^https?://([^/]+)/(?:@[^/]+|users/[^/]+)/statuses?/(\d+)$",
            r"^https?://([^/]+)/@[^/]+/(\d+)$",
            r"^https?://([^/]+)/web/statuses/(\d+)$"]


def mastodon(url):
    for p in MASTODON:
        m = re.match(p, url.split("?")[0].rstrip("/"))
        if m:
            inst, sid = m.group(1), m.group(2)
            r = get("https://%s/api/v1/statuses/%s" % (inst, sid))
            d = json.loads(r["text"])
            if not d.get("media_attachments") and d.get("reblog"):
                d = d["reblog"]
            return [a["url"] for a in (d.get("media_attachments") or []) if a.get("url")]
    return []


# ---------------------------------------------------------------- bluesky
BSKY = [r"^https?://(?:www\.)?bsky\.app/profile/([^/]+)/post/([A-Za-z0-9]+)"]


def bluesky(url):
    m = None
    for p in BSKY:
        m = re.match(p, url)
        if m:
            break
    if not m:
        return []
    actor, rkey = m.group(1), m.group(2)
    r = get("https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread"
            "?uri=%s" % urllib.parse.quote("at://%s/app.bsky.feed.post/%s" % (actor, rkey), safe=""))
    d = json.loads(r["text"])
    post = ((d.get("thread") or {}).get("post") or {})
    emb = post.get("embed") or {}
    out = []
    for img in emb.get("images") or []:
        if img.get("fullsize"):
            # the CDN serves webp by default; the Shortcuts save action wants a
            # real JPEG, so ask for one explicitly (same trick the shortcut uses)
            out.append(img["fullsize"] + "@jpeg")
    if not out and isinstance(emb.get("media"), dict):
        out = [i["fullsize"] + "@jpeg" for i in emb["media"].get("images", []) if i.get("fullsize")]
    if not out:
        # video: original MP4 blob (HLS is not savable in Shortcuts)
        ref = (((post.get("record") or {}).get("embed") or {}).get("video") or {}).get("ref") or {}
        cid = ref.get("$link")
        did = post.get("author", {}).get("did")
        if cid and did:
            out.append("https://bsky.social/xrpc/com.atproto.sync.getBlob?did=%s&cid=%s" % (did, cid))
    return out


# ---------------------------------------------------------------- pinterest
def pinterest(url):
    """Pin: widgets/pidgets JSON -> V_720P mp4 for video, 564x for image."""
    m = re.search(r"pinterest\.[a-z.]+/pin/(\d+)", url) or re.search(r"pin\.it/([A-Za-z0-9]+)", url)
    if not m:
        return []
    pid = m.group(1)
    if not pid.isdigit():  # pin.it short link -> follow to canonical pin
        r = get(url, ua=MOBILE_UA)
        m2 = re.search(r"/pin/(\d+)", r["url"])
        if not m2:
            return []
        pid = m2.group(1)
    r = get("https://widgets.pinterest.com/v3/pidgets/pins/info/?pin_ids=%s" % pid)
    d = json.loads(r["text"])
    for pin in (d.get("data") or []):
        vl = ((pin.get("videos") or {}).get("video_list") or {})
        for q in ("V_720P", "V_540P", "V_480P"):
            if (vl.get(q) or {}).get("url"):
                return [vl[q]["url"]]
        imgs = pin.get("images") or {}
        for q in ("orig", "564x", "237x"):
            if (imgs.get(q) or {}).get("url"):
                return [imgs[q]["url"]]
    return []


RECIPES = {
    "fb": ("Facebook", fb),
    "x": ("X / Twitter", x_media),
    "tiktok": ("TikTok", tiktok),
    "mastodon": ("Mastodon", mastodon),
    "bluesky": ("Bluesky", bluesky),
    "pinterest": ("Pinterest", pinterest),
}

# (recipe, label, url, required)
CASES = [
    ("fb", "reel", "https://www.facebook.com/reel/815233250817277", True),
    ("fb", "reel#2", "https://www.facebook.com/reel/1295440819226974", False),
    ("fb", "video watch/?v=", "https://www.facebook.com/watch/?v=815233250817277", False),
    ("fb", "photo?fbid=", "https://www.facebook.com/photo?fbid=1426466698848702", True),
    ("fb", "photo.php?fbid=", "https://www.facebook.com/photo.php?fbid=1426466698848702", True),
    ("fb", "post permalink", "https://www.facebook.com/NASA/posts/1426466738848698/", False),
    ("x", "tweet video", "https://x.com/NASA/status/1732824684683784516", True),
    ("x", "tweet photo", "https://x.com/wexler/status/501860042338213889", False),
    ("x", "tweet gif", "https://x.com/MushirMickeyJoe/status/2009384131864437082", False),
    ("x", "4-photo tweet", "https://x.com/NetflixKR/status/2066672100316778953", False),
    ("x", "no media", "https://x.com/dril/status/205052027259195393", False),
    ("tiktok", "tiktok video", "https://www.tiktok.com/@scout2015/video/6718335390845095173", True),
    ("mastodon", "mastodon video", "https://mastodon.social/@mastodon/117303445557305921", True),
    ("bluesky", "bluesky photos", "https://bsky.app/profile/jay.bsky.team/post/3mvvdpby3x22t", True),
    ("bluesky", "bluesky video", "https://bsky.app/profile/jay.bsky.team/post/3mvorbgjaks24", True),
    ("bluesky", "bluesky handle-as-did", "https://bsky.app/profile/bsky.app/post/3mv3shqdfuc2e", False),
    ("pinterest", "pin (image)", "https://www.pinterest.com/pin/93660867247422713/", True),
]


def check_regexes(plist_path):
    """Assert the patterns actually stored in the shortcut match real URL forms
    and reject lookalike hosts. These are the exact strings the Match Text
    actions run on userLink."""
    pats = []
    for a in plistlib.load(open(plist_path, "rb"))["WFWorkflowActions"]:
        p = (a.get("WFWorkflowActionParameters") or {}).get("WFMatchTextPattern")
        if isinstance(p, str) and p not in pats:
            pats.append(p)

    def one(marker):
        hit = [p for p in pats if marker in p]
        assert hit, "no pattern containing %r" % marker
        return hit[0]

    xp = one("twitter|x")
    pinp = one("pinterest")
    bskyp = one("bsky")
    fbid = one("reels?")
    fbphoto = one("_1p6f")
    mast = one("users/")

    cases = [
        ("X plain", xp, "https://x.com/NASA/status/1732824684683784516", True),
        ("X photo tab", xp, "https://twitter.com/u/status/123456789/photo/1", True),
        ("X i/status", xp, "https://x.com/i/status/123456789", True),
        ("X mobile", xp, "https://mobile.twitter.com/u/status/123456789", True),
        ("X own api REJECT", xp, "https://api.fxtwitter.com/i/status/123456789", False),
        ("X lookalike host REJECT", xp, "https://netflix.com/user/status/123456789", False),
        ("pin", pinp, "https://www.pinterest.com/pin/93660867247422713/", True),
        ("pin ccTLD", pinp, "https://pinterest.co.uk/pin/93660867247422713/", True),
        ("pin lookalike REJECT", pinp, "https://mypinterest.com/pin/93660867247422713/", False),
        ("bsky handle", bskyp, "https://bsky.app/profile/jay.bsky.team/post/3mvvdpby3x22t", True),
        ("bsky did", bskyp, "https://bsky.app/profile/did:plc:abc/post/3mvvdpby3x22t", True),
        ("bsky lookalike REJECT", bskyp, "https://notbsky.app/profile/x/post/3mvvdpby3x22t", False),
        ("fb reel", fbid, "https://www.facebook.com/reel/815233250817277", True),
        ("fb videos", fbid, "https://www.facebook.com/NASA/videos/815233250817277/", True),
        ("fb watch", fbid, "https://www.facebook.com/watch/?v=815233250817277", True),
        ("fb photo REJECT", fbid, "https://www.facebook.com/photo?fbid=1426466698848702", False),
        ("fb photo regex",
         fbphoto,
         '<a href="https://www.facebook.com/photo.php?fbid=1&amp;set=a.2&amp;ref=embed_post" '
         'target="_blank"><img class="_1p6f _1p6g img" src="https://lookaside.fbsbx.com/'
         'lookaside/crawler/media/?media_id=1426466698848702" alt="" style="max-width:552px"',
         True),
        ("fb poster thumb REJECT", fbphoto,
         '<img class="_1p6f _1p6g img" src="https://lookaside.fbsbx.com/lookaside/crawler/'
         'media/?media_id=815233250817277&amp;get_thumbnail=1"', False),
        ("mastodon @", mast, "https://mastodon.social/@mastodon/117303445557305921", True),
        ("mastodon @ with status", mast, "https://mastodon.social/@mastodon/statuses/117303445557305921", True),
        ("mastodon users", mast, "https://fosstodon.org/users/x/statuses/123456", True),
        ("mastodon web", mast, "https://mastodon.social/web/statuses/117303445557305921", True),
        ("mastodon short id REJECT", mast, "https://mastodon.social/@user/12345", False),
        ("threads REJECT", mast, "https://www.threads.net/@user/post/ABCdef123", False),
        ("tiktok REJECT", mast, "https://www.tiktok.com/@scout2015/video/6718335390845095173", False),
        ("tiktok trailing digits REJECT", mast, "https://www.tiktok.com/@user123456/video/6718335390845095173", False),
    ]
    fails = 0
    for label, pat, url, want in cases:
        got = bool(re.search(pat, url))
        if got != want:
            fails += 1
            print("REGEX FAIL %-26s want=%s got=%s  %s" % (label, want, got, url))
    print("regex matrix: %d cases, %d failures" % (len(cases), fails))
    return fails


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma separated recipe keys")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--regexes", action="store_true",
                    help="only run the offline regex matrix")
    a = ap.parse_args()
    if a.list:
        for k, (n, _) in RECIPES.items():
            print(k, "=", n)
        return 0
    plist = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "shortcut", "fed.unsigned.plist")
    if a.regexes:
        return 1 if check_regexes(plist) else 0
    only = set(a.only.split(",")) if a.only else None
    fails, req_fails = 0, 0
    for key, label, url, required in CASES:
        if only and key not in only:
            continue
        name, fn = RECIPES[key]
        try:
            got = fn(url)
        except Exception as e:  # noqa: BLE001
            print("ERROR  %-8s %-16s %s: %s" % (key, label, name, e))
            got = []
        if not got:
            mark = "FAIL " if required else "skip "
            print("%s %-8s %-16s %s" % (mark, key, label, url))
            if required:
                req_fails += 1
            continue
        ml = got[0]
        detail = ""
        if not a.no_download:
            try:
                h = head(ml, ua=CRAWLER_UA if "fbsbx" in ml else None)
                detail = "%s %s bytes-range=%s" % (h["status"], h["ct"], h["len"])
                if h["status"] not in (200, 206) or h["len"] < 1024:
                    raise RuntimeError("bad media fetch")
            except Exception as e:  # noqa: BLE001
                print("FAIL  %-8s %-16s media fetch: %s (%s)" % (key, label, e, ml[:90]))
                fails += 1
                continue
        print("PASS  %-8s %-16s n=%d  %s  <- %s" % (key, label, len(got), detail, ml[:110]))
    print("\nrequired failures: %d   other failures: %d" % (req_fails, fails))
    rx = check_regexes(plist)
    return 1 if (req_fails or fails or rx) else 0


if __name__ == "__main__":
    sys.exit(main())
