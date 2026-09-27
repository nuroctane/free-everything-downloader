#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build FREE Media Downloader 1.6 from 1.4.

Adds direct, single-request fast paths ahead of the server-side aggregator:

  Facebook   video/Reel -> /video/embed hd_src|sd_src      (~0.4 s, no polling)
  Facebook   photo/multi -> /plugins/post.php lookaside     (~0.5 s, no polling)
  X          post        -> api.fxtwitter.com media.all[].url
  Mastodon   post        -> <instance>/api/v1/statuses/<id>
  Bluesky    post        -> public.api.bsky.app getPostThread (+ getBlob for video)
  Pinterest  pin         -> widgets.pinterest.com v3/pidgets pins/info
  Threads    public post -> crawler-rendered media JSON (video/image)

and tunes the aggregator fallback: 1 s poll cadence, 60 s ceiling, and an
honest failure message instead of a raw JSON dump.

The template `Settings.shortcut.version` (9.0.0) is the aggregator's client
gate and MUST NOT change; only the user-facing `Settings.version` moves to 1.6.

    python -X utf8 scripts/build_v15.py [--check] [--out FILE]
"""
import argparse
import os
import plistlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf import (Graph, tstr, var, out, coerce, COND_CONTAINS, COND_HAS_VALUE,  # noqa: E402
                dict_field)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "shortcut", "fed.unsigned.plist")

CRAWLER_UA = "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"

VERSION = "1.6"
VERSION_DATE = "2026-09-26"

# --- regexes (all verified live by scripts/test_extractors.py) --------------
# One capture group, no optional slash inside an alternation. Shortcuts Match
# Text is ICU, and the old reels?/ form matched in Python but captured nothing
# on /reel/ and /videos/ in ICU — so the Reel fast path never ran.
FB_VIDEO_ID = r"(?:(?:reel|reels|videos|video)/|[?&]v=|video\.php\?v=)(\d{6,})"
FB_EMBED_SRC = (r'"(?:hd_src|sd_src|browser_native_hd_url'
                r'|browser_native_sd_url|playable_url)":"([^"]+)"')
FB_PHOTO = (r'(?:class="_1p6f[^"]*"[^>]*src'
            r'|photo\.php\?fbid=\d+[^"]*"[^>]*>\s*<img[^>]*src)'
            r'="(https://lookaside\.fbsbx\.com/lookaside/crawler/media/\?media_id=\d+)"')
X_ID = (r'(?:^|//)(?:www\.|mobile\.|m\.)?(?:twitter|x)\.com/'
        r'(?:[^/\s]+|i)/(?:status|statuses)/(\d{6,})')
MASTODON = (r"https?://([^/\s]+)/(?:@[^/\s]+|users/[^/\s]+|web)"
            r"(?:/status(?:es)?)?/(\d{6,})")
BSKY = r"(?:^|//)bsky\.app/profile/([^/\s]+)/post/([A-Za-z0-9]+)"
PIN = r"(?:^|//)(?:[a-z0-9-]+\.)*pinterest\.[a-z.]{2,6}/pin/(\d+)"
THREADS_ID = (r"(?:^|//)(?:www\.)?threads\.(?:net|com)/"
             r"(?:@[^/\s]+/post/|t/)([A-Za-z0-9_-]+)")
THREADS_UA = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"

NEW_COMMENT = """FREE Media Downloader
Version {v}  ({d})
RoutineHub 26384. If the listing is newer than this number, update from there.

Sites: YouTube, YouTube Music, TikTok, Instagram, Facebook, X, Threads, Bluesky, Mastodon, Reddit, Pinterest, LinkedIn, Snapchat, Vimeo, DailyMotion, SoundCloud.

