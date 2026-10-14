# RoutineHub feedback investigation — 2026-10-13

Reports: Merry-Knight-2609 (repeated, ambiguous sign-in instructions), Elc29
(certain YouTube videos fail despite YouTube-app login), and
Robust-Scorpion-2607-17457 (Threads says it is opening the post but nothing
opens). Source: https://routinehub.co/shortcut/26384/#feedback
No failing post URLs or terminal logs were available from the user.

## Published artifact and preserved behavior

RoutineHub serves 1.7, release ID 59987. Its Get Shortcut link resolves to
https://www.icloud.com/shortcuts/b7c7868e0eda4cdb9620572e1b7fe115.
The published payload has 649 actions. Its YouTube section and sign-in tail
match the local source in the relevant fields. Import/export differences
elsewhere were saved to `dist/rh-investigation-roundtrip-diff.json` and were
not changed as part of this investigation.

The existing lock check passed for all 16 locked platforms (40 share links,
five modeled outcomes). This is a control-flow comparison, not an iPhone test.
No shortcut, builder, lock file, listing, or release was changed.
This describes the initial investigation; the authorized candidate below was
prepared afterward.

## Code findings

1. Actions 280–281 react to server status `failed` with advice to sign in. The
   later tail (635–640) states that the post requires login, opens `userLink`,
   waits for return, and repeats that advice. It does not inspect the server's
   error or establish that authentication caused the failure. A non-authentication
   extraction failure therefore gets the same message.
2. Ordinary intact Threads URLs bypass the direct Threads recipe because it
   lives inside the Facebook/unsupportedbrowser section. They use the server.
   This matches the documented 1.7 routing; it is not a new regression proven
   by this investigation.
3. Published action 637 opens `userLink` with a URL coercion. The preceding
   notification claims it is opening the post before that action runs. No step
   checks that the app/browser opened or that a session changed. The reported
   iOS handoff failure remains unreproduced.
4. YouTube's own branch (58–89) stops at action 88, including when both a-Shell
   attempts leave `fedKind` as `missing`. An ordinary YouTube URL should not
   reach the shared sign-in tail. A sign-in error inside a-Shell must be
   distinguished from a FED notification before diagnosing the report.
5. The YouTube shell command checks whether the two helper packages are
   installed and updates dependencies only if that presence check fails. It
   does not refresh an existing installation, check compatible versions, or
   retain the downloader's exit status/error in a file that FED can read.
   Dependency age is a plausible contributor, not the established cause of
   the users' failures. The command supplies authentication only through an
   optional `Documents/cookies.txt`; it does not import the YouTube app session.

## Small desktop probes

- Public Threads control `@kfury/post/DaGcWDwj8tW`: direct crawler recipe
  produced media and a ranged GET returned HTTP 206, video/mp4, 262144 bytes.
- Requests to the server with Python's default user-agent returned HTTP 403
  (`error code: 1010`). Adding browser user-agents resolved that probe limitation.
  Both jobs for this post completed with one media item. The initial 403 is
  not evidence that the server is broadly broken or that users saw it.
- Public Threads control `@zuck/post/Ddt7cL5EfUG`: one further server job
  completed with nine items. No media from that job was downloaded.
- Payloads and results are in ignored `dist/rh-investigation-*.json` files.
  These desktop probes do not reproduce the affected users' iOS environment.

## Next steps and scope

Obtain the real failing downloader error before changing extraction behavior.
A targeted diagnostic change could retain YouTube's error/exit status and
dependency versions. The generic failure tail needs error-based wording
instead of an unconditional authentication claim. The Threads handoff requires
an on-device failure observation; no proven code fix for it exists yet.

YouTube, Threads, and the shared tail are protected by the platform lock.
Any diagnostic or repair to those executed steps requires the user's explicit
unlock or a precise exception. Do not weaken the checks, rewrite the input
schema, or change successful paths to get an unproven fix through.

## Authorized 1.7.1 diagnostic candidate

**Diagnostic-only; blocked from release.** The user explicitly requires the
reported failures to be resolved before publishing. Logging and message
changes do not establish that. Do not request a publishing link for this build.

The user authorized the narrow exception with "yes, go ahead and do so" and
selected 1.7.1. The date, quoted authorization, context, and exact four allowed
UUID/field pairs are recorded in `tests/locked-platforms.json`.

Only four runtime fields change: YouTube's command text, its failure notice,
and the two notifications in the late shared failure tail. The early failure
notice also runs on X and was retained byte-identically after the independent
preservation test caught it. No actions are inserted, removed or reordered.
Input handling, download arguments other than progress suppression for the
log, a-Shell intents, formats, retries, URLs and save steps remain intact.

The command saves helper/yt-dlp package versions, downloader output and exit
status in `Documents/fed-youtube-last.log` inside the a-Shell app that runs it.
It overwrites the previous log, suppresses progress noise, trims to the last
65536 bytes, and displays the retained output in a-Shell. Both mini and full
a-Shell execute the same YouTube command; each has its own Documents folder.
No cookies file is read or uploaded by diagnostics (the original downloader's
optional cookies behavior is unchanged). Installed dependencies are not
refreshed by this candidate.

