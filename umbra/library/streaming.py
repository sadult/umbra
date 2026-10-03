"""Streaming bridge — YouTube Music / YouTube (via yt-dlp) and Spotify link import.

Spotify does not allow third-party apps to stream its audio. Umbra imports Spotify
tracks/playlists (title + artist) and plays the best match from YouTube.
"""
import html
import json
import re
import threading
import time
import urllib.parse
import urllib.request

try:
    import yt_dlp
except Exception:
    yt_dlp = None

try:
    from ytmusicapi import YTMusic
except Exception:
    YTMusic = None

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
_resolved = {}   # path -> (expires, url, headers)
_lock = threading.Lock()


def available():
    return yt_dlp is not None


def auth_opts():
    """Optional browser cookies for yt-dlp (helps when YouTube asks to 'confirm you're not a bot')."""
    try:
        from ..ui.context import ctx
        b = (ctx.settings["ytdlp_cookies"] or "none") if ctx.settings else "none"
    except Exception:
        b = "none"
    return {"cookiesfrombrowser": (b,)} if b and b != "none" else {}


def _ydl(extra=None):
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True,
            "format": "bestaudio/best", "socket_timeout": 12}
    opts.update(auth_opts())
    opts.update(extra or {})
    return yt_dlp.YoutubeDL(opts)


def _thumb(e):
    th = e.get("thumbnails") or []
    if th:
        th = sorted(th, key=lambda t: (t.get("width") or 0))
        return th[-1].get("url")
    return e.get("thumbnail")


def search(query, source="ytmusic", limit=20):
    if source == "ytmusic" and YTMusic is not None:
        try:
            yt = YTMusic()
            out = []
            for r in yt.search(query, filter="songs", limit=limit):
                if not r.get("videoId"):
                    continue
                out.append({"id": r["videoId"], "source": "youtube",
                            "url": f"https://music.youtube.com/watch?v={r['videoId']}",
                            "title": r.get("title"), "artist": ", ".join(a["name"] for a in r.get("artists") or []),
                            "album": (r.get("album") or {}).get("name") or "",
                            "duration": r.get("duration_seconds") or 0,
                            "thumb": (r.get("thumbnails") or [{}])[-1].get("url")})
            return out
        except Exception:
            pass
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed (pip install yt-dlp)")
    prefix = "ytsearch"
    q = query + (" audio" if source == "ytmusic" else "")
    with _ydl({"extract_flat": True}) as y:
        info = y.extract_info(f"{prefix}{limit}:{q}", download=False)
    out = []
    for e in info.get("entries") or []:
        if not e:
            continue
        src = "youtube"
        url = e.get("url") or e.get("webpage_url")
        if src == "youtube" and e.get("id"):
            url = f"https://www.youtube.com/watch?v={e['id']}"
        title = e.get("title") or ""
        artist = e.get("uploader") or e.get("channel") or ""
        if " - " in title and src == "youtube":
            a, t = title.split(" - ", 1)
            artist, title = a.strip(), re.sub(r"\s*[\(\[](official|lyric|audio|video|hd|4k)[^\)\]]*[\)\]]", "", t, flags=re.I).strip()
        out.append({"id": str(e.get("id")), "source": src, "url": url, "title": title, "artist": artist,
                    "album": "", "duration": e.get("duration") or 0, "thumb": _thumb(e)})
    return out


def resolve(src):
    """Return (direct_audio_url, headers) for a streaming track dict."""
    key = src.get("path")
    with _lock:
        c = _resolved.get(key)
        if c and c[0] > time.time():
            return c[1], c[2]
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed")
    url = src.get("url")
    if src.get("source") == "spotify" or not url:
        q = f"{src.get('artist', '')} - {src.get('title', '')} audio"
        target = f"ytsearch1:{q}"
    else:
        target = url
    with _ydl() as y:
        info = y.extract_info(target, download=False)
    if "entries" in info:
        info = (info.get("entries") or [None])[0]
        if not info:
            raise RuntimeError("No match found")
    direct = info.get("url")
    if not direct and info.get("formats"):
        direct = info["formats"][-1]["url"]
    headers = info.get("http_headers") or {}
    with _lock:
        _resolved[key] = (time.time() + 60 * 60 * 4, direct, headers)
    return direct, headers


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=12) as r:
        return r.read().decode("utf-8", "ignore")


