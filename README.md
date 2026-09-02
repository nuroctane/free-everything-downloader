# FREE Media Downloader

iOS Shortcut. Share a link. Save the file. No key. No paywall. No checkout.

Canonical unsigned source: `shortcut/fed.unsigned.plist`. HubSign writes the `.shortcut` to Google Drive (`H:\My Drive`). RoutineHub is a separate publish step, not this repo's ship pipeline.

Version **1.2** lives in the first comment inside the shortcut. Open it in the Shortcuts app to see it. Update from RoutineHub when that page is newer.

## What it does

- **TikTok:** no-watermark file when the source lets it. Straight to Photos.
- **YouTube:** always yt-dlp inside **a-Shell mini**. Lands in a-Shell mini → Files → Documents.
- **Instagram:** same yt-dlp path. Original file. No watermark overlay.
- **X / Bluesky / Mastodon:** secondary extractor when the first one fails.
- **Also:** Facebook, Threads, Reddit, Pinterest, LinkedIn, Snapchat, Vimeo, DailyMotion, SoundCloud, YouTube Music.
- **Everything else:** first extractor, then the others. Never a checkout.
- **Sign-in wall:** opens the post in Safari (or the native app, if that URL hands off). Sign in. Share the post again.

## Apps you need

| App | Why |
| --- | --- |
| **a-Shell mini** | YouTube and Instagram. The shortcut calls this app, not full a-Shell. [App Store](https://apps.apple.com/app/a-shell-mini/id1543537943) |
| **Safari** | Built in. Used when a post wants a session. |
| **YouTube / Instagram / TikTok / X** (optional) | Sign in there if you already use those apps. The share sheet can hand the URL to the app. |
| **Photos** | TikTok (and other stills/video the first extractor saves to Camera Roll). |
| **Files** | Audio from the first extractor; yt-dlp output lives under a-Shell mini. |

Full **a-Shell** is a different app (`a-Shell`, not `a-Shell mini`). This shortcut does not call it. You do not need both.

## One-time permissions

The first save to Photos, the first save to Files, the first network call, and the first a-Shell mini run each ask once. Approve them. yt-dlp itself may install on the first YouTube or Instagram share (pip inside a-Shell mini). That is also once.

If a site wants cookies, put a Netscape `cookies.txt` in a-Shell mini's Documents folder. The command uses it when that file is present.

## Build / sign

```powershell
python -X utf8 scripts\validate.py
python -X utf8 scripts\sign.py
```

`scripts/sign.py` writes the signed file to `H:\My Drive` as `FREE Media Downloader.shortcut`. Add it from Files → Drive → My Drive. Do not duplicate the file.

## RoutineHub

Listing: https://routinehub.co/shortcut/26384/

Copy lives in `listing.md`. Updating RoutineHub needs a logged-in session plus a fresh iCloud share link from the device. Ship on GitHub does not touch RoutineHub.

## Install on iPhone or iPad

1. Install a-Shell mini if you want YouTube or Instagram.
2. Files → Drive → My Drive → **FREE Media Downloader** → Add Shortcut.
3. Open a post → Share → FREE Media Downloader.
4. Approve the first Photos / Files / a-Shell prompts.

Paste a URL and run it from Shortcuts the same way.
