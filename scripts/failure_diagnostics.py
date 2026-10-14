"""The fields the user explicitly authorized changing on 2026-10-13.

No actions, groups, URLs, formats, app intents or save destinations are added
or replaced. The original 1.7 fixture remains the immutable comparison base.
"""
import copy
import json
import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCEPTION_ID = "2026-10-13-youtube-logging-and-failure-messages"
# 2026-10-13: the user rejected the diagnostic-only build ("we arent shipping shit
# without resolving the failures") and told this session to fix the reported
# YouTube/Threads failures. The same field list is reused: the only YouTube
# runtime fields that may change are its command text and its failure notice.
USER_WORDS = ("do your absolute best to fix it without breaking or regressing anything "
              "and requiring failure reproduction")
COMMAND_UUID = "1AD25592-D6F8-4699-ACD7-E133678DECBE"
MESSAGES = {
    "F113D37D-F272-412D-85C1-0218FA50F60E":
        "Download failed. Attempting to open the original post so you can check whether it is available.",
    "EF2EE840-7A25-442C-8F31-7225CC482C0F":
        "If the post is public and still cannot be downloaded, please report the failure.",
}
# 2026-10-14: on 1.7.3 the user reported YouTube Shorts failing and downloads that
# "simply hang and dont complete with no error". The logged command hid yt-dlp's
# live output in a-Shell and added a silent pip update + retry, so YouTube's
# command and its failure notice are back to the confirmed 1.7 text (no longer
# in FIELDS). logged_command() below is kept for reference only; nothing calls it.
FIELDS = {u: "WFNotificationActionBody" for u in MESSAGES}


START = 'U="\ufffc"; '
# The state files the shortcut reads back with GetFileIntent once the command
# finishes. The 1.7 baseline wrote them *after* the helper check and any pip
# work; a first-run install that is slow or is killed left them missing, so the
# shortcut died on a raw missing-file error instead of its own notice.
GUARD = ('SC="${SHORTCUTS:-}"; [ -n "$SC" ] || SC=~shortcuts; mkdir -p "$SC"; '
         'printf missing > "$SC/fed-kind.txt"; printf txt > "$SC/fed-ext.txt"; '
         'touch "$SC/fed-media"; ')
HELPERS = ('pip show yt-dlp-ejs yt-dlp-apple-webkit-jsi >/dev/null 2>&1 || '
           'pip install -U "yt-dlp[default]" yt-dlp-ejs yt-dlp-apple-webkit-jsi; ')
DOWNLOAD = ('yt-dlp $CK $AUD $EMB -f "$FMT" -S "ext:mp4:m4a" --no-mtime --no-part '
            '--force-overwrites -P "$HOME/Documents" -o "fed-dl.%(ext)s" -- "$U"; '
            'f=$(ls -t "$HOME/Documents"/fed-dl.* 2>/dev/null | sed -n 1p); ')
TRIM = ('python3 -c \'import os,sys; p=sys.argv[1]; f=open(p,"rb"); '
        'f.seek(max(0,os.fstat(f.fileno()).st_size-65536)); b=f.read(65536); '
        'f.close(); open(p,"wb").write(b)\' "$LOG" 2>/dev/null || true; ')


def _attempt():
    """One identical yt-dlp run; records its exit status and the file it left."""
    return ('yt-dlp --no-progress $CK $AUD $EMB -f "$FMT" -S "ext:mp4:m4a" '
            '--no-mtime --no-part --force-overwrites -P "$HOME/Documents" '
            '-o "fed-dl.%(ext)s" -- "$U" >> "$LOG" 2>&1; FED_RC=$?; '
            'f=$(ls -t "$HOME/Documents"/fed-dl.* 2>/dev/null | sed -n 1p); ')


