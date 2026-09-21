# Changelog

## 1.5.1 (candidate, not published)

- Full a-Shell now works too. Both apps expose the same Execute command / Get file intents under different bundle ids, and the shortcut only ever addressed a-Shell mini, so the full app silently could not run the yt-dlp path. Mini still runs first; full a-Shell is only used when mini leaves the result marker at "missing". Install either app - not both.
- Facebook video id regex rewritten for ICU. The old form matched in Python and failed on /reel/ and /videos/ in the engine Shortcuts actually uses, so a Reel would have skipped the fast path and gone back to the slow server job. Group 1 now captures reel, reels, video, videos, watch?v=, and video.php. Photos still do not match it.
- scripts/test_extractors.py --regexes now runs every stored pattern in Node ICU and requires group 1. A Python-only pass is no longer enough.
- Facebook only: Reels/videos from the video player, photos from the public post embed, plus a 1 s x 60 fallback poll.
- X, Bluesky, Mastodon and Pinterest are left exactly as 1.4. Their 1.5 on-device fast paths were removed after the X path regressed share-sheet runs.
- Fixes the regression itself. The Wait duration inside the poll loop was written as the string "1.0" instead of the number 1.0. iOS blanks a string in that field, so the shipped 1.5 had a required value empty on every run - which is what made the shortcut stop and prompt instead of taking the shared post. The 1.4 file had a real number (3.0). It is a real number again (1.0).
- validate.py now type-checks the Wait duration and the poll ceiling, because comparing stringified values hid this: "1.0" and 1.0 both printed as 1.0.

## 1.5 (rolled back)

- Added on-device fast paths for X, Bluesky, Mastodon and Pinterest, and the two Facebook fixes.
- **Regression:** on a real device the X fast path made the shortcut ask for the link instead of using the shared post. Rolled back to 1.4 as version 1.4.1 on RoutineHub. The Facebook fixes are unaffected and return in 1.5.1.

## 1.5

- **Facebook is fast now.** Reels and videos resolve from Facebook's own video player (`video/embed`) instead of a server-side job. Three requests, ~0.4–0.8 s, no polling, no sign-in.
- **Facebook photos work now.** They used to fail on the backend with `invalid media url`, which the shortcut misread as a login wall: it opened Safari and saved nothing. Photos and multi-photo posts now come from the public post embed (~0.5 s). The crawler user agent is required on both requests.
- **New direct paths**, one request each: X (`api.fxtwitter.com` — video, GIF and all photos, including 4-photo posts), Bluesky (public `getPostThread`, video pulled as the original MP4 blob rather than the HLS playlist), Mastodon (the instance's own API, boosting handled), Pinterest (public pin widget, 720p mp4 for video pins).
- **The server fallback stops hogging the wait.** Poll cadence 3 s → 1 s and 500 polls → 60, so the worst case is a minute instead of 25 minutes.
- **Honest failures.** A real extraction failure now says so instead of dumping raw JSON, and the Safari sign-in path is a last resort rather than the first thing a Facebook photo hit.
- Housekeeping: build tooling in `scripts/` (`wf.py` action-graph kit, `build_v15.py`, `dump.py`, `test_extractors.py`), and `validate.py` now checks control-flow nesting, UUID uniqueness, the 9.0.0 client gate, and that every site path is still present.

## 1.4

- Video and images always Save to Camera Roll. Audio always Save to Files. YouTube and Instagram included. No album.
- After yt-dlp finishes in a-Shell mini, the shortcut pulls the file back and saves it the same way as every other site.

## 1.3

- YouTube on a-Shell mini asked yt-dlp to merge separate video and audio with ffmpeg. a-Shell mini does not ship ffmpeg, so no playable file was written. The command now takes a single already-mixed file unless ffmpeg is actually there.
- First YouTube or Instagram run also installs yt-dlp-ejs and the Apple WebKit JS helper YouTube requires now. Without that, yt-dlp dies with a bot check or "file not found".

## 1.2

- Renamed to FREE Media Downloader.
- Version 1.2 is in the first comment and in Settings so you can see it in the Shortcuts app.
- Listing names the sites this shortcut covers.
- Signed file lives on Google Drive (`H:\My Drive`), not iCloud Documents.

## 1.1

- YouTube always uses yt-dlp in a-Shell mini (no first-extractor detour).
- Instagram uses yt-dlp for the original file (no watermark overlay).
- First-run pip install of yt-dlp inside a-Shell mini; optional `Documents/cookies.txt`.
- Sign-in wall opens Safari (or the native app via the URL) and waits. Share again after.
- Listing names a-Shell mini, Safari, Photos, Files, and the optional native apps. One-time permission prompts called out.

## 1.0

- Initial release. Free. No key. No paywall.