_SP_TOKEN = {"token": None, "exp": 0}


def _spotify_token(anon=None):
    """Client-credentials token when the user configured an app (Settings → Streaming), else the embed's anonymous one."""
    try:
        from ..ui.context import ctx
        cid, sec = (ctx.settings["spotify_client_id"] or "").strip(), (ctx.settings["spotify_client_secret"] or "").strip()
    except Exception:
        cid = sec = ""
    if cid and sec:
        if _SP_TOKEN["token"] and _SP_TOKEN["exp"] > time.time():
            return _SP_TOKEN["token"]
        import base64
        req = urllib.request.Request("https://accounts.spotify.com/api/token", data=b"grant_type=client_credentials",
                                     headers={"Authorization": "Basic " + base64.b64encode(f"{cid}:{sec}".encode()).decode(),
                                              "Content-Type": "application/x-www-form-urlencoded"})
        try:
            with urllib.request.urlopen(req, timeout=12) as r:
                d = json.loads(r.read())
            _SP_TOKEN.update(token=d["access_token"], exp=time.time() + int(d.get("expires_in", 3600)) - 60)
            return _SP_TOKEN["token"]
        except Exception:
            pass
    return anon


def _spotify_api(path, token):
    req = urllib.request.Request("https://api.spotify.com/v1/" + path, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())


def _sp_item(tr, album_name="", thumb=None):
    imgs = ((tr.get("album") or {}).get("images")) or []
    return {"id": tr.get("id") or "", "source": "spotify", "url": None, "title": tr.get("name") or "",
            "artist": ", ".join(a.get("name", "") for a in tr.get("artists") or []),
            "album": album_name or (tr.get("album") or {}).get("name") or "",
            "duration": (tr.get("duration_ms") or 0) / 1000.0, "thumb": (imgs[0]["url"] if imgs else thumb)}


def _spotify_more(kind, sid, have, token, thumb, album_name):
    """Fetch tracks beyond the embed's first 100 through the Web API (best effort)."""
    out, offset = [], len(have)
    for _ in range(100):
        if kind == "playlist":
            d = _spotify_api(f"playlists/{sid}/tracks?offset={offset}&limit=100&market=US", token)
            items = [it.get("track") for it in d.get("items") or []]
        else:
            d = _spotify_api(f"albums/{sid}/tracks?offset={offset}&limit=50", token)
            items = d.get("items") or []
        items = [t for t in items if t and t.get("id")]
        out += [_sp_item(t, album_name, thumb) for t in items]
        offset += len(d.get("items") or [])
        if not d.get("next"):
            break
    return out


