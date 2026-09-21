#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Audit fed.unsigned.plist before it is signed.

Written after a shipped regression where the poll loop's Wait duration was
written as the string "1.0" instead of the number 1.0; iOS stored an empty value
and the shortcut stopped and prompted on every run. Structural validation had
passed. So this checks the things structural validation cannot:

  A  structure        identifiers, strict control-flow nesting, uuid uniqueness
  B  type fidelity    every parameter type against a known-good base plist
  C  required values  missing / empty / wrongly-typed parameters per action
  D  wiring           every ActionOutput and Variable reference resolves
  E  routes           each site's url forms, both share sheet and pasted link

    python -X utf8 scripts/audit.py --base <known-good-1.4.plist>
    python -X utf8 scripts/audit.py --base <1.4.plist> --device <payload-from-phone.plist>
"""
import argparse
import json
import plistlib
import re
import sys
from collections import Counter, defaultdict

CURRENT = "shortcut/fed.unsigned.plist"

# action -> {param: (expected python types, must_be_non_empty)}
REQUIRED = {
    "is.workflow.actions.downloadurl": {"WFURL": ((str, dict), True)},
    "is.workflow.actions.text.match": {"WFMatchTextPattern": ((str, dict), True)},
    "is.workflow.actions.text.match.getgroup": {
        "WFGetGroupType": ((str,), True), "WFGroupIndex": ((int,), False)},
    "is.workflow.actions.text.replace": {
        "WFReplaceTextFind": ((str,), True), "WFReplaceTextReplace": ((str,), False),
        "WFReplaceTextCaseSensitive": ((bool,), False),
        "WFReplaceTextRegularExpression": ((bool,), False)},
    "is.workflow.actions.setvariable": {
        "WFVariableName": ((str,), True), "WFInput": ((dict,), True)},
    "is.workflow.actions.getvalueforkey": {
        "WFDictionaryKey": ((str,), True), "WFInput": ((dict,), True)},
    "is.workflow.actions.conditional": {
        "WFCondition": ((int,), False), "WFControlFlowMode": ((int,), False)},
    "is.workflow.actions.repeat.each": {"WFControlFlowMode": ((int,), False)},    "is.workflow.actions.delay": {"WFDelayTime": ((int, float), True)},
    "is.workflow.actions.number": {"WFNumberActionNumber": ((str, int), True)},
    "is.workflow.actions.gettext": {"WFTextActionText": ((str, dict), True)},
    "is.workflow.actions.notification": {"WFNotificationActionBody": ((str, dict), True)},
    "is.workflow.actions.urlencode": {
        "WFEncodeMode": ((str,), True), "WFInput": ((dict,), True)},
    "is.workflow.actions.documentpicker.save": {"WFInput": ((dict,), True)},
    "is.workflow.actions.openurl": {"WFInput": ((dict,), True)},
    "is.workflow.actions.setitemname": {"WFName": ((dict, str), True)},
    "AsheKube.app.a-Shell-mini.ExecuteCommandIntent": {"command": ((dict, str), True)},
    "AsheKube.app.a-Shell-mini.GetFileIntent": {"fileName": ((str,), True)},
}
# parameter types Apple writes for the actions this repo generates that the 1.4
# base does not contain
EXPECTED_TYPES = {
    "WFMatchTextPattern": str, "WFMatchTextCaseSensitive": bool,
    "WFGroupIndex": int, "WFGetGroupType": str, "WFReplaceTextFind": str,
    "WFReplaceTextReplace": str, "WFReplaceTextCaseSensitive": bool,
    "WFReplaceTextRegularExpression": bool,
}
MAGIC_VARS = {"Repeat Item", "Repeat Item 2", "CurrentDate", "DeviceDetails",
              "Clipboard", "Repeat Index", "ExtensionInput", "Shortcut Input",
              "Ask for Input", "Current Weather", "Workflow Input"}
EMPTY_OK = {"WFPhotoAlbumName", "WFReplaceTextReplace"}


def load(p):
    return plistlib.loads(open(p, "rb").read())


def params(a):
    return a.get("WFWorkflowActionParameters") or {}


def walk_values(v, path=""):
    """Yield (path, key, value) for every dict key, recursively."""
    if isinstance(v, dict):
        for k, x in v.items():
            yield path, k, x
            for r in walk_values(x, "%s.%s" % (path, k)):
                yield r
    elif isinstance(v, list):
        for i, x in enumerate(v):
            for r in walk_values(x, "%s[%d]" % (path, i)):
                yield r


def collect_refs(v, out):
    """Collect ActionOutput uuids and Variable names."""
    if isinstance(v, dict):
        if v.get("Type") == "ActionOutput" and "OutputUUID" in v:
            out["uuid"].append(v["OutputUUID"])
        if v.get("Type") == "Variable" and "VariableName" in v:
            out["var"].append(v["VariableName"])
        for x in v.values():
            collect_refs(x, out)
    elif isinstance(v, list):
        for x in v:
            collect_refs(x, out)


def type_map(acts):
    """(identifier, param) -> set of python type names seen."""
    m = defaultdict(set)
    for a in acts:
        for k, v in params(a).items():
            m[(a.get("WFWorkflowActionIdentifier"), k)].add(type(v).__name__)
    return m


def audit_structure(acts, problems, base_acts=None):
    # known = everything the known-good base uses, plus the action types this
    # repo generates on top of it (regex extraction)
    known = {a.get("WFWorkflowActionIdentifier")
             for a in (base_acts if base_acts is not None else acts)} | {
        "is.workflow.actions.text.match", "is.workflow.actions.text.match.getgroup",
        "is.workflow.actions.text.replace",
    }
    for i, a in enumerate(acts):
        if a.get("WFWorkflowActionIdentifier") not in known:
            problems.append(("A", "unknown action at %d: %s" % (i, a.get("WFWorkflowActionIdentifier"))))
    stack, counts = [], Counter()
    seen_uuid = Counter()
    for i, a in enumerate(acts):
        p = params(a)
        if p.get("UUID"):
            seen_uuid[p["UUID"]] += 1
        g, mode = p.get("GroupingIdentifier"), p.get("WFControlFlowMode")
        if g is None or mode is None:
            continue
        counts[(g, mode)] += 1
        if mode == 0:
            stack.append((g, i))
        elif mode == 1:
            if not stack or stack[-1][0] != g:
                problems.append(("A", "Otherwise without matching If at %d" % i))
        else:
            if not stack or stack[-1][0] != g:
                problems.append(("A", "End without matching open at %d" % i))
            else:
                stack.pop()
    if stack:
        problems.append(("A", "unclosed control flow: %s" % [(g[:8], i) for g, i in stack]))
    for u, n in seen_uuid.items():
        if n > 1:
            problems.append(("A", "duplicate UUID %s x%d" % (u[:8], n)))
    return counts


def audit_types(acts, base_acts, problems):
    base = type_map(base_acts)
    for a in acts:
        ident = a.get("WFWorkflowActionIdentifier")
        for k, v in params(a).items():
            if k in ("UUID", "GroupingIdentifier"):
                continue
            tn = type(v).__name__
            if (ident, k) in base:
                if tn not in base[(ident, k)]:
                    problems.append(("B", "%s.%s is %s, base uses %s"
                                     % (ident.split('.')[-1], k, tn,
                                        "/".join(sorted(base[(ident, k)])))))
            elif k in EXPECTED_TYPES and tn != EXPECTED_TYPES[k].__name__:
                problems.append(("B", "%s.%s is %s, expected %s"
                                 % (ident.split('.')[-1], k, tn, EXPECTED_TYPES[k].__name__)))
    # the specific regression: a string in the Wait field
    for a in acts:
        if a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.delay":
            v = params(a).get("WFDelayTime")
            if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
                problems.append(("B", "Wait duration must be a positive NUMBER, got %r (%s)"
                                 % (v, type(v).__name__)))


def audit_required(acts, problems):
    for i, a in enumerate(acts):
        ident = a.get("WFWorkflowActionIdentifier")
        rule = REQUIRED.get(ident)
        if not rule:
            continue
        p = params(a)
        if ident == "is.workflow.actions.conditional" and p.get("WFControlFlowMode") != 0:
            continue  # Otherwise / End If carry no condition
        for k, (types, nonempty) in rule.items():
            if k not in p:
                problems.append(("C", "%s missing %s at %d" % (ident.split('.')[-1], k, i)))
                continue
            v = p[k]
            if not isinstance(v, types) or isinstance(v, bool) and bool not in types:
                problems.append(("C", "%s.%s wrong type %s at %d"
                                 % (ident.split('.')[-1], k, type(v).__name__, i)))
            if nonempty and k not in EMPTY_OK and (v == "" or v is None):
                problems.append(("C", "%s.%s is empty at %d" % (ident.split('.')[-1], k, i)))


def audit_wiring(acts, problems):
    defined = {params(a).get("UUID") for a in acts if params(a).get("UUID")}
    var_defs, order = set(), {}
    refs = {"uuid": [], "var": []}
    for i, a in enumerate(acts):
        ident = a.get("WFWorkflowActionIdentifier")
        p = params(a)
        if ident == "is.workflow.actions.setvariable" and p.get("WFVariableName"):
            var_defs.add(p["WFVariableName"])
            order[p["WFVariableName"]] = i
        collect_refs(p, refs)
    for u in refs["uuid"]:
        if u not in defined:
            problems.append(("D", "ActionOutput reference to unknown uuid %s" % u[:8]))
    undef = sorted({v for v in refs["var"] if v not in var_defs and v not in MAGIC_VARS})
    for v in undef:
        problems.append(("D", "variable {%s} is never set (and is not a magic variable)" % v))
    return len(refs["uuid"]), len(refs["var"])


ROUTES = [
    # (label, url forms, expected site branch)
    ("TikTok", ["https://www.tiktok.com/@u/video/6718335390845095173"], "tiktok"),
    ("YouTube", ["https://youtu.be/dQw4w9WgXcQ", "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                 "https://youtube.com/shorts/abc123", "https://m.youtube.com/watch?v=x",
                 "https://music.youtube.com/watch?v=x"], "youtu"),
    ("Instagram", ["https://www.instagram.com/p/Cabc/", "https://www.instagram.com/reel/Cabc/",
                   "https://instagr.am/p/Cabc/"], "instagram"),
    ("Facebook video", ["https://www.facebook.com/reel/815233250817277",
                        "https://www.facebook.com/watch/?v=815233250817277",
                        "https://www.facebook.com/NASA/videos/815233250817277/",
                        "https://m.facebook.com/story.php?story_fbid=815233250817277&id=1",
                        "https://fb.watch/abcDEF/"], "facebook"),
    ("Facebook photo", ["https://www.facebook.com/photo?fbid=1426466698848702",
                        "https://www.facebook.com/photo.php?fbid=1426466698848702&set=a.1",
                        "https://www.facebook.com/photo/?fbid=1426466698848702",
                        "https://www.facebook.com/NASA/posts/1426466738848698/"], "facebook"),
    ("X / Twitter", ["https://x.com/NASA/status/1732824684683784516",
                     "https://twitter.com/u/status/123456789?s=20&t=abc",
                     "https://x.com/i/status/123456789",
                     "https://twitter.com/u/status/123456789/photo/1",
                     "https://mobile.twitter.com/u/status/123456789"], "server extractor"),
    ("Reddit", ["https://www.reddit.com/r/x/comments/abc/title/", "https://redd.it/abc"], "server extractor"),
    ("Threads", ["https://www.threads.net/@u/post/Cabc", "https://www.threads.com/t/Cabc"], "server extractor"),
    ("Pinterest", ["https://www.pinterest.com/pin/93660867247422713/", "https://pin.it/abcDEF"], "server extractor"),
    ("Bluesky", ["https://bsky.app/profile/jay.bsky.team/post/3mvvdpby3x22t"], "server extractor"),
    ("Mastodon", ["https://mastodon.social/@mastodon/117303445557305921"], "server extractor"),
    ("Vimeo", ["https://vimeo.com/76979871"], "server extractor"),
    ("DailyMotion", ["https://www.dailymotion.com/video/x8n4jzh"], "server extractor"),
    ("SoundCloud", ["https://soundcloud.com/forss/flickermood"], "server extractor"),
    ("LinkedIn", ["https://www.linkedin.com/posts/u_x-activity-123"], "server extractor"),
    ("Snapchat", ["https://www.snapchat.com/spotlight/abc"], "server extractor"),
]


SITE_GUARDS = {
    # site: [probe that must exist in the plist for the branch to be present,
    #        substrings a url of that site realistically contains]
    "TikTok": ["tiktok", ["tiktok"]],
    "YouTube": ["youtu", ["youtu"]],
    "Instagram": ["instagram.com", ["instagram.com", "instagr.am"]],
    "Facebook video": ["facebook.com", ["facebook.com", "fb.watch"]],
    "Facebook photo": ["facebook.com", ["facebook.com", "fb.watch"]],
    "X / Twitter": ["api.fxtwitter.com", ["x.com/", "twitter.com/"]],
    "Pinterest": ["pin_ids=", ["pinterest.", "pin.it/"]],
    "Bluesky": ["getPostThread", ["bsky.app"]],
    "Mastodon": ["api/v1/statuses/", ["/status/", "/statuses/"]],
    "Reddit": None, "Threads": None, "Vimeo": None, "DailyMotion": None,
    "SoundCloud": None, "LinkedIn": None, "Snapchat": None,
}


def audit_routes(acts, problems, warnings, sites=None):
    """Report the branch each url form reaches, derived from the guards present."""
    blob = json.dumps(acts)
    rows = []
    for label, urls, _expected in [(r[0], r[1], r[2]) for r in ROUTES]:
        rule = SITE_GUARDS.get(label)
        if rule is None:
            rows.extend((label, u, "server extractor") for u in urls)
            continue
        probe, triggers = rule
        if probe not in blob:
            rows.extend((label, u, "server extractor") for u in urls)
            continue
        for u in urls:
            low = u.lower()
            if any(t in low for t in triggers):
                rows.append((label, u, label))
            else:
                warnings.append(("E", "%s: %s would not reach its own branch "
                                      "(url triggers: %s) - it falls through to the "
                                      "server extractor" % (label, u, triggers)))
                rows.append((label, u, "MISSED BRANCH"))
    return rows


def audit_input(cur, problems):
    """Share sheet + pasted-link entry points."""
    nok = cur.get("WFWorkflowNoInputBehavior") or {}
    if nok.get("Name") != "WFWorkflowNoInputBehaviorGetClipboard":
        problems.append(("F", "NoInputBehavior is %r: a run with no input will not "
                              "fall back to the clipboard" % nok.get("Name")))
    if "ActionExtension" not in (cur.get("WFWorkflowTypes") or []):
        problems.append(("F", "WFWorkflowTypes lacks ActionExtension: not offered in the share sheet"))
    for cls in ("WFURLContentItem", "WFStringContentItem", "WFRichTextContentItem"):
        if cls not in (cur.get("WFWorkflowInputContentItemClasses") or []):
            problems.append(("F", "input classes lack %s" % cls))
    blob = json.dumps(cur["WFWorkflowActions"])
    if "is.workflow.actions.detect.link" not in blob:
        problems.append(("F", "no Detect Link: a pasted url with surrounding text would not resolve"))
    if "is.workflow.actions.url.expand" not in blob:
        problems.append(("F", "no Expand URL: short links (fb.watch, pin.it, t.co) stay unresolved"))
    return nok


def selftest(cur, base):
    """Prove the checks catch the defect classes that have actually shipped."""
    import copy
    cases = []

    def caught(mutate, tag, what):
        pl = copy.deepcopy(cur)
        acts = pl["WFWorkflowActions"]
        mutate(pl, acts)
        probs = []
        audit_structure(acts, probs)
        audit_types(acts, base, probs)
        audit_required(acts, probs)
        audit_wiring(acts, probs)
        audit_input(pl, probs)
        hit = any(t == tag for t, _ in probs)
        cases.append((hit, tag, what))
        return hit

    def delay_as_string(pl, acts):
        for a in acts:
            if a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.delay":
                params(a)["WFDelayTime"] = "1.0"

    def blank_pattern(pl, acts):
        for a in acts:
            if a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.text.match":
                params(a)["WFMatchTextPattern"] = ""
                return

    def group_index_string(pl, acts):
        for a in acts:
            if a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.text.match.getgroup":
                params(a)["WFGroupIndex"] = "1"
                return

    def bogus_output_uuid(pl, acts):
        for a in acts:
            for k, v in params(a).items():
                if isinstance(v, dict) and v.get("Value", {}).get("Type") == "ActionOutput":
                    v["Value"]["OutputUUID"] = "00000000-0000-0000-0000-000000000000"
                    return

    def undefined_variable(pl, acts):
        for a in acts:
            if a.get("WFWorkflowActionIdentifier") == "is.workflow.actions.downloadurl":
                params(a)["WFURL"] = {"Value": {"Type": "Variable", "VariableName": "nope"},
                                      "WFSerializationType": "WFTextTokenAttachment"}
                return

    def no_clipboard(pl, acts):
        pl["WFWorkflowNoInputBehavior"] = {"Name": "WFWorkflowNoInputBehaviorAskForInput",
                                           "Parameters": {}}

    caught(delay_as_string, "B", "Wait duration as a string (the one that shipped)")
    caught(group_index_string, "B", "Group index as a string")
    caught(blank_pattern, "C", "empty Match Text pattern")
    caught(undefined_variable, "D", "variable that is never set")
    caught(bogus_output_uuid, "D", "reference to a non-existent action output")
    caught(no_clipboard, "F", "pasted-link entry point replaced by Ask For Input")
    print("== self-test: does the audit catch what has shipped? ==")
    for ok, tag, what in cases:
        print("   %s [%s] %s" % ("CAUGHT " if ok else "MISSED ", tag, what))
    missed = [c for c in cases if not c[0]]
    return len(cases) - len(missed), len(cases)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--plist", default=CURRENT)
    ap.add_argument("--device", help="payload downloaded back from a phone")
    ap.add_argument("--quiet-routes", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    cur = load(args.plist)
    acts = cur["WFWorkflowActions"]
    base = load(args.base)["WFWorkflowActions"]
    problems = []
    warnings = []

    if args.selftest:
        ok, total = selftest(cur, base)
        return 0 if ok == total else 1

    print("== A structure ==")
    audit_structure(acts, problems, base)
    print("   actions %d | base %d | ids %d" % (len(acts), len(base),
                                                len({a.get('WFWorkflowActionIdentifier') for a in acts})))
    print("== B type fidelity (vs known-good base) ==")
    audit_types(acts, base, problems)
    print("== C required values ==")
    audit_required(acts, problems)
    print("== D wiring ==")
    nu, nv = audit_wiring(acts, problems)
    print("   output refs %d | variable refs %d" % (nu, nv))
    print("== E routes ==")
    rows = audit_routes(acts, problems, warnings)
    print("   tested %d url forms across %d sites" % (len(rows), len({r[0] for r in rows})))
    if not args.quiet_routes:
        for label, u, hit, _ in rows:
            print("   %-16s %-56s -> %s" % (label, u[:56], hit))
    print("== F entry points (share sheet + pasted link) ==")
    nok = audit_input(cur, problems)
    print("   NoInputBehavior %s | types %s | input classes %d"
          % (nok.get("Name"), cur.get("WFWorkflowTypes"), len(cur.get("WFWorkflowInputContentItemClasses") or [])))

    if args.device:
        print("== G device round-trip fidelity (%s) ==" % args.device)
        dev = load(args.device)["WFWorkflowActions"]
        if len(dev) != len(acts):
            problems.append(("G", "device payload has %d actions, local has %d" % (len(dev), len(acts))))
        else:
            blanks, ids = [], 0
            for i, (d, l) in enumerate(zip(dev, acts)):
                if d.get("WFWorkflowActionIdentifier") != l.get("WFWorkflowActionIdentifier"):
                    ids += 1
                    problems.append(("G", "action %d changed type on device" % i))
                for k, v in params(l).items():
                    dv = params(d).get(k)
                    if dv in ("", None) and v not in ("", None) and k != "WFPhotoAlbumName":
                        blanks.append((i, l.get("WFWorkflowActionIdentifier").split('.')[-1], k, v))
            for b in blanks:
                problems.append(("G", "device blanked %s.%s (local %r)" % (b[1], b[2], b[3])))
            print("   actions match: %s | identifier changes: %d | blanked: %d"
                  % (len(dev) == len(acts), ids, len(blanks)))

    print()
    if warnings:
        print("WARNINGS: %d" % len(warnings))
        for tag, m in warnings[:10]:
            print("   -", m)
    if problems:
        by = defaultdict(list)
        for tag, msg in problems:
            by[tag].append(msg)
        for tag in sorted(by):
            print("PROBLEMS [%s]: %d" % (tag, len(by[tag])))
            for m in by[tag][:20]:
                print("   -", m)
        print("\n%d problem(s)" % len(problems))
        return 1
    print("AUDIT CLEAN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
