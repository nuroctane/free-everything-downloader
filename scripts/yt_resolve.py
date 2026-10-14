# Runs inside a-Shell (python3 + the yt-dlp it already installs), never on the
# desktop build. Input: argv[1] = URL-encoded text the share handed over (the
# YouTube app can give the shortcut only the text on screen). Output: one
# YouTube URL (or a ytsearch1: query) on stdout, nothing if no match.
# Keep it free of single quotes: youtube_tail embeds it base64-encoded.
import re, sys, unicodedata, urllib.parse
from difflib import SequenceMatcher

text = urllib.parse.unquote(sys.argv[1] if len(sys.argv) > 1 else "")
link = re.search(r"https?://[^\s\"<>]*youtu[^\s\"<>]*", text)
if link:
    print(link.group(0))
    sys.exit(0)


def norm(s):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", s)).lower()


lines = [l.strip() for l in text.splitlines() if l.strip()]
handles = []
for h in re.findall(r"@([A-Za-z0-9._-]+?)(?=Subscribe|\s|$)", text, re.M):
    if len(h) >= 3 and h not in handles:
        handles.append(h)
captions = []
for l in lines:
    cut = l.endswith("...") or l.endswith("…")
    n = norm(l[:-3] if l.endswith("...") else l.rstrip("…"))
    if len(n) >= 6 and not l.startswith("@"):
        captions.append((n, cut))
sys.stderr.write("FED: handles %s, %d caption lines\n" % (handles[:3], len(captions)))

best = (0.0, None, "")
if handles and captions:
    import yt_dlp
    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": 300,
            "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        for h in handles[:3]:
            for tab in ("shorts", "videos"):
                try:
                    info = ydl.extract_info("https://www.youtube.com/@%s/%s" % (h, tab), download=False)
                except Exception as e:
                    sys.stderr.write("FED: %s/%s: %s\n" % (h, tab, str(e)[:120]))
                    continue
                for e in info.get("entries") or []:
                    title, vid = e.get("title") or "", e.get("id")
                    nt = norm(title)
                    if not vid or not nt:
                        continue
                    for n, cut in captions:
                        target = nt[:len(n)] if cut else nt
                        score = SequenceMatcher(None, n, target).ratio()
                        if score > best[0]:
                            url = ("https://www.youtube.com/shorts/%s" if tab == "shorts"
                                   else "https://www.youtube.com/watch?v=%s") % vid
                            best = (score, url, title)
            if best[0] >= 0.97:
                break
sys.stderr.write("FED: best match %.2f %s %s\n" % best)
if best[1] and best[0] >= 0.85:
    print(best[1])
    sys.exit(0)
# Last resort: the line right above the @channel line, plus the channel.
m = re.search(r"(?m)^([^\r\n]+)\r?\n@([A-Za-z0-9._-]+?)(?:Subscribe)?[ \t]*$", text)
if m:
    print("ytsearch1:%s %s" % (m.group(1).strip(), m.group(2)))
