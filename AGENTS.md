# Agent instructions

This shortcut has real users who depend on it. Every update ships to them.
Breaking something that already works is worse than not shipping the feature.

## LOCKED PLATFORMS (hard rule from the user)

Once the user confirms a platform works on their iPhone, it is **locked**.
No agent may change the code that platform's shares run. Not a field, not an
added If check, not a comment, not a "harmless" cleanup. No exceptions.

- The list lives in `tests/locked-platforms.json` (today: **X** and
  **Instagram**, confirmed on 1.5.1), with sample share links for each.
- `scripts/test_input.py` walks every locked link through the new build and
  through the baseline and requires the executed steps to be byte-identical.
  The shared download/save/fallback steps (the server-extractor POST to the
  end of the shortcut) must be byte-identical too. `scripts/sign.py` runs it
  and refuses to sign on any difference. Do not weaken, skip, or edit this
  check to get a build through.
- New work goes only where locked platforms never run: inside another
  platform's own section (e.g. 1.5.1's `If userLink contains "facebook.com"`
  section), never on the shared path before or after it.
- If a fix is impossible without touching a locked path, stop and tell the
  user. Only the user can unlock a platform, in chat; record the date and
  their words in `tests/locked-platforms.json` when they do.
- When the user confirms another platform works on their phone, add it to
  the lock with its real share-link forms.

## How updates are handled

**A feature request is an addition, not a rewrite.** Do what was asked and
nothing else. If it isn't broken, don't touch it.

- Change only what the requested feature needs. No refactors, cleanups,
  "while I'm in here" fixes, renamed files, reworded messages, extractor
  changes, or tooling rewrites bundled into a feature.
- Found something else that looks wrong? Tell the user in your report as a
  separate item. Do not fix it unless they say to.
- Add the new behavior *next to* the working path. Never replace a working
  path to make room for it. Example: "make Brave shares work" means Brave gets
  handled and every app that already worked is untouched, not that the whole
  share-input step gets redesigned.
- Don't guess. If you can't tell why something fails, say so and ask for what
  would show it (the exact error text, what the user tapped, which app). Do not
  ship a theory as a fix.
- Before handing off a build, diff the shortcut (`shortcut/fed.unsigned.plist`)
  against the last version the user confirmed works. Every changed action must
  belong to the requested feature. If something else changed, remove it.

**When the user reports a regression:** put the last working version's
behavior back first. Don't pile a new attempt on top of the broken one.

## The share sheet: non-negotiable

Sharing a post to the shortcut must download it. Period.

- Never ask for a link, text, or any input when someone shares a post. No
  prompts, no "paste the URL", no "copy the link and try again".
- Native-app shares (X, Instagram, Facebook, Threads, TikTok, YouTube, and
  every other supported app) must keep working exactly as they do now.
- Browsers are not all Safari. Don't assume Safari is installed or is the
  default.
- Sign-in fallbacks must be obvious: open the post in its own app if it's
  installed, otherwise the user's default browser, and tell them plainly what
  to do.
- Where one platform downloads straight from the app, the others should too.
  That is the bar.

**Known-good baseline: 1.5.1** (commit `c3966fa`, RoutineHub iCloud
`1e4945fd5e834686b166491329d3928d`, stored as `tests/fixtures/good-1.5.1.plist`).
On 1.5.1, sharing from an app asks only for permissions and puts the media in
Photos. That is the intended behavior. 1.5.1 is never edited, and it is never
to be broken again.

1.6 looked fine but was broken: it was built from the old 1.4 base with
`scripts/build.py` and silently dropped 1.5.1's full a-Shell fallback (24
actions), so YouTube/Instagram failed for anyone without a-Shell mini. 1.6,
Codex's 1.6.1 and the 1.6.2 candidate were all deleted or rejected. None of them
is a base.

**Releases are built only with `scripts/build_release.py`**, starting from the
lock baseline (`tests/fixtures/good-1.7.plist`, RoutineHub 1.7, the build the user
confirmed on 2026-09-28), never from an older base: rebuilding confirmed code changes it.
New work is added as blocks wrapped in `FMD+ <name>` / `FMD- <name>` comments,
only where working shares of locked platforms never go.

Already in the confirmed baseline (locked):
- 1.5.1 for X and Instagram, byte for byte.
- Facebook section repaired in the Shortcuts app's own formats, plus a
  Threads/Facebook fallback for links that come back as
  `facebook.com/unsupportedbrowser` (`scripts/fb_section.py`).
- TikTok photo slideshows save the photos (`build_v15.patch_tiktok_photos`).

Added on top of it (not yet confirmed on the phone, so not locked):
- **Reddit share links** and **Mastodon posts** (`scripts/reddit_tail.py`), in
  the sign-in tail of the server-failed branch. Only a share that already
  failed in its own section AND on the server reaches that tail; X and the
  other twirrl sites always stop earlier, and working downloads stop in their
  own sections or the completed branch. Reddit `/s/` links are reopened with
  Facebook's crawler user-agent to get the post's `og:url`, then 1.5.1's own
  server-download steps (copied) run again. Mastodon posts on any server use the
  server's public `/api/v1/statuses/<id>`.