The late failure messages no longer claim that authentication caused the
failure. They describe an attempted opening of the post and invite a failure
report if a public post still cannot download. Open URL and Wait to Return
themselves are unchanged; the reported iOS handoff failure is not claimed fixed.

`scripts/failure_diagnostics.py` applies exact edits to the confirmed baseline.
The lock checker accepts only those exact approved values in those four
fields; arbitrary edits to them or to other fields still fail. Separate tests
compare X/Instagram execution without exception normalization and exercise the
actual shell command with stubbed downloads in temporary folders: success,
failure, and a deliberately oversized error. These are desktop checks, not
iPhone execution.

Device handoff checks: share a YouTube video and confirm saving; inspect
`fed-youtube-last.log` for package versions and exit status (0 for success);
try an affected video if one becomes available. Also share X, Instagram and
Threads posts from their apps. On a failed Threads/server download, check the
new wording and whether the attempted app/browser opening happens. If it
doesn't, that is still an unresolved handoff failure, not successful testing.

## 1.7.2 repairs (2026-10-13)

The user rejected the diagnostic build ("we arent shipping shit without
resolving the failures") and told this session to fix the reported failures
without a reproduction. Nothing was posted to RoutineHub; no user was replied
to. `docs/rh-reproduction-requests-2026-10-13.md` was not sent.

Two repairs, both on the paths the reports describe.

### Threads (feedback 46328)

Finding 2 above is the cause of the report. `threads_tail.py` adds one block,
"Threads server-failed posts", in the sign-in tail of the server-failed branch,
gated on `userLink contains "threads."`. It runs the exact recipe the confirmed
baseline already runs for Threads inside the Facebook section. So an intact
threads.com link that failed on the server now downloads on the phone instead of
being told to sign in, and `Open URL` is no longer reached on that path.

Why that is safe: X and Instagram never reach the tail (they stop at 503 and 121
respectively); the locked Threads links are answered by the Facebook section's
own copy of the recipe, which stops at its "no media" notice, so they never
reach this block either; and on every other platform's failed path the gate is
false, so only the block's two comments, its If and its End If execute, which is
what the `failure_path_allowance` entry requires. `test_input.py` fails if a
completed download ever enters the block.

### YouTube (feedback 46291/46292/46298)

The command wrote `fed-kind.txt`, `fed-ext.txt` and `fed-media` - the files the
shortcut reads back with GetFileIntent - *after* the helper check and any pip
work. A first-run install that is slow or is killed leaves them unwritten, and
the shortcut then dies on a raw missing-file error instead of its own failure
notice. That matches the reported "it says the file can't be found". The same
three files, with the same contents, are now written first.

If yt-dlp leaves no file, the command updates yt-dlp and the JS helpers once and
runs the identical download again; a working download never pays for the update.
yt-dlp's output and exit status now land in `Documents/fed-youtube-last.log`
(last 64 KB) and in a-Shell's output, so a failed video shows the actual reason.

Not fixed, and not claimed: a video that yt-dlp refuses without a session
("Sign in to confirm you're not a bot") still needs `Documents/cookies.txt`.
FED cannot use the YouTube app's session. If the reports persist after the phone
test, that error text is the evidence to ask for.

## 1.7.3 audit fixes (2026-10-13)

An audit of the 1.7.2 diff found two things worth fixing before a phone test.

**Threads dead end.** 1.7.2 reused the Facebook section's Threads recipe
verbatim, and that recipe stops in *every* branch once the post id matches -
including the branch where no media was found. So a Threads post the recipe
could not parse showed "No photo or video found in this Threads post" and
stopped: no `Open URL`, no sign-in handoff, the opposite of the report's
request. `fb_section.threads_recipe` now takes an optional `on_no_media`
callback; the Facebook section (the phone-confirmed path) calls it with no
argument, so its behavior is byte-identical, and the tail passes a handoff that
notifies, opens a real URL action output, waits, tells the user to share again,
and stops.

**The tail's own `Open URL` takes the `userLink` variable and coerces it** - the
same shape the report says never opens. The new handoff opens a `URL` action
output instead, which is the shape every working open in this shortcut uses.

**YouTube log noise.** 1.7.2 printed the whole 64 KB diagnostic log into
a-Shell on every run, including successful ones. It now prints only when no file
was saved. The log itself is unchanged.

Still not fixed, and not claimed: action 281 ("sign in and share it again")
fires before the Threads block and also runs on X, so the locked paths forbid
changing it - a Threads user can be told to sign in and then get "Saved from
Threads." in the same run. Unlocking that wording is a user decision.

### What was verified, and what was not

Passing: `validate.py`, `test_input.py` (16 locked platforms, 40 links x 5
outcomes), `audit.py` (clean, one pre-existing Mastodon warning also present
when the baseline is compared with itself), `test_extractors.py` (live probes,
including the Threads public-video control), and the shell tests, which now
cover the state-file ordering, the retry after a first attempt that leaves no
file, and that a working download does not retry.

Not verified: anything about an iPhone. No phone test has been run on 1.7.2. The
reports' exact posts were never reproduced, so the Threads repair is proven to
run on the right path and to be unable to touch a working one - not proven to
fix the reporter's specific post. That is what the phone test decides.