Facebook, Threads, X, Bluesky, Mastodon and Pinterest resolve on the phone - no waiting on a server job for public media.
Facebook videos and Reels come from the video player. Facebook photos come from the public post embed.
Threads public videos and images come from the post page. Private or login-gated posts open Threads or the default browser with a clear retry instruction.
YouTube and Instagram: yt-dlp in a-Shell mini. Video and photos go to Photos. Audio goes to Files.
TikTok: no-watermark when the source lets it.
The remaining sites use the server extractor, then the other free backends.
Share a link. Save the file. No key. No paywall. No upgrade nag.
First Photos, Files, and a-Shell prompts: approve once.
If a post is private, the shortcut opens Threads when installed, or your default browser. Sign in there, then share the post again.""".format(v=VERSION, d=VERSION_DATE)


def json_pairs(pairs):
    """WFDictionaryFieldValue used by WFJSONValues (kept for completeness)."""
    return dict_field(pairs)


# ---------------------------------------------------------- share-sheet input
def patch_input_normalization(acts):
    """Normalize URL input from Safari, Brave, and other browser share sheets.

    Browser extensions do not all send the same Shortcuts content item. Safari
    and browsers that advertise a webpage hand over a ``Safari Web Page``
    object; other browsers send a URL, text, or rich text containing one or
    more URLs. The old graph passed the complete URL list straight into
    ``Expand URL``. That is fragile when a webpage contains several links and
    can leave yt-dlp with a list/object instead of one URL.

    Prefer the page's canonical URL for webpage inputs. For every other input,
    extract URLs and keep the first one. Expansion then runs on that scalar,
    and an empty share item gets a useful message instead of falling through
    to the server extractor with an empty link.
    """
    idx = None
    for i, a in enumerate(acts):
        if a.get("WFWorkflowActionIdentifier") != "is.workflow.actions.detect.link":
            continue
        if i + 2 >= len(acts):
            continue
        if (acts[i + 1].get("WFWorkflowActionIdentifier") == "is.workflow.actions.url.expand"
                and acts[i + 2].get("WFWorkflowActionIdentifier") == "is.workflow.actions.setvariable"
                and (acts[i + 2].get("WFWorkflowActionParameters") or {}).get("WFVariableName") == "userLink"):
            idx = i
            break
    if idx is None:
        raise SystemExit("share-sheet input normalization block not found")

    g = Graph()
    extension_input = tstr({"Type": "ExtensionInput"})

    input_type = g.get_type(extension_input, name="Input Type")
    g.if_(COND_CONTAINS, out(input_type), "Safari Web")
    page_url = g.safari_page_property("Page URL", extension_input, name="Browser Page URL")
    page_url_first = g.get_item_first(out(page_url), name="Shared URL")
    g.setvar("rawLink", out(page_url_first))
    g.else_()
    urls = g.detect_links(extension_input, name="Detected URLs")
    shared_url = g.get_item_first(out(urls), name="Shared URL")
    g.setvar("rawLink", out(shared_url))
    g.endif()

    # Some browser extensions advertise a webpage item but leave its page URL
    # property empty. Fall back to the same link extractor used for URL/text
    # shares before declaring the share invalid.
    g.if_(COND_HAS_VALUE, var("rawLink"))
    g.else_()
    fallback_text = g.text_from_input(extension_input, name="Shared Text")
    fallback_urls = g.detect_links(out(fallback_text), name="Fallback URLs")
    fallback_url = g.get_item_first(out(fallback_urls), name="Fallback URL")
    g.setvar("rawLink", out(fallback_url))
    g.endif()

    g.if_(COND_HAS_VALUE, var("rawLink"))
    # URL fields are text-token fields in the Shortcuts plist; wrap the scalar
    # variable the same way the editor serializes an action-output URL.
    expanded = g.expand_url(tstr({"Type": "Variable", "VariableName": "rawLink"}),
                            name="Expanded URL")
    g.if_(COND_HAS_VALUE, out(expanded))
    g.setvar("userLink", out(expanded))
    g.else_()
    g.setvar("userLink", var("rawLink"))
    g.endif()
    g.else_()
    g.notify("No link was received from the share sheet. Copy the page URL and share it again.")
    g.stop()
    g.endif()

    g.close()
    assert not g._stack, "input normalization control flow is unbalanced"
    acts[idx:idx + 3] = [a.d for a in g.actions]
    return True


# --------------------------------------------------------------- facebook
def facebook(g):
    g.comment("Facebook: video and Reels come straight from the video player; "
              "photos come from the public post embed. One request each, no server job, "
              "no sign-in. Anything that misses falls through to the extractor below.")
    g.if_(COND_CONTAINS, var("userLink"), "facebook.com")

    # -- video / reel --------------------------------------------------------
    vid = g.match(FB_VIDEO_ID, var("userLink"), name="FacebookVideoID")
    g.if_(COND_HAS_VALUE, out(vid))
    vnum = g.group(1, out(vid), "FacebookVideoNumber")
    embed = g.download(tstr("https://www.facebook.com/video/embed?video_id=", out(vnum)),
                       method="GET",
                       headers=[("User-Agent", CRAWLER_UA)],
                       name="FacebookPlayer")
    src = g.match(FB_EMBED_SRC, out(embed), name="FacebookMediaURL")
    g.if_(COND_HAS_VALUE, out(src))
    g2 = g.group(1, out(src), "FacebookMediaGroup")
    fixed = g.replace("\\/", "/", out(g2), regex=False, name="FacebookMediaLink")
    # some player payloads escape the slashes as \u002F instead of \/
    fixed2 = g.replace(r"\u002F", "/", out(fixed), regex=False,
                       name="FacebookMediaLink2")
    media = g.download(out(fixed2), name="FacebookVideo")
    g.save_camera_roll()
    g.notify("Saved from Facebook.")
    g.stop()
    g.endif()
    g.endif()

    # -- photo / multi-photo -------------------------------------------------
    enc = g.urlencode(var("userLink"))
    html = g.download(tstr("https://www.facebook.com/plugins/post.php?href=", out(enc)),
                      method="GET",
                      headers=[("User-Agent", CRAWLER_UA)],
                      name="FacebookEmbed")
    ph = g.match(FB_PHOTO, out(html), name="FacebookPhotos")
    g.if_(COND_HAS_VALUE, out(ph))
    g.repeat_each(out(ph))
    pg = g.group(1, var("Repeat Item"), "FacebookPhotoURL")
    pamp = g.replace("&amp;", "&", out(pg), regex=False, name="FacebookPhotoLink")
    pimg = g.download(out(pamp), method="GET",
                      headers=[("User-Agent", CRAWLER_UA)], name="FacebookPhoto")
    g.save_camera_roll()
    g.endrepeat()
    g.notify("Saved from Facebook.")
    g.stop()
    g.endif()

    g.endif()
    return g


# ------------------------------------------------------------------- Threads
def threads(g):
    """Resolve public Threads posts from Meta's crawler-rendered page data."""
    g.comment(
        "Threads: public posts use crawler-rendered page data and signed CDN "
        "URLs. Private or login-gated posts open Threads or the default browser."
    )
    m = g.match(THREADS_ID, var("userLink"), name="ThreadsPostID")
    g.if_(COND_HAS_VALUE, out(m))
    tid = g.group(1, out(m), "ThreadsPostCode")
    page = g.download(
        var("userLink"), method="GET",
        headers=[("User-Agent", THREADS_UA)], name="ThreadsPostPage"
    )

    # A post page embeds many post objects. Stop at the next code field so a
    # recommendation or reply cannot be mistaken for the shared post.
    video_pattern = tstr(
        r'"code":"', out(tid),
        r'"(?:(?!"code":).){0,50000}?"video_versions":\[\{(?:(?!"url":).){0,500}?"url":"'
        r'(https:[^"]+?\.mp4(?:\?[^"]*)?)"'
    )
    videos = g.match(video_pattern, out(page), name="ThreadsVideoURLs")
    g.if_(COND_HAS_VALUE, out(videos))
    g.repeat_each(out(videos))
    vu = g.group(1, var("Repeat Item"), "ThreadsVideoURL")
    vu1 = g.replace(r"\/", "/", out(vu), regex=False, name="ThreadsVideoURLSlashes")
    vu2 = g.replace(r"\u002F", "/", out(vu1), regex=False, name="ThreadsVideoURLUnicodeSlashes")
    vu3 = g.replace(r"\u0026", "&", out(vu2), regex=False, name="ThreadsVideoURLAmpersands")
    vu4 = g.replace(r"\u003D", "=", out(vu3), regex=False, name="ThreadsVideoURLEquals")
    vu5 = g.replace(r"\u0025", "%", out(vu4), regex=False, name="ThreadsVideoURLPercent")
    g.download(out(vu5), headers=[("Referer", "https://www.threads.com/")], name="ThreadsVideo")
    g.save_camera_roll()
    g.endrepeat()
    g.notify("Saved from Threads.")
    g.stop()
    g.else_()

    image_pattern = tstr(
        r'"code":"', out(tid),
        r'"(?:(?!"code":).){0,50000}?"image_versions2":\{"candidates":\['
        r'\{(?:(?!"url":).){0,500}?"url":"(https:[^"]+)"'
    )
    images = g.match(image_pattern, out(page), name="ThreadsImageURLs")
    g.if_(COND_HAS_VALUE, out(images))
    g.repeat_each(out(images))
    iu = g.group(1, var("Repeat Item"), "ThreadsImageURL")
    iu1 = g.replace(r"\/", "/", out(iu), regex=False, name="ThreadsImageURLSlashes")
    iu2 = g.replace(r"\u002F", "/", out(iu1), regex=False, name="ThreadsImageURLUnicodeSlashes")
    iu3 = g.replace(r"\u0026", "&", out(iu2), regex=False, name="ThreadsImageURLAmpersands")
    iu4 = g.replace(r"\u003D", "=", out(iu3), regex=False, name="ThreadsImageURLEquals")
    iu5 = g.replace(r"\u0025", "%", out(iu4), regex=False, name="ThreadsImageURLPercent")
    g.download(out(iu5), headers=[("Referer", "https://www.threads.com/")], name="ThreadsImage")
    g.save_camera_roll()
    g.endrepeat()
    g.notify("Saved from Threads.")
    g.stop()
    g.else_()

    # Universal links route to the Threads app when installed, otherwise to
    # the user's default browser. Safari is never assumed.
    g.notify(
        "Threads hid this post from public download. Opening Threads or your "
        "default browser. Sign in if asked, then share the post again."
    )
    g.open_url(var("userLink", [coerce("WFURLContentItem")]))
    g.wait_to_return()
    g.notify("Share the visible Threads post to FREE Media Downloader again.")
    g.stop()
    g.endif()
    g.endif()
    g.endif()
    return g


