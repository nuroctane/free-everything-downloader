#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Add full a-Shell as a fallback next to a-Shell mini (YouTube / Instagram).

Both apps expose the same three intents under different bundle ids:
    mini  AsheKube.app.a-Shell-mini.{ExecuteCommandIntent,GetFileIntent}
    full  AsheKube.app.a-Shell.{ExecuteCommandIntent,GetFileIntent}
The shortcut only ever addressed mini, so the full app silently could not run
the yt-dlp path.

Insert, after each yt-dlp block has pulled its result back from mini:

    If fedKind is "missing"
        run the same command in full a-Shell
        pull fed-kind.txt / fed-ext.txt back from full a-Shell
    End If

Mini keeps working exactly as before (it runs first and wins). Full a-Shell is
only touched when mini left fedKind as "missing" - which is also the value a
failed yt-dlp run writes, so the retry costs one extra attempt only in the
already-failing case.

    python -X utf8 scripts/build_shell_compat.py --in P --out P2
"""
import argparse
import os
import plistlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wf import Action, Graph, new_uuid, tstr, var, out, COND_IS  # noqa: E402

FULL_EXEC = "AsheKube.app.a-Shell.ExecuteCommandIntent"
FULL_GET = "AsheKube.app.a-Shell.GetFileIntent"


def full_retry(g, command_uuid):
    """5 actions: try full a-Shell, refresh fedKind / fedExt."""
    g.if_(COND_IS, var("fedKind"), "missing", name="If")
    # the command variable is set just before mini runs; reuse it
    g._push(Action(FULL_EXEC,
                   {"command": var("command"), "keepGoing": True}, "Full shell"))
    g._push(Action("is.workflow.actions.waittoreturn", {}, "Wait to Return"))
    kind = g._push(Action(FULL_GET, {"fileName": "fed-kind.txt"}, "FullKindFile"))
    kind.d["WFWorkflowActionParameters"]["CustomOutputName"] = "FullKindFile"
    g.setvar("fedKind", out(kind))
    ext = g._push(Action(FULL_GET, {"fileName": "fed-ext.txt"}, "FullExtFile"))
    ext.d["WFWorkflowActionParameters"]["CustomOutputName"] = "FullExtFile"
    g.setvar("fedExt", out(ext))
    g.endif()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    p = plistlib.loads(open(a.src, "rb").read())
    acts = p["WFWorkflowActions"]
    if FULL_EXEC in str(acts):
        raise SystemExit("full a-Shell fallback already present")

    inserts = []  # (index, actions)
    for i, act in enumerate(acts):
        if act.get("WFWorkflowActionIdentifier") != "is.workflow.actions.setvariable":
            continue
        prm = act.get("WFWorkflowActionParameters") or {}
        if prm.get("WFVariableName") != "fedExt":
            continue
        # must be the yt-dlp result pull (preceded by GetFileIntent fed-ext.txt)
        prev = acts[i - 1]
        if (prev.get("WFWorkflowActionIdentifier") != "AsheKube.app.a-Shell-mini.GetFileIntent"
                or (prev.get("WFWorkflowActionParameters") or {}).get("fileName") != "fed-ext.txt"):
            continue
        g = Graph()
        full_retry(g, None)
        assert not g._stack
        inserts.append((i + 1, [x.d for x in g.actions]))

    if not inserts:
        raise SystemExit("no yt-dlp result pull found")
    for idx, new in reversed(inserts):
        acts[idx:idx] = new

    tmp = a.out + ".tmp"
    with open(tmp, "wb") as fh:
        plistlib.dump(p, fh, fmt=plistlib.FMT_XML)
    chk = plistlib.loads(open(tmp, "rb").read())
    assert len(chk["WFWorkflowActions"]) == len(acts)
    os.replace(tmp, a.out)
    print("inserted full a-Shell fallback at %d site(s): %s"
          % (len(inserts), [i for i, _ in inserts]))
    print("actions -> %d" % len(acts))


if __name__ == "__main__":
    sys.exit(main())
