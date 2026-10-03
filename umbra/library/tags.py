"""Format-agnostic tag reading / writing on top of Mutagen."""
import base64
import re
from pathlib import Path

import mutagen
from mutagen.flac import FLAC, Picture
from mutagen.id3 import (APIC, COMM, ID3, TALB, TCOM, TCON, TDRC, TIT2, TPE1, TPE2, TPOS, TRCK, USLT,
                         ID3NoHeaderError)
from mutagen.mp4 import MP4, MP4Cover

FIELDS = ["title", "artist", "albumartist", "album", "genre", "year", "track", "tracktotal",
          "disc", "disctotal", "composer", "comment", "lyrics"]

ID3_MAP = {"title": TIT2, "artist": TPE1, "albumartist": TPE2, "album": TALB, "genre": TCON,
           "year": TDRC, "composer": TCOM}
VORBIS_MAP = {"title": "TITLE", "artist": "ARTIST", "albumartist": "ALBUMARTIST", "album": "ALBUM",
              "genre": "GENRE", "year": "DATE", "composer": "COMPOSER", "comment": "COMMENT",
              "lyrics": "LYRICS"}
MP4_MAP = {"title": "\xa9nam", "artist": "\xa9ART", "albumartist": "aART", "album": "\xa9alb",
           "genre": "\xa9gen", "year": "\xa9day", "composer": "\xa9wrt", "comment": "\xa9cmt",
           "lyrics": "\xa9lyr"}
LOSSLESS = {"flac", "wav", "aiff", "alac", "ape", "wavpack", "dsf", "pcm"}


def _first(v):
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        v = v[0] if v else ""
    return str(v).strip()


def _num_pair(s):
    s = _first(s)
    m = re.match(r"\s*(\d+)?\s*(?:/\s*(\d+))?", s)
    if not m:
        return 0, 0
    return int(m.group(1) or 0), int(m.group(2) or 0)


def _year(s):
    m = re.search(r"(\d{4})", _first(s))
    return int(m.group(1)) if m else 0


def _rg(s):
    m = re.search(r"(-?\d+(?:\.\d+)?)", _first(s))
    return float(m.group(1)) if m else None


def read_tags(path: str) -> dict:
    d = {k: "" for k in FIELDS}
    d.update(track=0, tracktotal=0, disc=0, disctotal=0, year=0, duration=0.0, bitrate=0,
             samplerate=0, bitdepth=0, channels=0, codec=Path(path).suffix.lstrip(".").lower(),
             lossless=0, has_art=0, rg_track=None, rg_album=None)
    try:
        f = mutagen.File(path)
    except Exception:
        f = None
    if f is None:
        return d
    info = getattr(f, "info", None)
    if info:
        d["duration"] = float(getattr(info, "length", 0) or 0)
        d["bitrate"] = int(getattr(info, "bitrate", 0) or 0) // 1000
        d["samplerate"] = int(getattr(info, "sample_rate", 0) or 0)
        d["bitdepth"] = int(getattr(info, "bits_per_sample", 0) or 0)
        d["channels"] = int(getattr(info, "channels", 0) or 0)
        codec = getattr(info, "codec", None)
        if codec == "alac":
            d["codec"] = "alac"
    tags = f.tags
    cls = type(f).__name__.lower()
    if "flac" in cls:
        d["codec"] = "flac"
    if tags is None:
        pass
    elif isinstance(tags, ID3):
        for k, frame in ID3_MAP.items():
            fr = tags.get(frame.__name__)
            if fr is not None:
                d[k] = _first(fr.text)
        d["track"], d["tracktotal"] = _num_pair(tags.get("TRCK").text if tags.get("TRCK") else "")
        d["disc"], d["disctotal"] = _num_pair(tags.get("TPOS").text if tags.get("TPOS") else "")
        comms = tags.getall("COMM")
        if comms:
            d["comment"] = _first(comms[0].text)
        ly = tags.getall("USLT")
        if ly:
            d["lyrics"] = ly[0].text
        d["has_art"] = int(bool(tags.getall("APIC")))
        for t in tags.getall("TXXX"):
            if t.desc.lower() == "replaygain_track_gain":
                d["rg_track"] = _rg(t.text)
            elif t.desc.lower() == "replaygain_album_gain":
                d["rg_album"] = _rg(t.text)
    elif isinstance(f, MP4):
        for k, key in MP4_MAP.items():
            if key in tags:
                d[k] = _first(tags[key])
        if "trkn" in tags and tags["trkn"]:
            d["track"], d["tracktotal"] = tags["trkn"][0]
        if "disk" in tags and tags["disk"]:
            d["disc"], d["disctotal"] = tags["disk"][0]
        d["has_art"] = int(bool(tags.get("covr")))
        for k in tags.keys():
            if k.lower().endswith("replaygain_track_gain"):
                d["rg_track"] = _rg(bytes(tags[k][0]).decode("utf-8", "ignore"))
    else:  # vorbis-like (FLAC, OGG, Opus, APE, WavPack …)
        def g(key):
            try:
                return _first(tags.get(key) or tags.get(key.lower()))
            except Exception:
                return ""
        for k, key in VORBIS_MAP.items():
            d[k] = g(key)
        if not d["lyrics"]:
            d["lyrics"] = g("UNSYNCEDLYRICS")
        if not d["albumartist"]:
            d["albumartist"] = g("ALBUM ARTIST")
        d["track"], d["tracktotal"] = _num_pair(g("TRACKNUMBER") or g("TRACK"))
        d["disc"], d["disctotal"] = _num_pair(g("DISCNUMBER") or g("DISC"))
        d["tracktotal"] = d["tracktotal"] or _num_pair(g("TRACKTOTAL") or g("TOTALTRACKS"))[0]
        d["disctotal"] = d["disctotal"] or _num_pair(g("DISCTOTAL") or g("TOTALDISCS"))[0]
        d["rg_track"] = _rg(g("REPLAYGAIN_TRACK_GAIN"))
        d["rg_album"] = _rg(g("REPLAYGAIN_ALBUM_GAIN"))
        if isinstance(f, FLAC):
            d["has_art"] = int(bool(f.pictures))
        else:
            d["has_art"] = int(bool(g("METADATA_BLOCK_PICTURE")))
    d["year"] = _year(d["year"])
    d["lossless"] = int(d["codec"] in LOSSLESS or d["bitdepth"] > 0 and d["codec"] not in ("mp3", "ogg", "opus", "m4a", "aac"))
    if not d["title"]:
        d["title"] = Path(path).stem
    return d