# ---------------------------------------------------------------------- X
def x_branch(g):
    g.comment("X: one fxtwitter request. Covers video, GIF and every photo, "
              "including 4-photo posts. No headers needed on the CDN.")
    m = g.match(X_ID, var("userLink"), name="XStatusID")
    g.if_(COND_HAS_VALUE, out(m))
    xid = g.group(1, out(m), "XStatusNumber")
    fx = g.download(tstr("https://api.fxtwitter.com/i/status/", out(xid)),
                    method="GET", headers=[("Accept", "application/json")],
                    name="XPost")
    media = g.getval("media", out(fx), name="XMedia")
    g.if_(COND_HAS_VALUE, out(media))
    allm = g.getval("all", out(media), name="XMediaItems")
    g.save_media_list(out(allm), url_key="url", notify_text="Saved from X.")
    g.endif()
    g.endif()
    return g


# ----------------------------------------------------------------- mastodon
def mastodon(g):
    g.comment("Mastodon: the instance's own public API. Photos, video and boosts.")
    m = g.match(MASTODON, var("userLink"), name="MastodonStatus")
    g.if_(COND_HAS_VALUE, out(m))
    inst = g.group(1, out(m), "MastodonInstance")
    sid = g.group(2, out(m), "MastodonStatusID")
    api = g.download(tstr("https://", out(inst), "/api/v1/statuses/", out(sid)),
                     method="GET", name="MastodonPost")
    m1 = g.getval("media_attachments", out(api), name="MastodonMedia")
    g.if_(COND_HAS_VALUE, out(m1))
    g.setvar("fedMedia", out(m1))
    g.else_()
    rb = g.getval("reblog", out(api), name="MastodonReblog")
    m2 = g.getval("media_attachments", out(rb), name="MastodonReblogMedia")
    g.setvar("fedMedia", out(m2))
    g.endif()
    g.if_(COND_HAS_VALUE, var("fedMedia"))
    g.save_media_list(var("fedMedia"), url_key="url", type_key="type",
                      notify_text="Saved from Mastodon.")
    g.endif()
    g.endif()
    return g


