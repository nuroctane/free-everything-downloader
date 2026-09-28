#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reddit share links, in the one place no locked platform ever reaches.

The Reddit app shares reddit.com/r/<sub>/s/<code> links. The phone's Expand URL
sends no browser user-agent and Reddit answers 403, so the link reaches the
server extractor unexpanded and fails ("invalid media url").

Where this goes: inside 1.5.1's `If Status is failed` branch, right before the
sign-in tail ("Session needed..."). Nothing that works ever gets there:
  - X, Twitter, Bluesky and Mastodon set UseTVDL and the backup downloader
    block always ends with Stop before the tail;
  - Instagram, TikTok, Threads and Facebook save in their own sections;
  - a successful server download stops in the "completed" branch.
Only a share that has already failed everywhere reaches the tail.

What it does, Reddit /s/ links only: open the link with Facebook's crawler
user-agent (Reddit then redirects to the post and states its og:url), put the
post URL in userLink (a URL action, never plain text), and rerun the server
download with exact copies of 1.5.1's own POST / poll / completed steps, the
ones the phone already runs for every X download.
"""
import copy
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf import (Graph, Action, var, out, coerce, dkey, COND_CONTAINS, COND_HAS_VALUE,  # noqa: E402
                native_if, native_match, native_group, native_get, native_url, native_notify,
                native_save)
import build_v15 as B  # noqa: E402

POLLS = 10          # 10 x 2 s: Reddit jobs finish in 4-10 s (measured)
POLL_WAIT = 2.0
TAIL = "Session needed: open the post in Safari or the native app. Sign in. Come back. Share the post again."


def nid():
    return str(uuid.uuid4()).upper()


def params(a):
    return a["WFWorkflowActionParameters"]


def kind(a):
    return a["WFWorkflowActionIdentifier"].rsplit(".", 1)[-1]


def clone(actions):
    """Copy 1.5.1 steps with fresh UUIDs / grouping ids; remap references inside the copy."""
    acts = copy.deepcopy(actions)
    ids = {params(a)["UUID"]: nid() for a in acts if "UUID" in params(a)}
    groups = {params(a)["GroupingIdentifier"]: nid() for a in acts if "GroupingIdentifier" in params(a)}

    def remap(v):
        if isinstance(v, dict):
            for k, x in list(v.items()):
                if k == "OutputUUID" and x in ids:
                    v[k] = ids[x]
                elif k in ("UUID",) and x in ids:
                    v[k] = ids[x]
                elif k == "GroupingIdentifier" and x in groups:
                    v[k] = groups[x]
                else:
                    remap(x)
        elif isinstance(v, list):
            for x in v:
                remap(x)
    for a in acts:
        remap(params(a))
    return acts


def locate(acts):
    agg = B.find_aggregator(acts)
    assert kind(acts[agg + 1]) == "setvariable" and params(acts[agg + 1])["WFVariableName"] == "ID"
    loop = agg + 3
    assert kind(acts[loop]) == "each" or kind(acts[loop]) == "count", kind(acts[loop])
    poll, resp, status, done = loop + 1, loop + 2, loop + 3, loop + 4
    assert params(acts[resp])["WFVariableName"] == "Response"
    assert params(acts[status])["WFVariableName"] == "Status"
    assert params(acts[done]).get("WFConditionalActionString") == "completed"
    gid = params(acts[done])["GroupingIdentifier"]
    done_end = next(i for i in range(done + 1, len(acts))
                    if params(acts[i]).get("GroupingIdentifier") == gid
                    and params(acts[i]).get("WFControlFlowMode") == 2)
    assert kind(acts[done_end - 1]) == "exit"
    delay = next(a for a in acts if kind(a) == "delay")
    tail = next(i for i, a in enumerate(acts) if params(a).get("WFCommentActionText") == TAIL)
    return dict(agg=agg, poll=poll, resp=resp, status=status, done=done, done_end=done_end,
                delay=delay, tail=tail)


def block(acts):
    at = locate(acts)
    post, set_id = acts[at["agg"]], acts[at["agg"] + 1]
    poll_steps = acts[at["poll"]:at["status"] + 1]          # GET, Response, Status
    completed_if = acts[at["done"]]
    completed_body = acts[at["done"] + 1:at["done_end"] - 1]  # everything before its Stop

    def if_completed():
        a = copy.deepcopy(completed_if)
        gid = nid()
        params(a)["GroupingIdentifier"], params(a)["UUID"] = gid, nid()
        return a, gid

    def flow(gid, mode):
        return {"WFWorkflowActionIdentifier": "is.workflow.actions.conditional",
                "WFWorkflowActionParameters": {"GroupingIdentifier": gid, "UUID": nid(),
                                               "WFControlFlowMode": mode}}

    def wait():
        a = copy.deepcopy(at["delay"])
        params(a)["UUID"], params(a)["WFDelayTime"] = nid(), POLL_WAIT
        return a

    g = Graph()
    g.comment("FMD+ Reddit share links: reddit.com/r/<sub>/s/<code> reaches here unexpanded "
              "after the server fails; only failed shares ever reach this point.")
    native_if(g, COND_CONTAINS, var("userLink"), "reddit.com")
    native_if(g, COND_CONTAINS, var("userLink"), "/s/")
    page = native_get(g, [var("userLink")], headers=[("User-Agent", B.CRAWLER_UA)],
                      name="Reddit Share Page")
    og = native_match(g, B.OG_URL, out(page), name="Reddit Post Link")
    native_if(g, COND_HAS_VALUE, out(og))
    post_url = native_url(g, out(native_group(g, out(og), name="Reddit Post URL")))
    g.setvar("userLink", out(post_url))
    head = [a.d for a in g.actions]

    # Rerun 1.5.1's own server download with the post URL.
    job = clone([post, set_id])
    steps = list(job)
    closes = []
    for n in range(POLLS):
        steps.append(wait())
        steps.extend(clone(poll_steps))
        cond, gid = if_completed()
        steps.append(cond)
        steps.append(flow(gid, 1))          # Otherwise: not completed yet -> poll again
        closes.append(gid)
    for gid in reversed(closes):
        steps.append(flow(gid, 2))
    cond, gid = if_completed()
    steps.append(cond)
    steps.extend(clone(completed_body))
    tail = Graph()
    native_notify(tail, "Saved from Reddit.")
    tail.stop()
    steps.extend(a.d for a in tail.actions)
    steps.append(flow(gid, 2))
    end = Graph()
    native_notify(end, "Couldn't download this Reddit post. If it's private or removed, "
                       "there is nothing public to save.")
    end.stop()
    steps.extend(a.d for a in end.actions)

    # Close: og match, /s/, reddit.com  (the Graph above opened three Ifs)
    closer = Graph()
    closer._stack = list(g._stack)
    closer.endif()
    closer.endif()
    closer.endif()
    closer.comment("FMD- Reddit share links")
    return head + steps + [a.d for a in closer.actions]


def patch(acts):
    at = locate(acts)
    steps = block(acts)
    acts[at["tail"]:at["tail"]] = steps
    return len(steps)


# ------------------------------------------------------------------ Mastodon
# The server extractor rejects every Mastodon post ("invalid media url") and
# 1.5.1's backup downloader only runs for links containing "mastodon", so
# posts on most Mastodon servers never downloaded. Same place as Reddit: the
# sign-in tail, which only already-failed shares reach. The instance's public
# API (/api/v1/statuses/<id>) lists the original media files.
def mastodon_block():
    g = Graph()
    g.comment("FMD+ Mastodon posts: any Mastodon server, from the server's own public API; "
              "only failed shares ever reach this point.")
    native_if(g, COND_CONTAINS, var("userLink"), "/@")
    post = native_match(g, B.MASTODON, var("userLink"), name="Mastodon Post")
    native_if(g, COND_HAS_VALUE, out(post))
    host = native_group(g, out(post), name="Mastodon Server", index=1)
    sid = native_group(g, out(post), name="Mastodon Status", index=2)
    api = native_get(g, ["https://", out(host), "/api/v1/statuses/", out(sid)], name="Mastodon Status JSON")
    # Same shape as the completed branch's `Items = Response.result.items`.
    g.setvar("MastoMedia", out(api, [coerce("WFDictionaryContentItem"), dkey("media_attachments")]))
    native_if(g, COND_HAS_VALUE, var("MastoMedia"))
    g.repeat_each(var("MastoMedia"))
    # Same shape as the completed branch's URL step: Repeat Item 2 as a dictionary, key url.
    link = g._push(Action("is.workflow.actions.url", {"WFURLActionURL": var(
        "Repeat Item 2", [coerce("WFDictionaryContentItem"), dkey("url")])}, "URL"))
    media = native_get(g, [out(link)], name="Mastodon Media")
    native_save(g, out(media))
    g.endrepeat()
    native_notify(g, "Saved from Mastodon.")
    g.stop()
    g.endif()   # media
    g.endif()   # status link
    g.endif()   # "/@"
    g.comment("FMD- Mastodon posts")
    assert not g._stack, "mastodon block is unbalanced"
    return [a.d for a in g.actions]


def patch_mastodon(acts):
    at = locate(acts)
    steps = mastodon_block()
    acts[at["tail"]:at["tail"]] = steps
    return len(steps)
