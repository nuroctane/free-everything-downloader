#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Threads and Facebook, inside 1.5.1's Facebook section only.

1.5.1's `If userLink contains "facebook.com"` section is the one place X and
Instagram never enter; everything here runs only there. The prelude handles
links that come back as facebook.com/unsupportedbrowser (what Meta returns to
clients without a user-agent). Measured later: the phone's Expand URL does
send a user-agent, so on the phone Facebook /share/ links arrive as
/reel/<id>/ for the repaired Facebook steps and Threads links stay intact and
download through the server extractor; the prelude is a safety net. This code
is in the confirmed, locked baseline (tests/fixtures/good-1.7.plist) and is
not re-run by build_release.py.

Every step is stored the way the Shortcuts app stores it (see wf.native_*):
1.5.1's generated Facebook steps kept their inputs under keys iOS ignores
(Match Text "WFInput" instead of "text", Get Group "WFInput" instead of
"matches", Save to Photo Album with no input and an empty album).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf import (Graph, tstr, var, out, COND_CONTAINS, COND_HAS_VALUE, raw,  # noqa: E402
                native_if, native_match, native_group, native_replace, native_get,
                native_save, native_url, native_notify)
import build_v15 as B  # noqa: E402

VIDEO_TAIL = (r'"(?:(?!"code":).){0,50000}?"video_versions":\[\{(?:(?!"url":).){0,500}?"url":"'
              r'(https:[^"]+?\.mp4(?:\?[^"]*)?)"')
IMAGE_TAIL = (r'"(?:(?!"code":).){0,50000}?"image_versions2":\{"candidates":\['
              r'\{(?:(?!"url":).){0,500}?"url":"(https:[^"]+)"')
UNESCAPE = ((r"\/", "/"), (r"/", "/"), (r"&", "&"), (r"=", "="), (r"%", "%"))
NO_MEDIA = ("No photo or video found in this Threads post. Text-only posts have nothing "
            "to save, and private accounts can't be downloaded.")


def threads_recipe(g):
    """Threads post page -> signed CDN media -> Photos. userLink is the post URL."""
    post = native_match(g, B.THREADS_ID, var("userLink"), name="ThreadsPostID")
    native_if(g, COND_HAS_VALUE, out(post))
    code = native_group(g, out(post), name="ThreadsPostCode")
    page = native_get(g, [var("userLink")], headers=[("User-Agent", B.THREADS_UA)],
                      name="ThreadsPostPage")
    for kind, tail in (("Video", VIDEO_TAIL), ("Image", IMAGE_TAIL)):
        found = native_match(g, tstr('"code":"', raw(out(code)), tail), out(page),
                             name="Threads%sURLs" % kind)
        native_if(g, COND_HAS_VALUE, out(found))
        g.repeat_each(out(found))
        link = native_group(g, var("Repeat Item"), name="Threads%sURL" % kind)
        for find, repl in UNESCAPE:
            link = native_replace(g, find, repl, out(link), name="Threads%sLink" % kind)
        media = native_get(g, [out(link)], headers=[("Referer", "https://www.threads.com/")],
                           name="Threads%s" % kind)
        native_save(g, out(media))
        g.endrepeat()
        native_notify(g, "Saved from Threads.")
        g.stop()
        g.else_()
    native_notify(g, NO_MEDIA)
    g.stop()
    g.endif()   # images
    g.endif()   # videos
    g.endif()   # post id