# ------------------------------------------------------------------ bluesky
def bluesky(g):
    g.comment("Bluesky: public getPostThread. Photos are pulled as JPEG off the image "
              "CDN; video is pulled as the original MP4 blob (the CDN only serves HLS).")
    m = g.match(BSKY, var("userLink"), name="BlueskyPost")
    g.if_(COND_HAS_VALUE, out(m))
    actor = g.group(1, out(m), "BlueskyActor")
    rkey = g.group(2, out(m), "BlueskyRecord")
    at = g.text("at://", out(actor), "/app.bsky.feed.post/", out(rkey), name="BlueskyURI")
    enc = g.urlencode(out(at))
    js = g.download(tstr("https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=",
                         out(enc)), method="GET", name="BlueskyThread")
    thread = g.getval("thread", out(js), name="BlueskyThreadPost")
    post = g.getval("post", out(thread), name="BlueskyPostBody")
    embed = g.getval("embed", out(post), name="BlueskyEmbed")

    imgs = g.getval("images", out(embed), name="BlueskyImages")
    g.if_(COND_HAS_VALUE, out(imgs))
    g.save_media_list(out(imgs), url_key="fullsize", notify_text="Saved from Bluesky.",
                      suffix="@jpeg")
    g.endif()

    mobj = g.getval("media", out(embed), name="BlueskyMediaObject")
    imgs2 = g.getval("images", out(mobj), name="BlueskyMediaImages")
    g.if_(COND_HAS_VALUE, out(imgs2))
    g.save_media_list(out(imgs2), url_key="fullsize", notify_text="Saved from Bluesky.",
                      suffix="@jpeg")
    g.endif()

    rec = g.getval("record", out(post), name="BlueskyRecordBody")
    remb = g.getval("embed", out(rec), name="BlueskyRecordEmbed")
    vid = g.getval("video", out(remb), name="BlueskyVideo")
    ref = g.getval("ref", out(vid), name="BlueskyVideoRef")
    cid = g.getval("$link", out(ref), name="BlueskyVideoCID")
    author = g.getval("author", out(post), name="BlueskyAuthor")
    did = g.getval("did", out(author), name="BlueskyDID")
    g.if_(COND_HAS_VALUE, out(cid))
    blob = g.download(tstr("https://bsky.social/xrpc/com.atproto.sync.getBlob?did=",
                           out(did), "&cid=", out(cid)), method="GET",
                      name="BlueskyVideoFile")
    g.download(out(blob), name="BlueskyVideoMedia")
    g.save_camera_roll()
    g.notify("Saved from Bluesky.")
    g.stop()
    g.endif()
    g.endif()
    return g


