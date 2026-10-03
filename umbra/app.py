"""Application bootstrap."""
import os
import sys


def run():
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    from . import winsys
    winsys.set_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("Umbra")
    app.setOrganizationName("Umbra")
    app.setQuitOnLastWindowClosed(False)

    from .config import settings
    from .theme import init_theme
    s = settings()
    theme = init_theme(s)
    from .ui.widgets import font
    app.setFont(font(9.5))

    from .library.db import Library
    from .library.lyrics import LyricsLoader
    from .library.scanner import Scanner
    from .player import Player
    from .ui.art import provider
    from .ui.context import ctx

    ctx.settings, ctx.theme = s, theme
    ctx.lib = Library()
    ctx.art = provider()
    ctx.player = Player(ctx.lib, s)
    ctx.lyrics = LyricsLoader(s)
    ctx.scanner = Scanner(ctx.lib, s)
    from .library.downloader import Downloader
    ctx.downloads = Downloader(ctx.lib, s)
    from .library.lyrics import LyricsBatch
    ctx.lyrics_batch = LyricsBatch(s)

    from .ui.window import MainWindow
    win = MainWindow()
    win.show()

    if winsys.MediaKeyFilter is not None:
        try:
            win._mk = winsys.MediaKeyFilter(win.media_key)
            app.installNativeEventFilter(win._mk)
        except Exception:
            pass

    ctx.player.restore_session()
    files = [a for a in sys.argv[1:] if os.path.isfile(a)]
    if files:
        win.open_files(files)
    if s["scan_on_start"] and ctx.lib.folders():
        ctx.scanner.scan()
    else:
        ctx.scanner.refresh_watch()
    if s["first_run"]:
        s.set("first_run", False)
    return app.exec()
