# FREE Media Downloader

iOS Shortcut. Share a link. Save the file. No key. No paywall. No checkout.

Canonical unsigned source: `shortcut/fed.unsigned.plist`. HubSign writes the `.shortcut` to Google Drive (`H:\My Drive`). RoutineHub is a separate publish step, not this repo's ship pipeline.

Version **1.5** lives in the first comment inside the shortcut. Open it in the Shortcuts app to see it. Update from RoutineHub when that page is newer.

## What it does

Most sites now resolve **on the phone in one or two requests**. Only a miss falls through to a server-side job, and that job is capped at a minute.

| Site | How it resolves | Measured |
| --- | --- | --- |
| **Facebook video / Reel** | Facebook's own player: `video/embed` → `hd_src`/`sd_src` | ~0.4–0.8 s |
| **Facebook photo / multi-photo** | public post embed → lookaside image | ~0.5 s |
| **X / Twitter** | `api.fxtwitter.com` → `media.all[].url` — video, GIF and every photo | ~0.4 s |
| **Bluesky** | public `getPostThread`; video comes back as the original MP4 blob | ~0.1–0.4 s |
| **Mastodon** | the instance's own `/api/v1/statuses/<id>` | ~0.1 s |
| **Pinterest** | public pin widget (720p mp4 for video pins) | ~0.1–0.3 s |
| **TikTok** | tikwm — no-watermark file when the source lets it | ~0.1–0.6 s |
| **YouTube / YouTube Music** | yt-dlp in **a-Shell mini** — video to Camera Roll, audio to Files | app switch |
| **Instagram** | yt-dlp in a-Shell mini — original file, no watermark overlay | app switch |
| **Threads, Reddit, LinkedIn, Snapchat, Vimeo, DailyMotion, SoundCloud** | server extractor, then the other free backends | ~1–8 s |

Video and photos go to Camera Roll. Audio goes to Files. No album.

Sign-in walls only apply to genuinely private posts now: if a post is private or age-restricted the shortcut opens it in Safari (or the native app), you sign in, you share it again.

## Apps you need

| App | Why |
| --- | --- |
| **a-Shell mini** | YouTube and Instagram only. The shortcut calls this app, not full a-Shell. [App Store](https://apps.apple.com/app/a-shell-mini/id1543537943) |
| **Safari** | Built in. Used when a post wants a session. |
| **YouTube / Instagram / TikTok / X** (optional) | Sign in there if you already use those apps. The share sheet can hand the URL to the app. |
| **Photos** | Video and images. Save to Camera Roll. No album. |
| **Files** | Audio only. |

Full **a-Shell** is a different app (`a-Shell`, not `a-Shell mini`). This shortcut does not call it. You do not need both.

Facebook, X, Bluesky, Mastodon, Pinterest and TikTok never touch a-Shell mini.

## One-time permissions

The first save to Photos, the first save to Files, the first network call, and the first a-Shell mini run each ask once. Approve them. yt-dlp itself may install on the first YouTube or Instagram share (pip inside a-Shell mini). That is also once.

If a site wants cookies, put a Netscape `cookies.txt` in a-Shell mini's Documents folder. The command uses it when that file is present.

## Build / sign / verify

```powershell
python -X utf8 scripts\validate.py         # structure, version gates, every site path
python -X utf8 scripts\test_extractors.py  # live-verifies each extraction recipe
python -X utf8 scripts\test_extractors.py --regexes   # offline pattern matrix
python -X utf8 scripts\sign.py             # HubSign -> H:\My Drive
```

`scripts/sign.py` writes the signed file to `H:\My Drive` as `FREE Media Downloader.shortcut`. Add it from Files → Drive → My Drive. Do not duplicate the file.

Useful extras:

```powershell
python -X utf8 scripts\dump.py --grep facebook   # readable action graph
python -X utf8 scripts\build_v15.py --check       # did the 1.5 fast paths land?
```

`Settings.shortcut.version` (9.0.0) is the server extractor's **client gate**, not
the release number. Bumping it down makes every server extraction return HTTP 426.
The user-facing release number is `Settings.version`, and `validate.py` fails if the
two get mixed up.

## RoutineHub

Listing: https://routinehub.co/shortcut/26384/

Copy lives in `listing.md`. Updating RoutineHub needs a logged-in session plus a fresh iCloud share link from the device. Ship on GitHub does not touch RoutineHub.

Facebook speed and photo analysis: `docs/facebook-speed.md`.

## Install on iPhone or iPad

1. Install a-Shell mini if you want YouTube or Instagram.
2. Files → Drive → My Drive → **FREE Media Downloader** → Add Shortcut.
3. Open a post → Share → FREE Media Downloader.
4. Approve the first Photos / Files / a-Shell prompts.

Paste a URL and run it from Shortcuts the same way.
