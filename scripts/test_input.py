#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Release guard. scripts/sign.py runs this and refuses to sign when it fails.

1. LOCKED PLATFORMS (tests/locked-platforms.json). Every locked platform's
   share links are walked through the new build and through the baseline (the
   build the user last confirmed on their phone) for each server outcome: not
   reached, completed, failed. The executed steps must be byte-identical: same
   actions, same fields, same order, same If results, nothing added - not even
   a comment. Platforms in "strict_every_outcome" (X, Instagram) have no
   exception. The one declared exception ("failure_path_allowance") lets a
   share that already failed on the server skip the named block's gate.
2. The new build minus blocks that are new since the baseline (between
   "FMD+ name" / "FMD- name" comments) equals the baseline byte for byte.
3. Every new step is stored the way the Shortcuts app stores it (Match Text
   input under "text", Get Group under "matches", Save to Photo Album with an
   explicit input and no album, text-field URLs, no variable wrapped twice),
   and userLink only ever receives a URL, never plain text.
4. No text action runs on every share; the full a-Shell fallback is present.

The walk models control flow only. It is not a device test.

    python -X utf8 scripts/test_input.py [plist]
"""
import copy
import json
import os
import plistlib
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_v15 as B  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCK = json.load(open(os.path.join(ROOT, "tests", "locked-platforms.json"), encoding="utf-8"))
GOOD = os.path.join(ROOT, LOCK["baseline"])
CUR = os.path.join(ROOT, "shortcut", "fed.unsigned.plist")
FULL_ASHELL = "AsheKube.app.a-Shell.ExecuteCommandIntent"
PREFIX = "is.workflow.actions."
TEXT_INPUT = {"text.match", "text.match.getgroup", "text.replace", "urlencode",
              "detect.text", "text.split", "text.combine"}
OUTCOMES = ((None, "ok"), ("completed", "ok"), ("failed", "ok"),
            ("completed", "fail"), ("failed", "fail"))
SIDE_EFFECT_FREE = {"comment", "conditional", "text.match", "text.match.getgroup"}


def kind(a):
    return a["WFWorkflowActionIdentifier"].removeprefix(PREFIX)


def params(a):
    return a.get("WFWorkflowActionParameters", {})


def comment(a):
    return str(params(a).get("WFCommentActionText", "")) if kind(a) == "comment" else ""


def stamp_free(actions):
    """Copy with the header comment and version strings blanked (release stamping)."""
    acts = copy.deepcopy(actions)
    if acts and kind(acts[0]) == "comment":
        params(acts[0])["WFCommentActionText"] = "X"
    s = plistlib.dumps({"a": acts}, fmt=plistlib.FMT_XML).decode()
    s = re.sub(r"<string>1\.\d+(?:\.\d+)?</string>", "<string>X</string>", s)
    return plistlib.loads(s.encode())["a"]


def blocks(actions):
    """{name: set of action indexes} for every FMD+ ... FMD- block (markers included)."""
    out, stack = {}, []
    for i, a in enumerate(actions):
        c = comment(a)
        if c.startswith("FMD+ "):
            stack.append((c[5:].split(":")[0].strip(), i))
        elif c.startswith("FMD- "):
            name, start = stack.pop()
            assert name == c[5:].strip(), "unbalanced addition markers at %r" % c
            out[name] = set(range(start, i + 1))
    assert not stack, "unclosed addition %r" % stack
    return out


def walk(actions, link, shared=None, outcome=None, sections="ok"):
    """Executed steps for a share, as (index, If result or None).

    outcome None stops at the server-extractor POST; "completed"/"failed"
    continue past it with that status. sections="fail" makes every other
    network step (a site's own section: tikwm, Facebook, Threads, a-Shell...)
    come back empty, so shares fall through to the server and its outcome.
    Loops and menus are walked once.
    """
    shared = shared or link
    outputs, variables, ran, stack, active = {}, {"userLink": link}, [], [], True

    def value(tok):
        v = tok.get("Value", tok) if isinstance(tok, dict) else tok
        if isinstance(v, dict) and v.get("Type") == "Variable":
            return variables.get(v["VariableName"], "")
        if isinstance(v, dict) and v.get("Type") == "ActionOutput":
            return outputs.get(v["OutputUUID"], "")
        if isinstance(v, dict) and v.get("Type") == "ExtensionInput":
            return shared
        if isinstance(v, dict) and "attachmentsByRange" in v:
            s = v["string"]
            for rng, t in sorted(v["attachmentsByRange"].items(),
                                 key=lambda x: -int(x[0][1:].split(",")[0])):
                i = int(rng[1:].split(",")[0])
                s = s[:i] + str(value(t)) + s[i + 1:]
            return s
        return v

    for i, a in enumerate(actions):
        k, p = kind(a), params(a)
        if k == "conditional":
            mode = p["WFControlFlowMode"]
            if mode == 0:
                src = p["WFInput"]["Variable"]
                x, cond = str(value(src)), p.get("WFCondition")
                op = p.get("WFConditionalActionString", "")
                if "WFNumberValue" in p:
                    try:
                        sel = float(x) == float(p["WFNumberValue"]) if cond == 4 else False
                    except ValueError:
                        sel = False
                else:
                    sel = (op.lower() in x.lower() if cond == 8 else x == op if cond == 4
                           else bool(x) if cond == 100 else not x if cond == 101 else False)
                if active:
                    ran.append((i, sel))
                stack.append((active, sel))
                active = active and sel
            else:
                parent, sel = stack[-1]
                if parent:
                    ran.append((i, None))
                if mode == 1:
                    active = parent and not sel
                else:
                    stack.pop()
                    active = parent
            continue
        if not active:
            continue
        ran.append((i, None))
        if k == "downloadurl" and p.get("WFHTTPMethod") == "POST" and "WFJSONValues" in p and outcome is None:
            break
        if k == "exit":
            break
        u = p.get("UUID")
        if sections == "fail" and k == "downloadurl":
            outputs[u] = ""
            continue
        if sections == "fail" and k.endswith("GetFileIntent"):
            outputs[u] = "missing"
            continue
        if k == "getvalueforkey":
            outputs[u] = "<getvalueforkey>" if value(p.get("WFInput", {})) else ""
            continue
        if k == "detect.link":
            outputs[u] = shared
        elif k == "url.expand":
            outputs[u] = link
        elif k == "gettext":
            outputs[u] = str(value(p["WFTextActionText"]))
        elif k == "url":
            outputs[u] = str(value(p["WFURLActionURL"]))
        elif k == "number":
            outputs[u] = str(p.get("WFNumberActionNumber", ""))
        elif k == "setvariable":
            name = p["WFVariableName"]
            variables[name] = outcome if (name == "Status" and outcome) else value(p["WFInput"])
        elif k == "text.match":
            pat = p["WFMatchTextPattern"]
            src = p.get("text", p.get("WFInput"))
            m = re.search(value(pat) if isinstance(pat, dict) else pat, str(value(src)), re.I)
            outputs[u], outputs[u + "#m"] = (m.group(0) if m else ""), m
        elif k == "text.match.getgroup":
            src = p.get("matches", p.get("WFInput"))
            m = outputs.get(src["Value"].get("OutputUUID", "") + "#m")
            outputs[u] = m.group(p.get("WFGroupIndex", 1)) if m else ""
        elif u:
            outputs[u] = "<%s>" % k
    return ran


def as_steps(actions, ran):
    return [(json.dumps(actions[i], sort_keys=True, default=str), sel) for i, sel in ran]


def locked_problems(cur, good):
    fails = []
    ca, ga = stamp_free(cur), stamp_free(good)
    allow = LOCK.get("failure_path_allowance", {})
    cur_blocks, good_blocks = blocks(cur), blocks(good)
    allowed = set()
    for b in allow.get("blocks", []):
        if b in cur_blocks and b not in good_blocks:
            allowed |= cur_blocks[b]
    for name, entry in LOCK["locked"].items():
        for link in entry["links"]:
            shared, expanded = (link["shared"], link["expanded"]) if isinstance(link, dict) else (link, link)
            for outcome, sections in OUTCOMES:
                before = as_steps(ga, walk(ga, expanded, shared, outcome, sections))
                ran = walk(ca, expanded, shared, outcome, sections)
                after = as_steps(ca, ran)
                if before == after:
                    continue
                if outcome == "failed" and name not in LOCK["strict_every_outcome"] and allowed:
                    stripped = [s for (i, _), s in zip(ran, after) if i not in allowed]
                    inside = [kind(cur[i]) for i, _ in ran if i in allowed]
                    if stripped == before and all(k in SIDE_EFFECT_FREE for k in inside):
                        continue
                n = next((j for j, (x, y) in enumerate(zip(before, after)) if x != y),
                         min(len(before), len(after)))
                shown = json.loads(after[n][0]) if n < len(after) else "missing"
                fails.append("LOCKED %s (own section %s, server %s): %s runs different steps than the "
                             "confirmed build (first difference at step %d: %s)" % (
                                 name, sections, outcome or "not reached", shared, n,
                                 json.dumps(shown, default=str)[:170]))
    return fails


def native_problems(a):
    k, p = kind(a), params(a)
    bad = []
    if k == "text.match" and ("WFInput" in p or "text" not in p):
        bad.append("Match Text input must be under 'text'")
    if k == "text.match.getgroup" and ("WFInput" in p or "matches" not in p):
        bad.append("Get Group input must be under 'matches'")
    if k == "savetocameraroll" and ("WFInput" not in p or "WFPhotoAlbumName" in p):
        bad.append("Save to Photo Album needs an explicit input and no album")
    if k in ("downloadurl", "urlencode", "text.replace"):
        field = p.get("WFURL" if k == "downloadurl" else "WFInput")
        if isinstance(field, dict) and field.get("WFSerializationType") != "WFTextTokenString":
            bad.append("%s input must be a text field" % k)
    return bad


def wrapped(v):
    if isinstance(v, dict):
        if any(isinstance(t, dict) and "WFSerializationType" in t
               for t in (v.get("attachmentsByRange") or {}).values()):
            return True
        return any(wrapped(x) for x in v.values())
    if isinstance(v, list):
        return any(wrapped(x) for x in v)
    return False


def graph_problems(cur, good):
    fails = []
    B.find_input_block(cur)  # SystemExit if the 1.5.1 input block changed
    if sum(a["WFWorkflowActionIdentifier"] == FULL_ASHELL for a in cur) != 3:
        fails.append("1.5.1 full a-Shell fallback missing (the 1.6 regression)")
    depth, loose = 0, []
    for i, a in enumerate(cur):
        mode = params(a).get("WFControlFlowMode")
        if kind(a) in ("conditional", "repeat.each", "repeat.count", "choosefrommenu") and mode is not None:
            depth += 1 if mode == 0 else -1 if mode == 2 else 0
        elif depth == 0 and kind(a) in TEXT_INPUT:
            loose.append(i)
    if loose:
        fails.append("text actions run on every share: %s" % loose)
    new_blocks = {n: ix for n, ix in blocks(cur).items() if n not in blocks(good)}
    new_idx = set().union(*new_blocks.values()) if new_blocks else set()
    rest = [a for i, a in enumerate(cur) if i not in new_idx]
    if stamp_free(rest) != stamp_free(good):
        a, b = stamp_free(rest), stamp_free(good)
        diff = [i for i in range(min(len(a), len(b))) if a[i] != b[i]][:6]
        fails.append("outside the new blocks %s, the build differs from the confirmed build "
                     "(steps %s, %d vs %d)" % (sorted(new_blocks), diff, len(a), len(b)))
    uuids = {params(a).get("UUID"): kind(a) for a in cur}
    for i in sorted(new_idx):
        a = cur[i]
        for problem in native_problems(a) + (["variable wrapped twice"] if wrapped(params(a)) else []):
            fails.append("step %d (%s): %s" % (i, kind(a), problem))
        if kind(a) == "setvariable" and params(a).get("WFVariableName") == "userLink":
            src = params(a)["WFInput"]["Value"].get("OutputUUID")
            if uuids.get(src) not in ("url", "url.expand"):
                fails.append("step %d stores %s into userLink; only a URL may go there" % (i, uuids.get(src)))
    return fails, sorted(new_blocks)


def reach_problems(cur):
    fails = []

    def gates(link, outcome):
        return [(params(cur[i]).get("WFConditionalActionString"), sel)
                for i, sel in walk(cur, link, outcome=outcome) if sel is not None]
    g = gates("https://www.reddit.com/r/node/s/cv5XKIpUIr", "failed")
    if ("reddit.com", True) not in g or ("/s/", True) not in g:
        fails.append("Reddit /s/ link never reaches the Reddit steps after the server fails")
    for masto in ("https://social.vivaldi.net/@Vivaldi/117326000018306833",
                  "https://mstdn.social/@stux/117337607851617408"):
        ran = walk(cur, masto, outcome="failed")
        if ("/@", True) not in gates(masto, "failed") or not any(
                "api/v1/statuses" in json.dumps(params(cur[i])) for i, _ in ran):
            fails.append("Mastodon post %s never reaches the Mastodon steps after the server fails" % masto)
    for link in ("https://www.reddit.com/r/pics/comments/1abcde/title/",
                 "https://social.vivaldi.net/@Vivaldi/117326000018306833"):
        if any(op in ("reddit.com", "/@") for op, _ in gates(link, "completed")):
            fails.append("a tail block runs on a working (completed) download: %s" % link)
    return fails


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else CUR
    cur = plistlib.load(open(path, "rb"))["WFWorkflowActions"]
    good = plistlib.load(open(GOOD, "rb"))["WFWorkflowActions"]
    gfails, new = graph_problems(cur, good)
    fails = locked_problems(cur, good) + gfails + reach_problems(cur)
    for f in fails:
        print("FAIL", f)
    n = sum(len(e["links"]) for e in LOCK["locked"].values())
    print("input: locked %s (%d share links x %d outcomes); new blocks %s: %s" % (
        ", ".join(LOCK["locked"]), n, len(OUTCOMES), new or "none",
        "FAIL" if fails else "OK - locked paths byte-identical to the confirmed build"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
