# Why Facebook is slow here, and why photos did nothing

Two reports, one root cause each. Both were measured against the live services on
2026-09-20; every number below comes from a real request made from this repo's
`scripts/test_extractors.py` or from a logged audit of the shortcut's own backend.

---

## 1. "Why does it take long to download videos from Facebook reels?"

Because Facebook was the only site in the list with **no code of its own**.

Every other site had a branch: TikTok called tikwm, YouTube and Instagram called
yt-dlp in a-Shell mini, X had a fallback backend. Facebook had nothing. A Reel or a
video fell straight through to the generic server-side extractor at
`api.allmediadownloader.com`, which works like this:

1. `POST /download` with the link → the service returns a **job id**.
2. The shortcut then **polls** `GET /download/<id>` and waits for the job to finish.
3. The poll loop was **500 iterations with a 3 second sleep** — a 25 minute ceiling.
4. Only when the job says `completed` does the shortcut download the file and save it.

So a Facebook Reel cost a round trip to a third-party server, a server-side page
fetch of a logged-out Facebook page, and then a 3-second-granularity wait for the
answer. Measured time to `completed`:

| Case | Server extraction time | With the old 3 s poll |
| --- | --- | --- |
| Facebook video (`watch/?v=`) | 2.1–2.8 s | 3–6 s |
| Facebook Reel (typical) | 2.7 s | 3–6 s |
| Facebook Reel (slow one) | 8.0 s | 9–12 s |
| X / Twitter video (for comparison) | 0.9 s | ~1 s |

That is the whole answer: for X the server answers inside the first poll, for
Facebook it needs several seconds of real work, and the 3-second sleep meant the
user almost always waited at least one extra beat on top of it. When a job never
reached `completed`, the shortcut kept polling for up to **25 minutes** before
giving up. That is the "it takes long" case, and it is a Facebook-only shape:
Facebook is the site that makes the server do the most work.

**Fixed in 1.5** — Facebook no longer queues a job at all.

A Reel/video is resolved on the phone from Facebook's own video player endpoint,
which returns the playable file URL directly:

```
GET https://www.facebook.com/video/embed?video_id=<id>
User-Agent: facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)
  -> "hd_src":"https:\/\/video.faus1-1.fna.fbcdn.net\/...mp4"   (unescape, download)
```

The `User-Agent` matters: with an ordinary iPhone Safari user agent that endpoint
answers `302` and yields nothing, and a logged-out Facebook page returns a
JavaScript shell with **no media URL at all** — which is exactly the state the old
code was stuck in. As a crawler, Facebook serves the player payload: three requests,
~0.4–0.8 s end to end, first bytes of the mp4 in 55–90 ms, no cookies, no login.

The fallback also stopped being silly: the poll cadence is now **1 s × 60** instead
of **3 s × 500**, so even a job that never completes now costs a minute, not
twenty-five.

---

## 2. "I cannot download photos from Facebook… nothing happened"

Facebook photos were failing **server-side**, and the shortcut then did something
that looked like nothing.

The extractor backend does not support photo URLs. Every shape of a Facebook photo
link was sent to it and every one came back the same way:

| URL sent | Backend answer | Time |
| --- | --- | --- |
| `facebook.com/photo?fbid=<id>` | `{"status":"failed","error":"invalid media url"}` | 0.7–0.9 s |
| `facebook.com/photo.php?fbid=<id>` | `{"status":"failed","error":"invalid media url"}` | 0.7–0.9 s |
| `facebook.com/permalink.php?story_fbid=<id>` | `{"status":"failed","error":"invalid media url"}` | 0.7–0.9 s |

The shortcut only saved files in the `status == "completed"` branch, so a photo
produced no file, no error dialog, and then it fell into the "this post wants a
sign-in" path: it opened the post in Safari and stopped. Signing in could never
help, because the failure was never a login wall — the backend simply cannot read
photo posts. That is the report, exactly: *logged in, pasted the link, nothing
happened.*

**Fixed in 1.5** — photos now come from Facebook's public post embed, on the phone:

```
GET https://www.facebook.com/plugins/post.php?href=<url-encoded post/photo url>
User-Agent: facebookexternalhit/1.1 (...)
  -> <img class="_1p6f ..." src="https://lookaside.fbsbx.com/lookaside/crawler/media/?media_id=<id>">
GET that lookaside URL with the same crawler user agent   -> image/jpeg, up to 400 KB
```

Verified live on `photo?fbid=`, `photo.php?fbid=`, `photo/?fbid=` and post
permalinks — all four saved a real JPEG (396,010 bytes in the test case), and the
whole path is two requests, ~0.5 s. Two user-agent notes: the crawler user agent is
required on **both** requests (the image URL answers with a 388-byte JavaScript
redirect for anything else), and a desktop Chrome user agent makes Facebook answer
`400`. Multi-photo posts save every photo the embed exposes; if an embed is
disabled, the link falls through to the server extractor as before.

The shortcut also no longer goes quiet on a real failure: the toast now reads
*"Couldn't grab a file from that link. If the post is private or age-restricted,
sign in and share it again."* instead of dumping raw JSON, and the Safari sign-in
path is now a last resort rather than the first thing a photo hit.

---

## What to tell people asking

> Facebook is the one site where a downloader has to ask Facebook for the file one
> step at a time, and the old build did that through a server that had to fetch the
> page itself. 1.5 asks Facebook's own player directly, so a Reel lands in about
> half a second instead of waiting on a job.
>
> Photos were a different bug: the server extractor we fell back on does not accept
> photo links at all — it answers "invalid media url" — and the old build treated
> that as "this post needs a login", opened Safari and stopped. That is why signing
> in changed nothing. 1.5 reads photo posts from the public embed instead, so no
> sign-in is involved.

## How this is verified

`python -X utf8 scripts/test_extractors.py` re-runs the exact HTTP recipe each
branch of the shortcut implements — Facebook reel/video/photo/post, X, TikTok,
Mastodon, Bluesky, Pinterest — and fails if any recipe stops returning a
downloadable media file. Run it before shipping a new version; these endpoints are
third-party surfaces and they do change.