def prelude():
    """First steps inside 1.5.1's Facebook section."""
    urls = {"OutputName": "URLs", "OutputUUID": B.INPUT_BLOCK_1_6[0][
        "WFWorkflowActionParameters"]["UUID"], "Type": "ActionOutput"}
    g = Graph()
    g.comment("FMD+ Facebook and Threads share links: the phone turns them into "
              "facebook.com/unsupportedbrowser; use the link as shared.")
    native_if(g, COND_CONTAINS, var("userLink"), "unsupportedbrowser")
    links = g.text(urls, name="Shared Links")
    native_if(g, COND_CONTAINS, out(links), "threads.")
    shared = native_match(g, B.THREADS_LINK, out(links), name="Shared Threads Link")
    native_if(g, COND_HAS_VALUE, out(shared))
    thread_url = native_url(g, out(native_group(g, out(shared), name="Threads Link")))
    g.setvar("userLink", out(thread_url))
    threads_recipe(g)
    g.endif()   # shared threads link found
    g.else_()   # not Threads -> Facebook share link
    fb = native_match(g, B.FB_SHARE_LINK, out(links), name="Shared Facebook Link")
    native_if(g, COND_HAS_VALUE, out(fb))
    fb_link = native_group(g, out(fb), name="Facebook Link")
    fb_page = native_get(g, [out(fb_link)], headers=[("User-Agent", B.CRAWLER_UA)],
                         name="Facebook Share Page")
    fb_vid = native_match(g, B.FB_PAGE_VIDEO_ID, out(fb_page), name="Facebook Share Video")
    native_if(g, COND_HAS_VALUE, out(fb_vid))
    reel = native_url(g, "https://www.facebook.com/reel/",
                      out(native_group(g, out(fb_vid), name="Facebook Video Number")), "/")
    g.setvar("userLink", out(reel))
    g.endif()   # video id
    g.endif()   # facebook link
    g.endif()   # threads / facebook
    g.endif()   # unsupportedbrowser
    g.comment("FMD- Facebook and Threads share links")
    assert not g._stack, "facebook prelude is unbalanced"
    return [a.d for a in g.actions]


def section(acts):
    """(start, end) of 1.5.1's Facebook section: its If and matching End If."""
    start = next(i for i, a in enumerate(acts)
                 if a["WFWorkflowActionParameters"].get("WFConditionalActionString") == "facebook.com")
    gid = acts[start]["WFWorkflowActionParameters"]["GroupingIdentifier"]
    end = next(i for i in range(start + 1, len(acts))
               if acts[i]["WFWorkflowActionParameters"].get("GroupingIdentifier") == gid
               and acts[i]["WFWorkflowActionParameters"].get("WFControlFlowMode") == 2)
    return start, end


def nativize(acts):
    """Store 1.5.1's Facebook steps the way the Shortcuts app does.

    The section's own `If userLink contains "facebook.com"` is left untouched:
    X passes it. Everything converted here only runs for Facebook.
    """
    start, end = section(acts)
    changed, last_download = 0, None
    for i in range(start + 1, end):
        ident = acts[i]["WFWorkflowActionIdentifier"]
        p = acts[i]["WFWorkflowActionParameters"]
        if ident == "is.workflow.actions.text.match" and "WFInput" in p:
            p["text"] = tstr(raw(p.pop("WFInput")))
        elif ident == "is.workflow.actions.text.match.getgroup" and "WFInput" in p:
            p["matches"] = {"Value": raw(p.pop("WFInput")), "WFSerializationType": "WFTextTokenAttachment"}
        elif (ident in ("is.workflow.actions.text.replace", "is.workflow.actions.urlencode")
              and p.get("WFInput", {}).get("WFSerializationType") == "WFTextTokenAttachment"):
            p["WFInput"] = tstr(raw(p["WFInput"]))
        elif ident == "is.workflow.actions.downloadurl":
            last_download = p["UUID"]
            if p.get("WFURL", {}).get("WFSerializationType") != "WFTextTokenAttachment":
                continue
            p["WFURL"] = tstr(raw(p["WFURL"]))
        elif ident == "is.workflow.actions.savetocameraroll":
            assert last_download, "save without a download before it"
            p.pop("WFPhotoAlbumName", None)
            p["WFInput"] = {"Value": {"OutputName": "Contents of URL", "OutputUUID": last_download,
                                      "Type": "ActionOutput"},
                            "WFSerializationType": "WFTextTokenAttachment"}
        elif ident == "is.workflow.actions.notification" and isinstance(
                p.get("WFNotificationActionBody"), dict):
            p["WFNotificationActionBody"] = B.token_text(p["WFNotificationActionBody"])
            p.setdefault("WFNotificationActionTitle", "FREE Media Downloader")
        else:
            continue
        changed += 1
    return changed


def patch(acts):
    """Nativize 1.5.1's Facebook steps, then put the prelude first inside the section."""
    changed = nativize(acts)
    start, _ = section(acts)
    steps = prelude()
    acts[start + 1:start + 1] = steps
    return changed, len(steps)
