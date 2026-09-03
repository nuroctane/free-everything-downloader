# Changelog

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