# ---------------------------------------------------------------- pinterest
def pinterest(g):
    g.comment("Pinterest: the public pin widget returns the media URLs directly. "
              "Most pins are images; story pins expose a plain 720p mp4.")
    m = g.match(PIN, var("userLink"), name="PinterestPin")
    g.if_(COND_HAS_VALUE, out(m))
    pid = g.group(1, out(m), "PinterestPinID")
    js = g.download(tstr("https://widgets.pinterest.com/v3/pidgets/pins/info/?pin_ids=",
                         out(pid)), method="GET", name="PinterestWidget")
    data = g.getval("data", out(js), name="PinterestPins")
    g.if_(COND_HAS_VALUE, out(data))
    g.repeat_each(out(data))
    vids = g.getval("videos", var("Repeat Item"), name="PinterestVideos")
    g.if_(COND_HAS_VALUE, out(vids))
    vl = g.getval("video_list", out(vids), name="PinterestVideoList")
    q = g.getval("V_720P", out(vl), name="PinterestQuality")
    u = g.getval("url", out(q), name="PinterestVideoURL")
    g.if_(COND_HAS_VALUE, out(u))
    g.download(out(u), name="PinterestVideo")
    g.save_camera_roll()
    g.notify("Saved from Pinterest.")
    g.stop()
    g.endif()
    g.endif()
    imgs = g.getval("images", var("Repeat Item"), name="PinterestImages")
    qz = g.getval("564x", out(imgs), name="PinterestImageSize")
    uz = g.getval("url", out(qz), name="PinterestImageURL")
    g.if_(COND_HAS_VALUE, out(uz))
    g.download(out(uz), name="PinterestImage")
    g.save_camera_roll()
    g.notify("Saved from Pinterest.")
    g.stop()
    g.endif()
    g.endrepeat()
    g.endif()
    g.endif()
    return g