def get_embedded_art(path: str):
    try:
        f = mutagen.File(path)
    except Exception:
        return None
    if f is None:
        return None
    try:
        if isinstance(f, FLAC) and f.pictures:
            pics = sorted(f.pictures, key=lambda p: p.type != 3)
            return pics[0].data
        tags = f.tags
        if tags is None:
            return None
        if isinstance(tags, ID3):
            pics = tags.getall("APIC")
            if pics:
                pics = sorted(pics, key=lambda p: p.type != 3)
                return pics[0].data
        if isinstance(f, MP4) and tags.get("covr"):
            return bytes(tags["covr"][0])
        for key in ("METADATA_BLOCK_PICTURE", "metadata_block_picture"):
            v = tags.get(key) if hasattr(tags, "get") else None
            if v:
                return Picture(base64.b64decode(_first(v))).data
    except Exception:
        return None
    return None


def find_folder_art(path: str, names="cover,folder,front,album,artwork"):
    folder = Path(path).parent
    wanted = [n.strip().lower() for n in names.split(",") if n.strip()]
    try:
        files = {p.stem.lower(): p for p in folder.iterdir()
                 if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp")}
    except Exception:
        return None
    for n in wanted:
        if n in files:
            return files[n].read_bytes()
    if files:
        return next(iter(files.values())).read_bytes()
    return None


def _mime(data: bytes):
    return "image/png" if data[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"


def write_tags(path: str, values: dict, artwork=None):
    """values: subset of FIELDS (strings / ints). artwork: bytes | 'remove' | None (keep)."""
    f = mutagen.File(path)
    if f is None:
        raise ValueError("Unsupported file")
    v = dict(values)

    def tn(a, b):
        a = int(a or 0)
        b = int(b or 0)
        return f"{a}/{b}" if b else (str(a) if a else "")

    if isinstance(f, MP4):
        if f.tags is None:
            f.add_tags()
        t = f.tags
        for k, key in MP4_MAP.items():
            if k in v:
                val = str(v[k] or "")
                if val:
                    t[key] = [val]
                elif key in t:
                    del t[key]
        if "track" in v or "tracktotal" in v:
            t["trkn"] = [(int(v.get("track") or 0), int(v.get("tracktotal") or 0))]
        if "disc" in v or "disctotal" in v:
            t["disk"] = [(int(v.get("disc") or 0), int(v.get("disctotal") or 0))]
        if artwork == "remove":
            t.pop("covr", None)
        elif artwork:
            fmt = MP4Cover.FORMAT_PNG if _mime(artwork) == "image/png" else MP4Cover.FORMAT_JPEG
            t["covr"] = [MP4Cover(artwork, imageformat=fmt)]
        f.save()
        return
    is_id3 = path.lower().endswith((".mp3", ".wav", ".aif", ".aiff")) or isinstance(getattr(f, "tags", None), ID3)
    if is_id3:
        try:
            t = f.tags if f.tags is not None else None
            if t is None:
                f.add_tags()
                t = f.tags
        except Exception:
            try:
                t = ID3(path)
            except ID3NoHeaderError:
                t = ID3()
        for k, frame in ID3_MAP.items():
            if k in v:
                val = str(v[k] or "")
                t.delall(frame.__name__)
                if val and val != "0":
                    t.add(frame(encoding=3, text=[val]))
        if "track" in v or "tracktotal" in v:
            t.delall("TRCK")
            s = tn(v.get("track"), v.get("tracktotal"))
            if s:
                t.add(TRCK(encoding=3, text=[s]))
        if "disc" in v or "disctotal" in v:
            t.delall("TPOS")
            s = tn(v.get("disc"), v.get("disctotal"))
            if s:
                t.add(TPOS(encoding=3, text=[s]))
        if "comment" in v:
            t.delall("COMM")
            if v["comment"]:
                t.add(COMM(encoding=3, lang="eng", desc="", text=[v["comment"]]))
        if "lyrics" in v:
            t.delall("USLT")
            if v["lyrics"]:
                t.add(USLT(encoding=3, lang="eng", desc="", text=v["lyrics"]))
        if artwork == "remove":
            t.delall("APIC")
        elif artwork:
            t.delall("APIC")
            t.add(APIC(encoding=3, mime=_mime(artwork), type=3, desc="Cover", data=artwork))
        if f.tags is t:
            f.save()
        else:
            t.save(path)
        return
    # Vorbis comments
    if f.tags is None:
        f.add_tags()
    t = f.tags
    for k, key in VORBIS_MAP.items():
        if k in v:
            val = str(v[k] or "")
            if val and val != "0":
                t[key] = [val]
            elif key in t:
                del t[key]
    for k, key in (("track", "TRACKNUMBER"), ("tracktotal", "TRACKTOTAL"),
                   ("disc", "DISCNUMBER"), ("disctotal", "DISCTOTAL")):
        if k in v:
            n = int(v[k] or 0)
            if n:
                t[key] = [str(n)]
            elif key in t:
                del t[key]
    if artwork is not None:
        if isinstance(f, FLAC):
            f.clear_pictures()
            if artwork != "remove":
                p = Picture()
                p.type, p.mime, p.desc, p.data = 3, _mime(artwork), "Cover", artwork
                f.add_picture(p)
        else:
            if "METADATA_BLOCK_PICTURE" in t:
                del t["METADATA_BLOCK_PICTURE"]
            if artwork != "remove":
                p = Picture()
                p.type, p.mime, p.desc, p.data = 3, _mime(artwork), "Cover", artwork
                t["METADATA_BLOCK_PICTURE"] = [base64.b64encode(p.write()).decode("ascii")]
    f.save()


def format_from_filename(path: str, pattern: str) -> dict:
    """'%track% - %artist% - %title%' → dict from file stem."""
    stem = Path(path).stem
    keys = re.findall(r"%(\w+)%", pattern)
    rx = re.escape(pattern)
    for k in keys:
        rx = rx.replace(re.escape(f"%{k}%"), r"(\d+)" if k in ("track", "disc", "year") else r"(.+?)")
    m = re.fullmatch(rx, stem)
    if not m:
        return {}
    return {k: m.group(i + 1).strip() for i, k in enumerate(keys)}


def filename_from_tags(tags: dict, pattern: str) -> str:
    def rep(m):
        k = m.group(1)
        val = tags.get(k, "")
        if k == "track":
            return f"{int(val or 0):02d}"
        return str(val or "Unknown")
    name = re.sub(r"%(\w+)%", rep, pattern)
    return re.sub(r'[<>:"/\\|?*]+', "_", name).strip()
