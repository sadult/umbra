"""Umbra Glyphs — a custom hairline icon set (24×24, rounded 1.6px strokes)."""
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

S = 'fill="none" stroke="{c}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"'
F = 'fill="{c}" stroke="none"'

P = {
    # navigation
    "home": f'<path {S} d="M3.5 10.6 12 3.8l8.5 6.8"/><path {S} d="M5.8 9v10.2c0 .6.4 1 1 1h3.4v-5.4h3.6v5.4h3.4c.6 0 1-.4 1-1V9"/>',
    "songs": f'<circle {S} cx="7" cy="17.5" r="2.6"/><path {S} d="M9.6 17.5V5.2l10-1.9v11.9"/><circle {S} cx="17" cy="15.2" r="2.6"/><path {S} d="M9.6 9.2l10-1.9"/>',
    "artists": f'<circle {S} cx="12" cy="8.2" r="3.9"/><path {S} d="M4.5 20.2c.9-3.7 4-5.6 7.5-5.6s6.6 1.9 7.5 5.6"/>',
    "albums": f'<circle {S} cx="12" cy="12" r="8.6"/><circle {S} cx="12" cy="12" r="2.4"/><path {S} d="M12 5.6a6.4 6.4 0 0 1 6.4 6.4" opacity=".55"/>',
    "genres": f'<path {S} d="M4 7.5 12 3.6l8 3.9-8 3.9z"/><path {S} d="m4 12 8 3.9 8-3.9"/><path {S} d="m4 16.4 8 3.9 8-3.9"/>',
    "playlists": f'<path {S} d="M4 6h11M4 11h11M4 16h6"/><path {S} d="M17.5 13v6.6"/><circle {S} cx="15.4" cy="19.4" r="2.1"/><path {S} d="M17.5 13l3-1"/>',
    "folder": f'<path {S} d="M3.6 7.2c0-1 .8-1.8 1.8-1.8h4l2 2.2h7.2c1 0 1.8.8 1.8 1.8v8.2c0 1-.8 1.8-1.8 1.8H5.4c-1 0-1.8-.8-1.8-1.8z"/>',
    "clock": f'<circle {S} cx="12" cy="12" r="8.6"/><path {S} d="M12 7.4V12l3.2 2"/>',
    "flame": f'<path {S} d="M12 21c-3.8 0-6.4-2.6-6.4-6.2 0-3.3 2.2-5.1 3.3-7.6.6 1.6 1.5 2.5 2.4 2.9-.2-2.9 1.1-5.4 3.2-6.9-.3 2.6 1 4.4 2.3 6.1 1.1 1.4 1.6 2.9 1.6 4.9 0 3.9-2.6 6.8-6.4 6.8z"/><path {S} d="M12 21c-1.6 0-2.7-1.2-2.7-2.7 0-1.8 1.6-2.6 2.2-4 .9 1 3.2 2 3.2 4 0 1.5-1.1 2.7-2.7 2.7z" opacity=".6"/>',
    "sparkle": f'<path {S} d="M12 3.5c.6 4.4 2.6 6.9 7.5 8.5-4.9 1.6-6.9 4.1-7.5 8.5-.6-4.4-2.6-6.9-7.5-8.5 4.9-1.6 6.9-4.1 7.5-8.5z"/><path {S} d="M19 3.6v3M17.5 5.1h3" opacity=".6"/>',
    "heart": f'<path {S} d="M12 19.6s-7.6-4.5-7.6-10a4.2 4.2 0 0 1 7.6-2.5 4.2 4.2 0 0 1 7.6 2.5c0 5.5-7.6 10-7.6 10z"/>',
    "heart_fill": f'<path {F} d="M12 19.6s-7.6-4.5-7.6-10a4.2 4.2 0 0 1 7.6-2.5 4.2 4.2 0 0 1 7.6 2.5c0 5.5-7.6 10-7.6 10z"/>',
    "ghost": f'<path {S} d="M5.6 20.2V10.6a6.4 6.4 0 0 1 12.8 0v9.6l-2.2-1.6-2.1 1.6-2.1-1.6-2.1 1.6-2.1-1.6z"/><circle {F} cx="9.8" cy="10.8" r="1.1"/><circle {F} cx="14.2" cy="10.8" r="1.1"/>',
    "dice": f'<rect {S} x="4" y="4" width="16" height="16" rx="4"/><circle {F} cx="8.7" cy="8.7" r="1.15"/><circle {F} cx="15.3" cy="15.3" r="1.15"/><circle {F} cx="12" cy="12" r="1.15"/><circle {F} cx="15.3" cy="8.7" r="1.15"/><circle {F} cx="8.7" cy="15.3" r="1.15"/>',
    "new": f'<path {S} d="M12 4v4M12 16v4M4 12h4M16 12h4M6.6 6.6l2.2 2.2M15.2 15.2l2.2 2.2M6.6 17.4l2.2-2.2M15.2 8.8l2.2-2.2"/>',
    "wave": f'<path {S} d="M3 12h1.8M6.6 8v8M10.2 5v14M13.8 9v6M17.4 6.5v11M21 12h-1.8"/>',
    "cloud": f'<path {S} d="M7.2 18.6a4.2 4.2 0 0 1-.5-8.4 5.6 5.6 0 0 1 10.8 1.3 3.6 3.6 0 0 1-.2 7.1z"/>',
    "ytmusic": f'<circle {S} cx="12" cy="12" r="8.6"/><circle {S} cx="12" cy="12" r="4.6" opacity=".5"/><path {F} d="M10.4 9.4v5.2l4.3-2.6z"/>',
    "soundcloud": f'<path {S} d="M10 17.6V8.2a4.9 4.9 0 0 1 8.7 3 3.2 3.2 0 0 1 1.3 6.2z"/><path {S} d="M7.4 17.6v-7M4.8 17.6v-4.6M2.6 17v-2.4"/>',
    "spotify": f'<circle {S} cx="12" cy="12" r="8.6"/><path {S} d="M7.3 9.6c3.3-1 6.9-.7 9.6.9M7.9 12.6c2.7-.7 5.4-.4 7.6.8M8.6 15.4c2-.5 4-.3 5.7.6"/>',
    "search": f'<circle {S} cx="10.8" cy="10.8" r="6.4"/><path {S} d="m15.6 15.6 4.6 4.6"/>',
    "settings": f'<path {S} d="M12 2.9l1.6 2.3 2.8-.4.9 2.7 2.6 1.1-.6 2.7 1.8 2.2-2.2 1.7.1 2.8-2.8.4-1.3 2.5-2.6-1-2.6 1-1.3-2.5-2.8-.4.1-2.8-2.2-1.7 1.8-2.2-.6-2.7 2.6-1.1.9-2.7 2.8.4z"/><circle {S} cx="12" cy="12" r="3"/>',
    "info": f'<circle {S} cx="12" cy="12" r="8.6"/><path {S} d="M12 11v5.4"/><circle {F} cx="12" cy="7.8" r="1.1"/>',
    "back": f'<path {S} d="M14.6 5.6 8.2 12l6.4 6.4"/>',
    "forward": f'<path {S} d="M9.4 5.6 15.8 12l-6.4 6.4"/>',
    "down": f'<path {S} d="M6 9.4l6 6 6-6"/>',
    "plus": f'<path {S} d="M12 5v14M5 12h14"/>',
    "minus": f'<path {S} d="M5 12h14"/>',
    "close": f'<path {S} d="M6.4 6.4l11.2 11.2M17.6 6.4 6.4 17.6"/>',
    "check": f'<path {S} d="M5 12.6l4.4 4.4L19 7.4"/>',
    "edit": f'<path {S} d="M14.6 5.4l4 4L9 19H5v-4z"/><path {S} d="M12.6 7.4l4 4" opacity=".55"/>',
    "trash": f'<path {S} d="M4.6 7h14.8M9.6 7V5h4.8v2M6.6 7l.9 12.2c.1.6.5 1 1.1 1h6.8c.6 0 1-.4 1.1-1L17.4 7"/>',
    "more": f'<circle {F} cx="5.6" cy="12" r="1.5"/><circle {F} cx="12" cy="12" r="1.5"/><circle {F} cx="18.4" cy="12" r="1.5"/>',
    "image": f'<rect {S} x="3.6" y="4.6" width="16.8" height="14.8" rx="3"/><circle {S} cx="9" cy="9.8" r="1.7"/><path {S} d="m4.4 17.4 4.8-4.4 3.4 3 2.8-2.4 4.6 4"/>',
    "refresh": f'<path {S} d="M19.4 12a7.4 7.4 0 1 1-2.2-5.2"/><path {S} d="M19.6 4.4v3.8h-3.8"/>',
    "link": f'<path {S} d="M10 14a4 4 0 0 0 5.6 0l3-3a4 4 0 0 0-5.6-5.6l-1 1"/><path {S} d="M14 10a4 4 0 0 0-5.6 0l-3 3a4 4 0 0 0 5.6 5.6l1-1"/>',
    "download": f'<path {S} d="M12 4v11M7.4 10.6 12 15.2l4.6-4.6M5 19.6h14"/>',
    "external": f'<path {S} d="M13.6 4.6h5.8v5.8M19.4 4.6l-8 8M17 14v4.4c0 .6-.4 1-1 1H5.6c-.6 0-1-.4-1-1V8c0-.6.4-1 1-1H10"/>',
    # transport
    "play": f'<path {F} d="M8.2 5.3c0-.9 1-1.4 1.7-.9l9.6 6.7c.6.4.6 1.4 0 1.8l-9.6 6.7c-.7.5-1.7 0-1.7-.9z"/>',
    "pause": f'<rect {F} x="6.6" y="5" width="3.8" height="14" rx="1.4"/><rect {F} x="13.6" y="5" width="3.8" height="14" rx="1.4"/>',
    "next": f'<path {F} d="M5.2 6.4c0-.8.9-1.2 1.5-.8l8 5.6c.5.4.5 1.2 0 1.6l-8 5.6c-.6.4-1.5 0-1.5-.8z"/><rect {F} x="16.6" y="5.4" width="2.4" height="13.2" rx="1.2"/>',
    "prev": f'<path {F} d="M18.8 6.4c0-.8-.9-1.2-1.5-.8l-8 5.6c-.5.4-.5 1.2 0 1.6l8 5.6c.6.4 1.5 0 1.5-.8z"/><rect {F} x="5" y="5.4" width="2.4" height="13.2" rx="1.2"/>',
    "shuffle": f'<path {S} d="M3.8 7.4h2.8c4.6 0 6.2 9.2 10.8 9.2h2.8"/><path {S} d="M3.8 16.6h2.8c1.6 0 2.7-1.1 3.6-2.6M13.8 10c.9-1.5 2-2.6 3.6-2.6h2.8"/><path {S} d="m18 5.2 2.2 2.2L18 9.6M18 14.4l2.2 2.2-2.2 2.2"/>',
    "repeat": f'<path {S} d="M5 11V9.4a2.6 2.6 0 0 1 2.6-2.6h11"/><path {S} d="m16.2 4.4 2.4 2.4-2.4 2.4"/><path {S} d="M19 13v1.6a2.6 2.6 0 0 1-2.6 2.6h-11"/><path {S} d="m7.8 19.6-2.4-2.4 2.4-2.4"/>',
    "repeat_one": f'<path {S} d="M5 11V9.4a2.6 2.6 0 0 1 2.6-2.6h11"/><path {S} d="m16.2 4.4 2.4 2.4-2.4 2.4"/><path {S} d="M19 13v1.6a2.6 2.6 0 0 1-2.6 2.6h-11"/><path {S} d="m7.8 19.6-2.4-2.4 2.4-2.4"/><path {S} d="M11.4 10.6l1.2-.8v4.6"/>',
    "volume": f'<path {S} d="M4.4 9.6v4.8h3.2l4.8 4V5.6l-4.8 4z"/><path {S} d="M15.6 9a4.2 4.2 0 0 1 0 6M18 6.6a7.6 7.6 0 0 1 0 10.8"/>',
    "volume_low": f'<path {S} d="M4.4 9.6v4.8h3.2l4.8 4V5.6l-4.8 4z"/><path {S} d="M15.6 9a4.2 4.2 0 0 1 0 6"/>',
    "mute": f'<path {S} d="M4.4 9.6v4.8h3.2l4.8 4V5.6l-4.8 4z"/><path {S} d="m16 9.6 4.6 4.8M20.6 9.6 16 14.4"/>',
    "queue": f'<path {S} d="M4 6h16M4 11h16M4 16h9"/><path {F} d="M16 14.2v5.6l4.4-2.8z"/>',
    "lyrics": f'<path {S} d="M5 5.6h14c.6 0 1 .4 1 1v8.8c0 .6-.4 1-1 1h-7l-4.4 3.4v-3.4H5c-.6 0-1-.4-1-1V6.6c0-.6.4-1 1-1z"/><path {S} d="M8 9.4h8M8 12.4h5"/>',
    "eq": f'<path {S} d="M6 4v5M6 13v7M12 4v9M12 17v3M18 4v3M18 11v9"/><circle {S} cx="6" cy="11" r="2"/><circle {S} cx="12" cy="15" r="2"/><circle {S} cx="18" cy="9" r="2"/>',
    "analyzer": f'<path {S} d="M3.6 19.6h16.8"/><path {S} d="M6 16v-3M9.4 16V8M12.8 16v-6M16.2 16V5M19.6 16v-4"/>',
    "nowplaying": f'<rect {S} x="3.6" y="3.6" width="16.8" height="16.8" rx="4.2"/><circle {S} cx="12" cy="12" r="4"/><circle {F} cx="12" cy="12" r="1.2"/>',
    "mini": f'<rect {S} x="3.6" y="5" width="16.8" height="14" rx="3"/><rect {S} x="11.6" y="11.4" width="6.4" height="5" rx="1.4"/>',
    "expand": f'<path {S} d="M14.4 4.6h5v5M9.6 19.4h-5v-5M19.4 4.6l-5.6 5.6M4.6 19.4l5.6-5.6"/>',
    "win_min": f'<path {S} d="M6.5 12h11"/>',
    "win_max": f'<rect {S} x="6.4" y="6.4" width="11.2" height="11.2" rx="2.6"/>',
    "win_restore": f'<rect {S} x="5.6" y="8.4" width="10" height="10" rx="2.4"/><path {S} d="M8.6 5.6h7.2c1.5 0 2.6 1.1 2.6 2.6v7.2"/>',
    "palette": f'<path {S} d="M12 3.6a8.4 8.4 0 0 0 0 16.8c1.2 0 1.8-.8 1.8-1.6 0-1.2-1-1.4-1-2.4 0-.8.6-1.4 1.6-1.4h2a4 4 0 0 0 4-4C20.4 7 16.6 3.6 12 3.6z"/><circle {F} cx="7.8" cy="11.4" r="1.2"/><circle {F} cx="10.4" cy="7.6" r="1.2"/><circle {F} cx="15" cy="7.8" r="1.2"/>',
    "github": f'<path {S} d="M9.4 19.4c-4 1.2-4-2-5.6-2.4M15 21.6v-3.4c0-1 .1-1.4-.5-2 2.7-.3 5.4-1.3 5.4-6a4.6 4.6 0 0 0-1.3-3.2 4.3 4.3 0 0 0-.1-3.2s-1-.3-3.3 1.2a11.4 11.4 0 0 0-6 0C6.9 3.5 5.9 3.8 5.9 3.8a4.3 4.3 0 0 0-.1 3.2A4.6 4.6 0 0 0 4.5 10.2c0 4.6 2.7 5.6 5.4 6-.6.6-.6 1.2-.5 2v3.4"/>',
    "globe": f'<circle {S} cx="12" cy="12" r="8.6"/><path {S} d="M3.4 12h17.2M12 3.4c2.4 2.3 3.6 5.2 3.6 8.6s-1.2 6.3-3.6 8.6c-2.4-2.3-3.6-5.2-3.6-8.6S9.6 5.7 12 3.4z"/>',
    "telegram": f'<path {S} d="M20.4 4.4 3.6 11c-.8.3-.7 1.4.1 1.6l4.2 1.2 1.6 5c.2.7 1.1.9 1.6.3l2.3-2.4 4.2 3.1c.6.4 1.4.1 1.6-.6l2.6-12.6c.2-.9-.6-1.5-1.4-1.2z"/><path {S} d="m7.9 13.8 8.4-5.6-6.3 6.6"/>',
    "user": f'<circle {S} cx="12" cy="9" r="3.6"/><path {S} d="M5.6 19.4c1.2-3 3.6-4.4 6.4-4.4s5.2 1.4 6.4 4.4"/>',
    "disc": f'<circle {S} cx="12" cy="12" r="8.6"/><circle {S} cx="12" cy="12" r="1.6"/>',
    "tag": f'<path {S} d="M3.8 12.4V5c0-.7.5-1.2 1.2-1.2h7.4l8 8c.5.5.5 1.2 0 1.7l-7 7c-.5.5-1.2.5-1.7 0z"/><circle {S} cx="8.4" cy="8.4" r="1.5"/>',
    "drop": f'<path {S} d="M12 3.6c3 3.8 6 7 6 10.4a6 6 0 0 1-12 0c0-3.4 3-6.6 6-10.4z"/><path {S} d="M9.2 14.6a2.8 2.8 0 0 0 2.8 2.8" opacity=".6"/>',
    "command": f'<path {S} d="M9 9V6.6A2.4 2.4 0 1 0 6.6 9H9zm0 0h6M9 9v6m6-6V6.6A2.4 2.4 0 1 1 17.4 9H15zm0 0v6m0 0h2.4a2.4 2.4 0 1 1-2.4 2.4V15zm0 0H9m0 0v2.4A2.4 2.4 0 1 1 6.6 15H9z"/>',
    "sliders": f'<path {S} d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle {S} cx="15" cy="7" r="2"/><circle {S} cx="9" cy="17" r="2"/>',
    "pin": f'<path {S} d="M9 4h6l-1 5 3 3H7l3-3zM12 12v8"/>',
    "headphones": f'<path {S} d="M4.6 15v-3a7.4 7.4 0 0 1 14.8 0v3"/><rect {S} x="3.6" y="14" width="4" height="6" rx="1.6"/><rect {S} x="16.4" y="14" width="4" height="6" rx="1.6"/>',
    "small": f'<rect {S} x="3.6" y="4.6" width="16.8" height="14.8" rx="3"/><rect {S} x="6.4" y="7.6" width="5.4" height="5.4" rx="1.2"/><path {S} d="M14 8.6h3.6M14 11.6h2.4M6.4 16.2h11.2"/>',
    "layers": f'<path {S} d="M12 4 3.6 8.4 12 12.8l8.4-4.4z"/><path {S} d="m3.6 12.4 8.4 4.4 8.4-4.4" opacity=".7"/><path {S} d="m3.6 16.2 8.4 4.4 8.4-4.4" opacity=".4"/>',
}

_cache = {}


def _svg(name, color, width):
    body = P.get(name, P["info"]).replace("{c}", color).replace("{w}", str(width))
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">{body}</svg>'


def renderer(name, color: QColor, width=1.6):
    c = QColor(color)
    key = (name, c.name(QColor.HexArgb), width)
    r = _cache.get(key)
    if r is None:
        col = c.name(QColor.HexRgb)
        svg = _svg(name, col, width)
        if c.alpha() < 255:
            svg = svg.replace("<svg ", f'<svg opacity="{c.alphaF():.3f}" ')
        r = QSvgRenderer(QByteArray(svg.encode()))
        _cache[key] = r
    return r


def draw(p: QPainter, name, rect: QRectF, color: QColor, width=1.6):
    renderer(name, color, width).render(p, QRectF(rect))


def pixmap(name, color, size=20, dpr=2.0, width=1.6):
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    draw(p, name, QRectF(0, 0, size * dpr, size * dpr), QColor(color), width)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def qicon(name, color="#ffffff", size=20):
    return QIcon(pixmap(name, color, size))
