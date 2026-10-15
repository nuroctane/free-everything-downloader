# YouTube / Shorts findings, 2026-10-14

Status: **none of 1.7.4 to 1.7.7 is confirmed on a phone.** Threads (1.7.2's
server-failed recipe) is confirmed working by the user on 1.7.3. Nothing here is
on RoutineHub or `main`.

## 1. Audit of 1.7.3 (commit `61f47cd`)

Desktop checks all pass: `validate.py`, `test_input.py` (40 locked links x 5
outcomes), `audit.py`, `test_failure_diagnostics.py`, `test_extractors.py`
(live, 0 failures). `build_release.py` reproduces the committed plist except
for 5 random UUIDs in the new Threads block.

Items found:

- **Locked YouTube steps were edited under `authorized_exceptions`**, and
  `test_input.py` normalizes those exact fields through
  `failure_diagnostics.comparison_view`. The authorization rests on "yes, go
  ahead and do so" / "do your absolute best to fix it...".
- `test_failure_diagnostics.py` skips its 4 shell tests silently unless Git
  Bash is at `C:\Program Files\Git\bin\bash.exe` (they pass under Linux bash).
- `threads_tail.py` says "Meta's crawler user-agent"; the steps send Googlebot's.
- 1.7.3's YouTube command sent yt-dlp's output to a log and added a silent
  `pip install -U` + retry on failure, so a-Shell sat blank (the user's
  "hangs and doesnt complete with no error"). **1.7.4 restored the 1.7 command
  and notice byte for byte.**

## 2. Why YouTube shares failed on the phone (measured)

The user's notifications were always the server extractor's "Couldn't grab a
file from that link" followed by the sign-in tail. A link containing `youtu`
always enters the YouTube section and stops there, so the shortcut never had a
YouTube link. This was the same on 1.7, 1.7.3, 1.7.4 and 1.7.5.

Three throwaway probe shortcuts (`FED Link Check`, `2`, `3`; Get URLs / Expand
URL / Get Type / Get Details of Safari Web Page, then Show Result) were run on
the phone:

| Probe | Input on the phone |
|---|---|
| Short, Link Check 1 | one **PNG image, 4 KB, "unknown"**; Get URLs and Expand URL return the same PNG |
| Short, Link Check 2 (accepts only URLs/text) | the same 4 KB PNG |
| Normal video, Link Check 1 | the PNG **plus the screen's text**: "Open App", title, "@CyberpunkGame", likes, views, comments and the titles of *other* videos further down the page |
| Normal video, Link Check 3 | `Get Type` = **Text**; Get Details of Safari Web Page: "couldn't convert from Text to Safari Web Page" |

No link reaches the shortcut. The user says they are in the YouTube app.
Text that includes comments and other videos' titles is a whole-screen capture,
not a share payload (YouTube's Share > More sheet carries only the one video's
link). Apple documents that onscreen items are passed when a shortcut runs other
than from the share sheet (Siri, back tap):
<https://support.apple.com/guide/shortcuts/receive-onscreen-items-apd350ce757a/ios>.
How the user starts the shortcut is still unconfirmed.

Wrong turns, for the record: Expand URL was suspected first (YouTube keeps
`youtube.com/shorts/...` links intact on expansion, measured), then the
accepted input types (Link Check 2 disproved it), then a browser share
(the user is in the app).

## 3. What other RoutineHub YouTube shortcuts do

[YouTube Download (gluebyte)](https://routinehub.co/shortcut/15247/), 3.12.2,
2026-09-03, and [YouTube Shorts Downloader (chrunos)](https://routinehub.co/shortcut/12802/),
2.1, 2026-09-04, are run from YouTube's **Share > More** sheet, which hands over
the video link; the rest is an ordinary yt-dlp or server download.
[Gadget Hacks](https://ios.gadgethacks.com/how-to/shortcut-lets-you-download-youtube-videos-your-iphone-straight-from-source-no-shady-services-needed-0187537/)
gives the steps as "Share" > "More" > the shortcut and says that kind of
shortcut does not work from the Shortcuts app, a widget, a Home Screen icon or
Siri. RoutineHub pages and downloads sit behind a Cloudflare challenge from the
build machine; only `/api/v1/shortcuts/<id>/versions/latest` answered, so the
shortcuts themselves were not inspected.

**Next phone test:** on a Short in the YouTube app, Share > **More** > FED Link
Check. If SHARED shows a `youtube.com/shorts/...` link, the normal YouTube
steps already handle it.

## 4. Candidate builds on `claude/intelligent-cerf-j5dbv2`

| Build | Change | Phone result |
|---|---|---|
| 1.7.4 `07e73af` | YouTube command + failure notice back to 1.7 (fixes the silent a-Shell) | same server error (expected: no link) |
| 1.7.5 `4ae1e45` | tail block `YouTube original links`: Get URLs output contains `youtu` but userLink did not | same server error (no link at all) |
| 1.7.6 `c5321c2` | tail block `YouTube shares without a link`: title search + clipboard | not tested |
| 1.7.7 `563c723` | same block, finder moved into a-Shell (`scripts/yt_resolve.py`) | not tested |

1.7.7's no-link block runs only after a share already failed and only when the
input has no `http` at all. Screen text with an `@channel` and "Subscribe" is
URL-encoded into the 1.7 YouTube command; `yt_resolve.py` (base64-embedded, run
by a-Shell's python3 with its yt-dlp) uses a link in the text if there is one,
else lists the channel's Shorts and videos and picks the title matching the
caption on screen ("..."-truncated captions match as a prefix), else
`ytsearch1:`. Otherwise a YouTube link on the clipboard is used. Desktop run of
the real command under dash with real yt-dlp lookups: the Shorts screen text
resolved to `shorts/vkWx7J00MQY` (the right one of two near-identical
"Bros failing..." Shorts on @Brainfrog10), the trailer text to
`watch?v=RgvsbigEylQ`. A PNG-only share has nothing to identify the video.

Lock: every locked share link contains `http`, so on their failed paths the new
blocks run only comments and If/Otherwise/End If; X and Instagram are
byte-identical in every outcome. `test_input.py` gained reach tests for both
YouTube blocks; the full a-Shell count guard now ignores copies inside new
FMD+ blocks; `audit.py` knows `getclipboard`.

## 5. Open items for the user

- How the shortcut is started on the phone (Share > More, or Back Tap /
  Action Button / Siri).
- Whether 1.7.5's `YouTube original links` block stays (harmless, covers a
  mangled expansion that was never observed).
- The version number for whichever build ships.
- The 1.7.3 `authorized_exceptions` question in section 1.