def build():
    g = Graph()
    facebook(g)
    threads(g)
    x_branch(g)
    mastodon(g)
    bluesky(g)
    pinterest(g)
    g.close()
    assert not g._stack, "unbalanced control flow"
    return [a.d for a in g.actions]


# --------------------------------------------------------------- plist surgery
def find_aggregator(acts):
    for i, a in enumerate(acts):
        if a.get("WFWorkflowActionIdentifier") != "is.workflow.actions.downloadurl":
            continue
        p = a.get("WFWorkflowActionParameters") or {}
        if p.get("WFHTTPMethod") == "POST" and "WFJSONValues" in p:
            return i
    raise SystemExit("aggregator POST action not found")


def token_text(v):
    """Best-effort text of a WFTextTokenString / plain string value."""
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        inner = v.get("Value")
        if isinstance(inner, dict) and "string" in inner:
            return inner["string"]
    return None


def set_token_text(v, new):
    if isinstance(v, str):
        return new
    if isinstance(v, dict) and isinstance(v.get("Value"), dict):
        v["Value"]["string"] = new
        return v
    raise SystemExit("cannot set text on %r" % (v,))


def dict_items(container):
    """Yield (key, item) for a WFDictionaryFieldValue wrapper."""
    items = container.get("Value", {}).get("WFDictionaryFieldValueItems", [])
    for it in items:
        yield token_text(it.get("WFKey")), it


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


def find_item(items, key):
    for it in items:
        if token_text(it.get("WFKey")) == key:
            return it
    return None


def settings_dict(acts):
    for a in acts:
        if a.get("WFWorkflowActionIdentifier") != "is.workflow.actions.dictionary":
            continue
        p = a.get("WFWorkflowActionParameters") or {}
        if p.get("CustomOutputName") == "Settings":
            return p
    raise SystemExit("Settings dictionary not found")


def patch_settings(acts):
    """Settings.version is the user-facing label; Settings.shortcut.version is
    the aggregator's client gate and must stay 9.0.0."""
    p = settings_dict(acts)
    items = p["WFItems"]["Value"]["WFDictionaryFieldValueItems"]
    it = find_item(items, "version")
    if it is None:
        raise SystemExit("Settings.version not found")
    it["WFValue"] = set_token_text(it["WFValue"], VERSION)

    sc = find_item(items, "shortcut")
    if sc is None:
        raise SystemExit("Settings.shortcut not found")
    sub = sub_items(sc)
    gv = find_item(sub, "version")
    if gv is None:
        raise SystemExit("Settings.shortcut.version not found")
    cur = token_text(gv["WFValue"])
    if cur != "9.0.0":
        raise SystemExit("unexpected aggregator gate %r" % cur)
    nm = find_item(sub, "name")
    if nm is not None:
        nm["WFValue"] = set_token_text(nm["WFValue"], "FREE Media Downloader")


def patch_comment(acts):
    a = acts[0]
    if a.get("WFWorkflowActionIdentifier") != "is.workflow.actions.comment":
        raise SystemExit("first action is not the version comment")
    p = a["WFWorkflowActionParameters"]
    p["WFCommentActionText"] = set_token_text(p.get("WFCommentActionText"), NEW_COMMENT)


