"""
╭──────────────────────────────────────────────────────────────╮
│  ABOUT THE DEVELOPER — edit this file to make it yours.      │
│  Everything here is shown on the “About” page of Umbra.      │
╰──────────────────────────────────────────────────────────────╯
"""

DEVELOPER = {
    "name": "Mersad Shahidi",
    "handle": "@Bitologist",
    "role": "Designer & Developer",
    "location": "Iran · UTC+3:30",
    "bio": ("I build calm, good-looking software for people who still own their music. "
            "Umbra is my love letter to local libraries, lossless audio and dark interfaces — "
            "designed pixel by pixel, painted entirely in code."),
    # path to a square image (png/jpg). Leave empty for a generated monogram avatar.
    "avatar": "",
    # label → url   (icons: github, website, telegram, twitter/x, instagram, email, youtube)
    "links": {
        "Website": "https://10ck.ir",
        "GitHub": "https://github.com/sadult",
        "Telegram": "https://t.me/Bitologist",
    },
    "stack": ["Python 3.10+", "PySide6 / Qt 6", "NumPy · SciPy", "Mutagen", "SoundFile · PortAudio", "yt-dlp"],
}

PROJECT = {
    "repo": "https://github.com/sadult/umbra",
    "issues": "https://github.com/sadult/umbra/issues",
    "releases": "https://github.com/sadult/umbra/releases",
    "license": "MIT",
}

CHANGELOG = [
    ("1.2.0", ["Fetch lyrics for the whole library in one click",
               "Save, stream, sync & download Spotify / YouTube playlists",
               "Downloads run in a queue and replace streams in your playlists",
               "Sleep timer with a gentle fade-out"]),
    ("1.1.0", ["Bento home, Small player and a redesigned Mini player",
               "Online lyrics search with one-click “Add lyrics”",
               "Download YouTube Music & Spotify tracks — tagged, with artwork",
               "Queue and lyrics fully separated · lyrics on/off toggle",
               "Every appearance setting now applies live"]),
    ("1.0.0", ["First release — liquid-glass UI, 10-band EQ, analyzer, synced lyrics, tag editor, streaming"]),
]

CREDITS = [
    ("LRCLIB", "Synced lyrics database — lrclib.net"),
    ("yt-dlp", "Streaming & downloads for YouTube Music / Spotify matches"),
    ("Mutagen", "Tag reading & writing"),
    ("libsndfile / FFmpeg", "Decoding"),
    ("Qt / PySide6", "Everything you see"),
]
