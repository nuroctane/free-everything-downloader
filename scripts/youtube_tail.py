#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""YouTube links that lost "youtu" before the YouTube check, in the server-failed tail.

Reported 2026-10-14 on 1.7, 1.7.3 and 1.7.4 (a-Shell mini installed): a YouTube
Short shared from the YouTube app, and the same link run from the Shortcuts app
off the clipboard (https://youtube.com/shorts/lMcdGXlFyPI?is=R7ufibXITQ_Q2Xdt),
both end with the server extractor's "Couldn't grab a file from that link" and
the sign-in tail. A link containing "youtu" always enters the YouTube section
and stops there, so on the phone `userLink` (the Expand URL output) no longer
contained "youtu" when the YouTube check ran. The link itself is fine, so this
block reads the link as it was shared (the Get URLs output, before Expand URL).

Where it lives: the sign-in tail of the server-failed branch, next to the
Reddit, Mastodon and Threads blocks. Only a share that already failed in its own
section AND on the server gets there; X and Instagram never do, and on every
other platform's failed path the gate is false, so only this block's comments,
its If and its End If run (tests/locked-platforms.json failure_path_allowance).

What it runs: the original link goes into userLink through a URL action, then
exact copies (fresh ids) of the confirmed 1.7 YouTube steps, from the a-Shell
command through its final Stop.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf import Graph, COND_CONTAINS, out, native_if, native_url  # noqa: E402
import reddit_tail  # noqa: E402

NAME = "YouTube original links"
YT_IF = "25121468-A600-4B62-BC17-5A4D31DD6CA8"    # If userLink contains "youtu"
LINKS = "90543E50-F039-4C91-A2AE-313ABC0D493F"    # Get URLs from Shortcut Input


def P(a):
    return a["WFWorkflowActionParameters"]


def youtube_section(acts):
    """The confirmed YouTube steps between its If and End If (command ... Stop)."""
    start = next(i for i, a in enumerate(acts) if P(a).get("UUID") == YT_IF)
    gid = P(acts[start])["GroupingIdentifier"]
    end = next(i for i in range(start + 1, len(acts))
               if P(acts[i]).get("GroupingIdentifier") == gid and P(acts[i]).get("WFControlFlowMode") == 2)
    body = acts[start + 1:end]
    assert reddit_tail.kind(body[-1]) == "exit", "YouTube section no longer ends with Stop"
    return body


def shared_links(acts):
    a = next(a for a in acts if P(a).get("UUID") == LINKS)
    assert a["WFWorkflowActionIdentifier"] == "is.workflow.actions.detect.link"
    return {"Value": {"OutputName": "URLs", "OutputUUID": LINKS, "Type": "ActionOutput"},
            "WFSerializationType": "WFTextTokenAttachment"}


def block(acts):
    links = shared_links(acts)
    g = Graph()
    g.comment("FMD+ %s: the shared link contains youtu but userLink did not, so the share "
              "skipped the YouTube section. Run the same YouTube steps on the link as shared; "
              "only an already-failed share gets here." % NAME)
    native_if(g, COND_CONTAINS, links, "youtu")
    link = native_url(g, links, name="Shared YouTube Link")
    g.setvar("userLink", out(link))
    head = [a.d for a in g.actions]
    steps = reddit_tail.clone(youtube_section(acts))
    closer = Graph()
    closer._stack = list(g._stack)
    closer.endif()
    closer.comment("FMD- %s" % NAME)
    assert not closer._stack, "youtube tail block is unbalanced"
    return head + steps + [a.d for a in closer.actions]


def patch(acts):
    """Insert the block immediately before the sign-in tail."""
    at = reddit_tail.locate(acts)["tail"]
    steps = block(acts)
    acts[at:at] = steps
    return len(steps)


# ------------------------------------------------------- shares with no link
# Reported 2026-10-14 with a test shortcut on the user's phone: started on a
# video in the YouTube app, the shortcut's input was Text (the screen's text:
# "Open App", the title, "@CyberpunkGame", likes, comments...) and sometimes a
# small PNG, with no link anywhere. Without a link nothing can match, so the
# share fails on the server and lands here. The user: "It should work either
# way". This block, only for a share whose input has no http link at all:
#   1. the input's own YouTube screen text (a title line, then an @channel line,
#      and YouTube's "Subscribe") -> yt-dlp searches YouTube for that exact
#      title + channel and downloads the top match with the same 1.7 steps;
#   2. otherwise a YouTube link on the clipboard (e.g. after Share > Copy link)
#      -> the same 1.7 steps on that link.
NO_LINK = "YouTube shares without a link"
SCREEN = r"(?m)^([^\r\n]+)\r?\n@([A-Za-z0-9._\-]+?)(?:Subscribe)?[ \t]*$"
CLIP = r"https?://[^\s\"'<>]*youtu[^\s\"'<>]*"
SHELL_UNSAFE = r"[\"$`\\]"


def _ext_input():
    return {"Value": {"Type": "ExtensionInput"}, "WFSerializationType": "WFTextTokenAttachment"}


def _on(source_token, section):
    """The YouTube steps with the command's userLink swapped for source_token (raw)."""
    steps = reddit_tail.clone(section)
    cmd = steps[0]
    assert cmd["WFWorkflowActionIdentifier"] == "is.workflow.actions.gettext"
    rng = P(cmd)["WFTextActionText"]["Value"]["attachmentsByRange"]
    keys = [k for k, t in rng.items() if t.get("VariableName") == "userLink"]
    assert len(keys) == 1, "YouTube command no longer reads userLink once"
    rng[keys[0]] = source_token
    return steps


def no_link_block(acts):
    from wf import COND_HAS_VALUE, Action, native_match, native_group, native_replace, raw
    section = youtube_section(acts)
    links = shared_links(acts)
    g = Graph()
    g.comment("FMD+ %s: the share had no link (the YouTube app can hand over only the "
              "screen's text). Search YouTube for the title and channel in that text, else "
              "use a YouTube link on the clipboard; only an already-failed share gets here." % NO_LINK)
    native_if(g, COND_CONTAINS, links, "http")
    g.else_()
    screen = native_match(g, SCREEN, _ext_input(), name="YouTube Screen Text")
    native_if(g, COND_HAS_VALUE, out(screen))
    native_if(g, COND_CONTAINS, _ext_input(), "Subscribe")
    title = native_group(g, out(screen), name="YouTube Title", index=1)
    channel = native_group(g, out(screen), name="YouTube Channel", index=2)
    safe = native_replace(g, SHELL_UNSAFE, "", out(title), name="YouTube Search Title")
    P(safe.d)["WFReplaceTextRegularExpression"] = True
    query = g.text("ytsearch1:", raw(out(safe)), " ", raw(out(channel)), name="YouTube Search")
    g.notify("No link came with this share. Searching YouTube for “", raw(out(title)),
             "” by @", raw(out(channel)), " and downloading it.")
    head = [a.d for a in g.actions]
    search = _on({"OutputName": query.name, "OutputUUID": query.uuid, "Type": "ActionOutput"}, section)
    mid = Graph()
    mid._stack = list(g._stack)
    mid.endif()   # Subscribe
    mid.endif()   # screen text
    clip = mid._push(Action("is.workflow.actions.getclipboard", {}, "Clipboard"))
    found = native_match(mid, CLIP, out(clip), name="Clipboard YouTube Link")
    native_if(mid, COND_HAS_VALUE, out(found))
    link = native_url(mid, out(found), name="Clipboard YouTube URL")
    mid.setvar("userLink", out(link))
    middle = [a.d for a in mid.actions]
    clipped = reddit_tail.clone(section)
    end = Graph()
    end._stack = list(mid._stack)
    end.endif()   # clipboard link
    end.endif()   # no http link
    end.comment("FMD- %s" % NO_LINK)
    assert not end._stack, "no-link block is unbalanced"
    return head + search + middle + clipped + [a.d for a in end.actions]


def patch_no_link(acts):
    """Insert the block immediately before the sign-in tail."""
    at = reddit_tail.locate(acts)["tail"]
    steps = no_link_block(acts)
    acts[at:at] = steps
    return len(steps)