def patch_poll(acts):
    changed = {"delay": False, "number": False}
    for a in acts:
        ident = a.get("WFWorkflowActionIdentifier")
        p = a.get("WFWorkflowActionParameters") or {}
        if ident == "is.workflow.actions.delay" and str(p.get("WFDelayTime")) == "3.0":
            # must stay a NUMBER: iOS blanks a string in this field, which leaves
            # the Wait action with an empty (prompting) duration
            p["WFDelayTime"] = 1.0
            changed["delay"] = True
        if ident == "is.workflow.actions.number" and str(p.get("WFNumberActionNumber")) == "500":
            p["WFNumberActionNumber"] = "60"
            changed["number"] = True
    return changed


def patch_failure_notice(acts):
    """Replace the raw `{Response}` dump with a message a human can act on.

    The notice is emitted when the aggregator reports status "failed".
    """
    for a in acts:
        if a.get("WFWorkflowActionIdentifier") != "is.workflow.actions.notification":
            continue
        p = a.get("WFWorkflowActionParameters") or {}
        body = p.get("WFNotificationActionBody")
        inner = body.get("Value", {}) if isinstance(body, dict) else {}
        atts = inner.get("attachmentsByRange") or {}
        if any(att.get("VariableName") == "Response" for att in atts.values()):
            p["WFNotificationActionBody"] = tstr(
                "Couldn't grab a file from that link. If the post is private or "
                "age-restricted, sign in and share it again.")
            return True
    return False


def patch_signin_copy(acts):
    """Make the shared sign-in branch describe universal-link routing.

    The 1.4 base already opens ``userLink`` and waits for it to return. Its
    copy said Safari, which is misleading when iOS hands the URL to an
    installed native app or another default browser.
    """
    replacements = {
        "Session needed: open the post in Safari or the native app. Sign in. Come back. Share the post again.":
            "Session needed: opening the post in its app or your default browser. Sign in there, then share the post again.",
        "This post wants a sign-in. Opening it now. Sign in, then share it again.":
            "This post wants a sign-in. Opening the post in its app or your default browser now. Sign in there, then share it again.",
    }
    changed = False
    for a in acts:
        p = a.get("WFWorkflowActionParameters") or {}
        if a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.comment":
            old = p.get("WFCommentActionText")
            old_text = token_text(old)
            if old_text in replacements:
                p["WFCommentActionText"] = set_token_text(old, replacements[old_text])
                changed = True
        elif a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.notification":
            old = p.get("WFNotificationActionBody")
            old_text = token_text(old)
            if old_text in replacements:
                p["WFNotificationActionBody"] = set_token_text(old, replacements[old_text])
                changed = True
    return changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="write here instead of overwriting the source")
    ap.add_argument("--check", action="store_true",
                    help="report whether the build is already applied")
    a = ap.parse_args()

    data = open(SRC, "rb").read()
    p = plistlib.loads(data)
    acts = p["WFWorkflowActions"]
    blob = str(acts)

    applied = "ThreadsPostPage" in blob
    if a.check:
        print("actions:", len(acts), "| v1.6 fast paths present:", applied)
        return 0
    if applied:
        raise SystemExit("refusing to build twice: fast paths already in the plist")

    before = len(acts)
    patch_input_normalization(acts)
    idx = find_aggregator(acts)
    new = build()
    acts[idx:idx] = new
    patch_settings(acts)
    patch_comment(acts)
    changed = patch_poll(acts)
    notice = patch_failure_notice(acts)
    signin = patch_signin_copy(acts)
    assert changed["delay"] and changed["number"], "poll cadence not found"
    assert notice, "failure notice not found"
    assert signin, "sign-in copy not found"

    out_path = a.out or SRC
    tmp = out_path + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(p, fh, fmt=plistlib.FMT_XML)
    # never leave a half-written plist behind: serialize, verify, then swap
    with open(tmp, "rb") as fh:
        check = plistlib.load(fh)
    assert len(check["WFWorkflowActions"]) == len(acts), "round-trip lost actions"
    os.replace(tmp, out_path)
    print("inserted %d actions at index %d (%d -> %d)" % (len(new), idx, before, len(acts)))
    print("poll: 1.0s x60 | failure notice: rewritten | version: %s" % VERSION)
    print("wrote %s (%d bytes)" % (out_path, os.path.getsize(out_path)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
