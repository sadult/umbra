"""Background folder scanner + filesystem watcher."""
import os
import threading
from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from ..config import AUDIO_EXTS
from .tags import read_tags


class Scanner(QObject):
    progress = Signal(int, int, str)     # done, total, current file
    finished = Signal(int, int)          # added/updated, removed
    started = Signal()

    def __init__(self, lib, settings):
        super().__init__()
        self.lib = lib
        self.s = settings
        self._thread = None
        self._cancel = False
        self.busy = False
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._on_fs_change)
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(2500)
        self._debounce.timeout.connect(lambda: self.scan())

    def _on_fs_change(self, _p):
        if self.s["watch_folders"]:
            self._debounce.start()

    def refresh_watch(self):
        dirs = self.watcher.directories()
        if dirs:
            self.watcher.removePaths(dirs)
        if not self.s["watch_folders"]:
            return
        paths = []
        for root in self.lib.folders():
            if not os.path.isdir(root):
                continue
            paths.append(root)
            for dp, dn, _ in os.walk(root):
                for d in dn:
                    paths.append(os.path.join(dp, d))
                if len(paths) > 2000:
                    break
        if paths:
            self.watcher.addPaths(paths[:2000])

    def scan(self, folders=None, full=False):
        if self.busy:
            return
        self.busy = True
        self._cancel = False
        self.started.emit()
        self._thread = threading.Thread(target=self._run, args=(folders, full), daemon=True)
        self._thread.start()

    def cancel(self):
        self._cancel = True

    def _run(self, folders, full):
        changed = removed = 0
        try:
            roots = folders or self.lib.folders()
            existing = {r["path"]: (r["mtime"], r["filesize"]) for r in
                        self.lib.q("SELECT path, mtime, filesize FROM tracks WHERE source='local'")}
            files = []
            for root in roots:
                for dp, _dn, fn in os.walk(root):
                    for f in fn:
                        if Path(f).suffix.lower() in AUDIO_EXTS:
                            files.append((os.path.join(dp, f), root))
            total = len(files)
            seen = set()
            for i, (p, root) in enumerate(files):
                if self._cancel:
                    break
                seen.add(p)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                old = existing.get(p)
                if not full and old and abs((old[0] or 0) - st.st_mtime) < 1 and old[1] == st.st_size:
                    if i % 200 == 0:
                        self.progress.emit(i + 1, total, p)
                    continue
                d = read_tags(p)
                d.pop("lyrics", None)
                d.update(path=p, source="local", filesize=st.st_size, mtime=st.st_mtime, folder=root)
                self.lib.upsert(d, commit=False)
                changed += 1
                if changed % 50 == 0:
                    self.lib.commit()
                if i % 10 == 0 or i == total - 1:
                    self.progress.emit(i + 1, total, p)
            self.lib.commit()
            if not self._cancel and not folders:
                gone = [p for p in existing if p not in seen and not os.path.exists(p)]
                if gone:
                    self.lib.remove_paths(gone)
                    removed = len(gone)
        except Exception as e:
            print("scan error:", e)
        finally:
            self.busy = False
            self.lib.invalidate()
            self.finished.emit(changed, removed)
