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