def logged_command(command):
    """Keep extraction/save logic intact; add a bounded log and one self-heal retry.

    Three changes, all inside the same shell command, no action or field added:

    1. The state files the shortcut reads back (fed-kind.txt, fed-ext.txt,
       fed-media) are written first, with the same contents as before, before
       the helper check and any pip work, so they exist even if a slow first-run
       install is killed.
    2. If yt-dlp leaves no file, update yt-dlp and the JS helpers once and run
       the identical command again. A working download never runs that update.
    3. yt-dlp's own output and exit status go to a bounded local log
       (Documents/fed-youtube-last.log, last 64 KB). The log is printed in
       a-Shell only when no file was saved, so a working download stays quiet.
    """
    if not command.startswith(START):
        raise ValueError("YouTube command differs from the authorized 1.7 baseline")
    for exact in (HELPERS, GUARD, DOWNLOAD):
        if command.count(exact) != 1:
            raise ValueError("YouTube command differs from the authorized 1.7 baseline")
    init = ('LOG="$HOME/Documents/fed-youtube-last.log"; '
            'printf "FED YouTube diagnostic\\n" > "$LOG"; ')
    helpers = ('pip show yt-dlp-ejs yt-dlp-apple-webkit-jsi >> "$LOG" 2>&1 || '
               'pip install -U "yt-dlp[default]" yt-dlp-ejs yt-dlp-apple-webkit-jsi >> "$LOG" 2>&1; '
               'pip show yt-dlp >> "$LOG" 2>&1; ')
    download = (_attempt() +
                'if [ -z "$f" ] || [ ! -s "$f" ]; then '
                'printf "\\nyt-dlp produced no file; updating yt-dlp and retrying once\\n" '
                '>> "$LOG"; '
                'pip install -U "yt-dlp[default]" yt-dlp-ejs yt-dlp-apple-webkit-jsi '
                '>> "$LOG" 2>&1; ' + _attempt() + 'fi; '
                'printf "\\nyt-dlp exit status: %s\\n" "$FED_RC" >> "$LOG"; '
                + TRIM + 'if [ -z "$f" ] || [ ! -s "$f" ]; then cat "$LOG"; fi; ')
    # Guard first, then the helper check; drop the originals from further down.
    out = command.replace(START, START + init + GUARD + helpers, 1)
    out = out.replace(HELPERS + GUARD, "", 1)
    return out.replace(DOWNLOAD, download, 1)


def expected_changes(good):
    targets = {a["WFWorkflowActionParameters"].get("UUID"): a for a in good}
    changes = {}
    for uuid, field in FIELDS.items():
        value = copy.deepcopy(targets[uuid]["WFWorkflowActionParameters"][field])
        if uuid == COMMAND_UUID:
            value["Value"]["string"] = logged_command(value["Value"]["string"])
        elif isinstance(value, str):
            value = MESSAGES[uuid]
        else:
            value["Value"]["string"] = MESSAGES[uuid]
        changes[uuid] = value
    return changes


def authorization(lock):
    entry = lock.get("authorized_exceptions", {}).get(EXCEPTION_ID)
    return bool(entry and entry.get("fields") == FIELDS
                and entry.get("user_words") == USER_WORDS)


def apply(actions, lock):
    if not authorization(lock):
        raise ValueError("Explicit user exception for these exact fields is missing")
    good = plistlib.loads((ROOT / "tests/fixtures/good-1.7.plist").read_bytes())["WFWorkflowActions"]
    original = {a["WFWorkflowActionParameters"].get("UUID"): a for a in good}
    changes = expected_changes(good)
    found = set()
    for action in actions:
        p = action["WFWorkflowActionParameters"]
        uuid = p.get("UUID")
        if uuid in changes:
            field = FIELDS[uuid]
            if p[field] not in (original[uuid]["WFWorkflowActionParameters"][field], changes[uuid]):
                raise ValueError("Unexpected pre-existing edit in authorized field " + uuid)
            p[field] = copy.deepcopy(changes[uuid])
            found.add(uuid)
    if found != set(FIELDS):
        raise ValueError("Authorized target actions are missing or renamed")


def comparison_view(actions, good, lock):
    """Accept only the exact approved edits; compare every other byte as before."""
    view = copy.deepcopy(actions)
    if not authorization(lock):
        return view
    originals = {a["WFWorkflowActionParameters"].get("UUID"): a for a in good}
    changes = expected_changes(good)
    for action in view:
        p = action["WFWorkflowActionParameters"]
        uuid = p.get("UUID")
        if uuid in changes and p.get(FIELDS[uuid]) == changes[uuid]:
            p[FIELDS[uuid]] = copy.deepcopy(originals[uuid]["WFWorkflowActionParameters"][FIELDS[uuid]])
    return view