def spotify_fetch(link):
    """Read a public Spotify track / album / playlist → dict(name, kind, id, link, thumb, tracks, complete)."""
    m = re.search(r"open\.spotify\.com/(?:intl-\w+/)?(track|album|playlist)/([A-Za-z0-9]+)", link) or \
        re.search(r"spotify:(track|album|playlist):([A-Za-z0-9]+)", link)
    if not m:
        raise ValueError("Paste a Spotify track, album or playlist link")
    kind, sid = m.groups()
    page = _get(f"https://open.spotify.com/embed/{kind}/{sid}")
    nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.+?)</script>', page, re.S)
    tracks, name, thumb, anon, desc = [], "Spotify import", None, None, ""
    if nd:
        data = json.loads(nd.group(1))
        state = data.get("props", {}).get("pageProps", {}).get("state", {})
        anon = ((state.get("settings") or {}).get("session") or {}).get("accessToken")
        ent = (state.get("data") or {}).get("entity", {})
        name = ent.get("name") or ent.get("title") or name
        desc = html.unescape(ent.get("subtitle") or "")
        items = ent.get("trackList") or []
        if kind == "track":
            items = [{"title": ent.get("name") or ent.get("title"),
                      "subtitle": ", ".join(a.get("name", "") for a in ent.get("artists") or []),
                      "duration": ent.get("duration"), "uri": ent.get("uri")}]
        imgs = (ent.get("visualIdentity") or {}).get("image") or ent.get("coverArt", {}).get("sources") or []
        if imgs:
            thumb = sorted(imgs, key=lambda i: i.get("maxWidth") or i.get("width") or 0)[-1].get("url")
        for i, it in enumerate(items):
            title = html.unescape(it.get("title") or "")
            artist = html.unescape(it.get("subtitle") or "").replace("\u00a0", " ")
            dur = (it.get("duration") or 0) / 1000.0
            uid = (it.get("uri") or f"{sid}-{i}").split(":")[-1]
            tracks.append({"id": uid, "source": "spotify", "url": None, "title": title, "artist": artist,
                           "album": name if kind == "album" else "", "duration": dur, "thumb": thumb})
    complete = True
    if kind != "track" and len(tracks) >= 100:
        complete = False
        tok = _spotify_token(anon)
        if tok:
            try:
                more = _spotify_more(kind, sid, tracks, tok, thumb, name if kind == "album" else "")
                seen = {t["id"] for t in tracks}
                tracks += [t for t in more if t["id"] not in seen]
                complete = True
            except Exception:
                pass
    if not tracks:
        raise RuntimeError("Could not read this Spotify link (is it public?)")
    return {"name": name, "kind": kind, "id": sid, "origin": f"spotify:{kind}:{sid}",
            "link": f"https://open.spotify.com/{kind}/{sid}", "thumb": thumb, "tracks": tracks,
            "complete": complete, "description": desc}


def youtube_fetch(link):
    """Read a YouTube / YouTube Music playlist (or a single video) link."""
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed (pip install yt-dlp)")
    lid = re.search(r"[?&]list=([\w-]+)", link)
    target = f"https://www.youtube.com/playlist?list={lid.group(1)}" if lid else link
    with _ydl({"extract_flat": "in_playlist", "noplaylist": not lid}) as y:
        info = y.extract_info(target, download=False)
    entries = info.get("entries") if "entries" in info else [info]
    tracks = []
    for e in entries or []:
        if not e or not e.get("id"):
            continue
        title = e.get("title") or ""
        if title in ("[Private video]", "[Deleted video]"):
            continue
        artist = e.get("uploader") or e.get("channel") or ""
        artist = re.sub(r"\s*-\s*Topic$", "", artist)
        if " - " in title:
            a, t = title.split(" - ", 1)
            artist, title = a.strip(), re.sub(r"\s*[\(\[](official|oficial|lyrics?|audio|video|visuali[sz]er|hd|4k|mv)[^\)\]]*[\)\]]", "", t, flags=re.I).strip()
        tracks.append({"id": str(e["id"]), "source": "youtube", "url": f"https://www.youtube.com/watch?v={e['id']}",
                       "title": title, "artist": artist, "album": "", "duration": e.get("duration") or 0, "thumb": _thumb(e)})
    if not tracks:
        raise RuntimeError("Nothing found at this link")
    pid = lid.group(1) if lid else tracks[0]["id"]
    return {"name": info.get("title") or "YouTube playlist", "kind": "playlist" if lid else "track", "id": pid,
            "origin": f"youtube:{pid}", "link": target, "thumb": tracks[0].get("thumb"), "tracks": tracks,
            "complete": True, "description": info.get("uploader") or ""}


def is_link(text):
    return bool(re.search(r"(open\.spotify\.com/|spotify:(track|album|playlist):|youtube\.com/|youtu\.be/)", text or ""))


def fetch_link(link):
    if "spotify" in link:
        return spotify_fetch(link)
    return youtube_fetch(link)


def spotify_import(link):
    """Back-compat: (name, tracks)."""
    d = spotify_fetch(link)
    return d["name"], d["tracks"]