What the phone does (measured, 2026-09-28): its Expand URL sends a user-agent.
Instagram and Threads links behave identically for every user-agent (no UA:
both become `facebook.com/unsupportedbrowser`; any UA: both stay intact), and
Instagram works on the phone, so links arrive intact. Threads then downloads
through the server extractor, Facebook `/share/` links expand to `/reel/<id>/`
for the repaired Facebook steps, and Reddit `/s/` links usually expand to the
post. The unsupportedbrowser prelude and the Reddit block are safety nets; the
Mastodon block is the working path for Mastodon servers whose address does not
contain "mastodon" (the server extractor rejects every Mastodon post).

**The lock check covers every outcome.** For each locked share link,
`test_input.py` compares the executed steps against the baseline with the
platform's own section working or failing, and the server not reached,
completed or failed (5 cases). X and Instagram must be byte-identical in all of
them. For the other locked platforms, only on a path where the share already
failed on the server, the tail blocks may run side-effect-free checks
(comments, If checks, Match Text, Get Group) and nothing else. Tampering tests
(a comment on X's path, an extra step on X's failed path, a changed Threads
field, a notification on TikTok's failed path) are all refused.

**Store every step the way the Shortcuts app does.** Copy field shapes from
device-built shortcuts, never from old action docs. Proven on the user's phone:
Match Text reads its input from `text` (not `WFInput`), Get Group from
`matches`, Save to Photo Album needs an explicit `WFInput` and no album,
download URLs and Replace/URL Encode inputs are text fields, and a variable
inside a text field is a raw token (never wrapped twice). A step whose input
iOS can't read shows a blank "Text" box or stops with "Please choose a value
for each parameter in this action". `wf.native_*` builders produce these
shapes; `test_input.py` rejects anything else. Only store URLs in `userLink`
(Expand URL or a URL action output), never plain text.

**Every addition must be gated.** A Match Text / Replace Text / URL Encode that
runs on every share makes iOS prompt for "Text". `test_input.py` fails on any
ungated text action.

A new feature is a new addition in `build_release.py` plus a matching update to
`scripts/test_input.py` for that addition only. `build.py` refuses to run
without an explicit override because it starts from 1.4.

## Testing and what you can claim

- Desktop checks (validate, audit, regex, live extractor probes, signing)
  catch mistakes. They do not prove the shortcut works on an iPhone. Never say
  "tested", "verified", or "works" about the share sheet unless the user tested
  it on their phone.
- When handing off a build, tell the user exactly which shares to try. For any
  input/share change that is at minimum: the thing they asked to fix, plus X,
  Instagram, and YouTube from their apps.

## Versions

- The user picks the version number. If they pick a different number than the
  one you signed, re-sign with their number and get a fresh iCloud link before
  shipping. The version inside the shortcut, on RoutineHub, and in the listing
  description must all match.
- Always update the RoutineHub listing description to the new version when
  shipping.
- Keep `Settings.shortcut.version` at `9.0.0` (API gate value).

## Shortcut release prep (do this automatically)

When a build is ready, or the user says "normal process" or "drive":

0. Build with `python -X utf8 scripts\build_release.py --version <X.Y.Z> --date <YYYY-MM-DD>`.
1. Run `python -X utf8 scripts\validate.py`, `scripts\test_input.py`, the audit, and `scripts\test_extractors.py`.
   `test_input.py` enforces the platform lock, native step formats and the additions layout.
   `sign.py` refuses to sign if it fails. Never edit the lock check to get a build through.
2. Run `python -X utf8 scripts\sign.py`.
3. Verify `H:\My Drive\FREE Media Downloader.shortcut` exists and starts with the `AEA1` HubSign header.
4. Tell the user: Files → Drive → My Drive → `FREE Media Downloader.shortcut`, what to test, then send the fresh iCloud link when they're happy.

Do not ask the user to upload files or search iCloud Documents. Do not drop the
file in iCloud Drive. Do not inspect Cursor sessions, transcripts, or Cursor
state unless the user explicitly asks.

If no fresh iCloud link exists yet, stop after the Drive handoff. Do not commit,
push, create a RoutineHub version, or claim anything shipped. Apple mints iCloud
links on the user's iPhone/iPad; you can't make one. Never reuse an old iCloud
link for a new build.

## Ship / push / deploy (mandatory)

When the user says **ship**, **push**, **deploy**, **put on main**, **release**, **publish**, **gh**, **rh**, or similar:

1. Read **`C:\Users\david\.agents\SHIP.md`**
2. **RoutineHub first.** If they gave an `icloud.com/shortcuts/` URL or said rh, run that before any git:

```powershell
python -X utf8 $env:USERPROFILE\.agents\shortcut-rh.py --repo free-everything-downloader --link <icloud-url> --version <X.Y> --changes "<no emojis>"
```

That creates the version first. Get Shortcut must already be that version before any listing copy is posted. Never listing-only. Never leave users on an older download while the page claims a newer build.

3. Then GitHub: `powershell -File $env:USERPROFILE\.agents\ship.ps1 -Repo free-everything-downloader -SkipRh [-Message "..."]` (or pass `-ICloudLink` if RH is not done yet so step 0 runs inside the script)

**Pipeline after RH:** Commit on Laboratory → Push `origin main` → Backup 7z to `D:\BACKUP\CODE Backups\free-everything-downloader\`
Pattern: `free-everything-downloader_YYYY-MM-DD_<sha>_<slug>.7z` (exclude target, .git, node_modules, dist, .next)

Never bare-push without backup. Report RH version, commit, remote, and full backup path.

If the RoutineHub web session is logged out, say so in one line and ask the user to log in. Don't create a duplicate version when retrying.
