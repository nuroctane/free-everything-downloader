#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Threads posts the server could not fetch, in the one place nothing working reaches.

The Threads app (and an Expand URL that sends a user-agent) hands the shortcut a
threads.com/... post link *intact*. The on-device Threads recipe only runs inside
1.5.1's `If userLink contains "facebook.com"` section, which an intact link never
enters, so it goes to the server extractor. When that job fails, the sign-in tail
claims the post wants a login and opens the link - which is wrong for a public
post, and does nothing the user can see because they just came from the app.

This block lives where Reddit and Mastodon already live: the sign-in tail of the
server-failed branch. Only a share that already failed in its own section AND on
the server reaches that tail, and the block is gated on "threads.", so:

  - X and Instagram never reach the tail at all;
  - on every other platform's failed path the gate is false, so only the FMD
    comments, the If and its End If execute (side-effect-free, which is what
    tests/locked-platforms.json's failure_path_allowance requires);
  - a Threads link in the locked model (facebook.com/unsupportedbrowser) is
    already answered by the Facebook section's own copy of the recipe and stops
    there, so this block is not reached;
  - a successful download stops in the "completed" branch.

The recipe itself is the exact one the confirmed baseline already runs for
Threads (post page fetched with Meta's crawler user-agent, signed CDN media,
save to Photos), so behavior matches the path the user confirmed on the phone.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf import Graph, COND_CONTAINS, var, out, coerce, native_if, native_url, native_notify  # noqa: E402
import fb_section  # noqa: E402
import reddit_tail  # noqa: E402

NAME = "Threads server-failed posts"
OPEN_NOW = ("Couldn't save this Threads post from the page. Opening it in the Threads app, "
            "or in your browser if Threads is not installed. Sign in there, then share it again.")
SHARE_AGAIN = "Once you are signed in, share the post to FREE Media Downloader again."


def open_for_signin(g):
    """Open a real URL, not the userLink variable.

    The tail's Open URL takes userLink and coerces it. That is the step the
    report says never opens. A URL action output is already a URL, which is
    the shape every working open in this shortcut uses.
    """
    native_notify(g, OPEN_NOW)
    link = native_url(g, var("userLink"))
    g.open_url(out(link, [coerce("WFURLContentItem")]))
    g.wait_to_return()
    native_notify(g, SHARE_AGAIN)
    g.stop()


def block():
    g = Graph()
    g.comment("FMD+ %s: an intact threads.com link skips the Facebook section, so a "
              "server failure landed on the sign-in tail. Same on-device recipe as that "
              "section; only an already-failed share gets here." % NAME)
    native_if(g, COND_CONTAINS, var("userLink"), "threads.")
    fb_section.threads_recipe(g, on_no_media=open_for_signin)
    g.endif()
    g.comment("FMD- %s" % NAME)
    assert not g._stack, "threads tail block is unbalanced"
    return [a.d for a in g.actions]


def patch(acts):
    """Insert the block immediately before the sign-in tail."""
    at = reddit_tail.locate(acts)["tail"]
    steps = block()
    acts[at:at] = steps
    return len(steps)
