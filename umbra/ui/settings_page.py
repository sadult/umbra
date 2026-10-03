"""Settings — appearance, audio, equalizer, library, lyrics, streaming, shortcuts."""
import shutil

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QColorDialog, QComboBox, QFrame, QGridLayout, QHBoxLayout, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

from ..audio import decoder
from ..audio.dsp import EQ_FREQS, EQ_LABELS, EQ_PRESETS, eq_response
from ..config import cache_dir
from ..library import streaming
from ..theme import PRESETS
from . import icons
from .context import ctx
from .widgets import (Caption, ChipButton, FlowLayout, IconButton, PillButton, Segmented, Slider, TextField, Toggle, VSlider,
                      ask_text, confirm, font, label, paint_glass)


class Row(QWidget):
    def __init__(self, title, desc="", control=None, parent=None):
        super().__init__(parent)
        self._hover = None
        self.setMouseTracking(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 16, 12)
        lay.setSpacing(16)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label(title, 10, QFont.DemiBold))
        if desc:
            col.addWidget(label(desc, 8.4, alpha=120, wrap=True))
        lay.addLayout(col, 1)
        if control is not None:
            if isinstance(control, (list, tuple)):
                for c in control:
                    lay.addWidget(c)
            else:
                lay.addWidget(control)
        self.setMinimumHeight(58)

    def mouseMoveEvent(self, e):
        self._hover = e.position()
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_glass(p, self, QRectF(self.rect()).adjusted(1, 1, -1, -1), None, 0.7, self._hover)


def toggle(key):
    t = Toggle(bool(ctx.settings[key]))
    t.toggled.connect(lambda v: ctx.settings.set(key, v))
    return t


def seg(key, options, height=30):
    s = Segmented(options, ctx.settings[key], height=height)
    s.changed.connect(lambda v: ctx.settings.set(key, v))
    return s


class BatchLyricsCard(QWidget):
    """Settings card: fetch lyrics from LRCLIB for the whole library, with live progress."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover = None
        self.k = 0.0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 16, 16)
        lay.setSpacing(8)
        top = QHBoxLayout()
        top.setSpacing(14)
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(label("Fetch lyrics for the whole library", 10.5, QFont.DemiBold))
        col.addWidget(label("Goes through every song one by one, looks it up on LRCLIB and attaches the lyrics it finds — "
                            "synced lines when available. Songs that already have lyrics are skipped.", 8.4, alpha=120, wrap=True))
        top.addLayout(col, 1)
        self.btn = PillButton("Fetch all lyrics", "lyrics", primary=True)
        self.btn.clicked.connect(self._click)
        top.addWidget(self.btn, 0, Qt.AlignTop)
        lay.addLayout(top)
        opts = QHBoxLayout()
        opts.setSpacing(10)
        opts.addWidget(label("Save as", 8.6, alpha=150))
        opts.addWidget(seg("lyrics_batch_mode", [("lrc", ".lrc next to file"), ("embed", "Inside the file"), ("cache", "Umbra only")], 28))
        opts.addStretch()
        self.only_missing = Toggle(True)
        opts.addWidget(label("Skip songs with lyrics", 8.6, alpha=150))
        opts.addWidget(self.only_missing)
        lay.addLayout(opts)
        self.status = label("", 8.6, alpha=150)
        self.status.hide()
        lay.addWidget(self.status)
        b = ctx.lyrics_batch
        b.progress.connect(self._progress)
        b.finished.connect(self._finished)
        self._sync()

    def _click(self):
        b = ctx.lyrics_batch
        if b.running:
            b.cancel()
            self.status.setText("Stopping…")
            self.status.show()
            return
        tracks = ctx.lib.tracks("source='local'", order="artist")
        if not tracks:
            self.status.setText("Your library is empty — add a music folder first.")
            self.status.show()
            return
        b.start(tracks, ctx.settings["lyrics_batch_mode"], self.only_missing.isChecked())
        self._sync()

    def _sync(self):
        b = ctx.lyrics_batch
        self.btn.setText("Stop" if b.running else "Fetch all lyrics")
        if b.running:
            self._progress(*b.state)

    def _progress(self, done, total, found, cur):
        self.k = done / total if total else 0
        self.btn.setText("Stop" if ctx.lyrics_batch.running else "Fetch all lyrics")
        if ctx.lyrics_batch.running:
            self.status.setText(f"{done} / {total}  ·  {found} found" + (f"  ·  {cur}" if cur else ""))
            self.status.show()
        self.update()

    def _finished(self, found, total, skipped, cancelled):
        self.k = 1.0 if not cancelled else self.k
        self.btn.setText("Fetch all lyrics")
        self.status.show()
        self.status.setText(("Stopped — " if cancelled else "Done — ") +
                            f"lyrics added to {found} songs · {skipped} already had lyrics · {total} checked")
        self.update()

    def mouseMoveEvent(self, e):
        self._hover = e.position()
        self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        paint_glass(p, self, r, None, 0.7, self._hover)
        if self.k > 0:
            bar = QRectF(18, r.bottom() - 8, r.width() - 36, 3)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 18))
            p.drawRoundedRect(bar, 1.5, 1.5)
            p.setBrush(ctx.theme.acc(230))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * self.k, 3), 1.5, 1.5)


class RangeSlider(QWidget):
    """Slider mapped to [lo, hi] with live value read-out."""

    def __init__(self, key, lo, hi, fmt="{:.1f}", step=None, width=220, cast=float, on_change=None):
        super().__init__()
        self.key, self.lo, self.hi, self.fmt, self.step, self.cast = key, lo, hi, fmt, step, cast
        self.on_change = on_change
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.s = Slider(height=22, groove=4, formatter=lambda v: self.fmt.format(self._val(v)))
        self.s.setFixedWidth(width)
        self.v = label("", 8.8, QFont.DemiBold, alpha=200)
        self.v.setFont(font(8.8, QFont.DemiBold, mono=True))
        self.v.setFixedWidth(62)
        self.v.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.s)
        lay.addWidget(self.v)
        cur = float(ctx.settings[key] if key else lo)
        self.s.setValue((cur - lo) / (hi - lo))
        self.v.setText(fmt.format(cast(cur)))
        self.s.moved.connect(self._moved)
        self.s.valueChanged.connect(self._moved)

    def _val(self, v):
        x = self.lo + v * (self.hi - self.lo)
        if self.step:
            x = round(x / self.step) * self.step
        return self.cast(x)

    def _moved(self, v):
        x = self._val(v)
        self.v.setText(self.fmt.format(x))
        if self.key:
            ctx.settings.set(self.key, x)
        if self.on_change:
            self.on_change(x)

    def set_value(self, x):
        self.s.setValue((x - self.lo) / (self.hi - self.lo))
        self.v.setText(self.fmt.format(self.cast(x)))


class ThemeCard(QWidget):
    def __init__(self, name, parent=None):
        super().__init__(parent)
        self.name = name
        self.setFixedSize(150, 104)
        self.setCursor(Qt.PointingHandCursor)
        self.h = False
        ctx.settings.changed.connect(lambda k, v: k == "theme" and self.update())

    def enterEvent(self, e):
        self.h = True
        self.update()

    def leaveEvent(self, e):
        self.h = False
        self.update()

    def mouseReleaseEvent(self, e):
        # picking a theme means "use its colours" — otherwise artwork/windows accents would mask the change
        ctx.settings.set("accent_source", "theme")
        ctx.settings.set("theme", self.name)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pr = PRESETS[self.name]
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        sel = ctx.settings["theme"] == self.name
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor(pr["tint"]).lighter(160))
        g.setColorAt(1, QColor(pr["bg"]))
        p.fillPath(path, g)
        acc = QColor(pr["accent"])
        p.setPen(Qt.NoPen)
        rg = QColor(acc)
        rg.setAlpha(60)
        p.setBrush(rg)
        p.drawEllipse(QPointF(r.right() - 26, r.top() + 26), 26, 26)
        p.setBrush(acc)
        p.drawEllipse(QPointF(r.right() - 26, r.top() + 26), 10, 10)
        for i, w in enumerate((70, 50, 84)):
            p.setBrush(QColor(255, 255, 255, 50 if i else 140))
            p.drawRoundedRect(QRectF(r.left() + 14, r.top() + 18 + i * 12, w * 0.8, 5), 2.5, 2.5)
        p.setFont(font(9.5, QFont.Bold))
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(QRectF(r.left() + 14, r.bottom() - 34, r.width(), 18), Qt.AlignVCenter, self.name)
        p.setFont(font(7.4))
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(QRectF(r.left() + 14, r.bottom() - 19, r.width() - 24, 14), Qt.AlignVCenter,
                   p.fontMetrics().elidedText(pr["desc"], Qt.ElideRight, int(r.width() - 28)))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(acc if sel else QColor(255, 255, 255, 70 if self.h else 30), 2 if sel else 1))
        p.drawRoundedRect(r, 14, 14)


class EqCurve(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        ctx.settings.changed.connect(lambda k, v: (k.startswith("eq_") or k == "bass_boost") and self.update())

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        th = ctx.theme
        r = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        import math
        p.setPen(QPen(QColor(255, 255, 255, 18), 1, Qt.DashLine))
        for db in (-12, -6, 0, 6, 12):
            y = r.center().y() - db / 15 * r.height() / 2
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        for f in EQ_FREQS:
            x = r.left() + r.width() * math.log10(f / 20) / 3
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
        s = ctx.settings
        freqs, mag = eq_response(s["eq_gains"], s["eq_preamp"], s["bass_boost"])
        pts = [QPointF(r.left() + r.width() * math.log10(f / 20) / 3, r.center().y() - max(-15, min(15, m)) / 15 * r.height() / 2)
               for f, m in zip(freqs, mag)]
        path = QPainterPath(pts[0])
        for q in pts[1:]:
            path.lineTo(q)
        fill = QPainterPath(path)
        fill.lineTo(r.right(), r.center().y())
        fill.lineTo(r.left(), r.center().y())
        fill.closeSubpath()
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        g.setColorAt(0, th.acc(70))
        g.setColorAt(0.5, th.acc(10))
        g.setColorAt(1, th.acc(70))
        p.setPen(Qt.NoPen)
        p.setBrush(g)
        p.drawPath(fill)
        on = s["eq_enabled"]
        p.setPen(QPen(th.acc(80), 6))
        p.setBrush(Qt.NoBrush)
        if on:
            p.drawPath(path)
        p.setPen(QPen(QColor(255, 255, 255, 240 if on else 90), 1.6))
        p.drawPath(path)


class SettingsPage(QWidget):
    key = "settings"

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 22, 20, 8)
        lay.setSpacing(14)
        lay.addWidget(Caption("Preferences"))
        lay.addWidget(label("Settings", 30, QFont.Bold))
        self.nav = Segmented([("appearance", "Appearance"), ("audio", "Audio"), ("eq", "Equalizer"), ("library", "Library"),
                              ("lyrics", "Lyrics"), ("streaming", "Streaming"), ("keys", "Shortcuts")], "appearance", height=34)
        self.nav.changed.connect(self.show_section)
        nr = QHBoxLayout()
        nr.addWidget(self.nav)
        nr.addStretch()
        lay.addLayout(nr)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)
        self.sections = {}
        for k, fn in (("appearance", self._appearance), ("audio", self._audio), ("eq", self._eq), ("library", self._library),
                      ("lyrics", self._lyrics), ("streaming", self._streaming), ("keys", self._keys)):
            sa = QScrollArea()
            sa.setWidgetResizable(True)
            sa.setFrameShape(QFrame.NoFrame)
            sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            inner = QWidget()
            inner.setAttribute(Qt.WA_TranslucentBackground)
            v = QVBoxLayout(inner)
            v.setContentsMargins(0, 4, 10, 20)
            v.setSpacing(8)
            fn(v)
            v.addStretch()
            sa.setWidget(inner)
            self.stack.addWidget(sa)
            self.sections[k] = sa

    def load(self, section=None, **kw):
        if section:
            self.show_section(section)

    def refresh(self):
        pass

    def show_section(self, k):
        self.nav.set_current(k)
        self.stack.setCurrentWidget(self.sections[k])

    # ─────────────────────────────────────────── sections
    def _appearance(self, v):
        v.addWidget(Caption("Theme"))
        holder = QWidget()
        row = FlowLayout(holder, 10)
        for n in PRESETS:
            row.addWidget(ThemeCard(n))
        v.addWidget(holder)
        v.addSpacing(6)
        v.addWidget(Caption("Colour & atmosphere"))
        custom = ChipButton("Pick colour", "palette")
        custom.clicked.connect(self._pick_color)
        v.addWidget(Row("Accent colour", "Follow the album art, your Windows accent, your wallpaper, the theme, or pick your own.",
                        [seg("accent_source", [("theme", "Theme"), ("artwork", "Artwork"), ("windows", "Windows"),
                                               ("wallpaper", "Wallpaper"), ("custom", "Custom")]), custom]))
        v.addWidget(Row("Backdrop", "What lives behind the glass. Acrylic uses real Windows blur-behind (Win10/11).",
                        seg("backdrop", [("void", "Void"), ("artwork", "Artwork"), ("wallpaper", "Wallpaper"), ("acrylic", "Acrylic")])))
        v.addWidget(Row("Glass density", "Opacity of the frosted panels.", RangeSlider("glass_opacity", 0.1, 0.95, "{:.0%}")))
        v.addWidget(Row("Backdrop dim", "How much the backdrop is darkened.", RangeSlider("backdrop_dim", 0.2, 0.95, "{:.0%}")))
        v.addWidget(Row("Blur strength", "Frost of the artwork / wallpaper backdrop and the glass sampling it.", RangeSlider("backdrop_blur", 1, 5, "{:.0f}", 1, cast=int)))
        v.addWidget(Row("Corner radius", "Roundness of every glass island.", RangeSlider("radius", 6, 28, "{:.0f} px", 1, cast=int)))
        v.addWidget(Row("Glass highlight", "Specular light that follows your cursor across glass.", toggle("specular")))
        v.addWidget(Row("Ambient motion", "The corona behind the glass slowly breathes.", toggle("ambient_motion")))
        v.addWidget(Row("Film grain", "A whisper of analog noise over the backdrop.", toggle("grain")))
        v.addWidget(Caption("Motion"))
        v.addWidget(Row("Animations", "Transitions, morphing controls and easing everywhere.", toggle("animations")))
        v.addWidget(Row("Animation speed", "", RangeSlider("anim_speed", 0.5, 2.0, "{:.1f}×")))
        v.addWidget(Caption("Now Playing & visualizer"))
        v.addWidget(Row("Show lyrics", "Synced lyrics on the Now Playing stage. Also toggled by the small lyrics button there.",
                        toggle("np_lyrics")))
        v.addWidget(Row("Show audio analyzer", "Format, loudness and spectrum card beside the lyrics.", toggle("np_analyzer")))
        v.addWidget(Row("Show visualizer", "Spectrum strip along the bottom of Now Playing.", toggle("np_visualizer")))
        v.addWidget(Row("Visualizer style", "Used everywhere the spectrum appears.", seg("visualizer_style", [("bars", "Bars"), ("mirror", "Mirror"), ("liquid", "Flow"),
                                                             ("radial", "Radial"), ("scope", "Scope")])))
        v.addWidget(Row("Bands", "Spectrum resolution.", RangeSlider("visualizer_bands", 16, 96, "{:.0f}", 1, cast=int)))
        rs = ChipButton("Restart now", "refresh")
        rs.clicked.connect(lambda: ctx.win.restart_app())
        v.addWidget(Row("Interface scale", "Text size — applied after a restart.", [RangeSlider("font_scale", 0.85, 1.3, "{:.2f}×"), rs]))
        v.addWidget(Row("Compact sidebar", "Icons only — more room for your music.", toggle("sidebar_compact")))

    def _pick_color(self):
        c = QColorDialog.getColor(QColor(ctx.settings["custom_accent"]), self, "Accent colour")
        if c.isValid():
            ctx.settings.set("custom_accent", c.name())
            ctx.settings.set("accent_source", "custom")

    def _audio(self, v):
        eng = ctx.player.engine
        v.addWidget(Caption("Output"))
        dev = QComboBox()
        dev.addItem("System default", None)
        for i, name in eng.devices():
            dev.addItem(name, i)
        cur = ctx.settings["output_device"]
        idx = dev.findData(cur)
        dev.setCurrentIndex(max(0, idx))
        dev.setMinimumWidth(340)
        dev.currentIndexChanged.connect(lambda _: ctx.settings.set("output_device", dev.currentData()))
        v.addWidget(Row("Output device", "Choose WASAPI devices for the cleanest path on Windows." +
                        ("" if eng.available() else "  ⚠ PortAudio not available."), dev))
        v.addWidget(Row("Exclusive mode", "WASAPI exclusive — bypasses the Windows mixer for bit-perfect output.", toggle("exclusive")))
        v.addWidget(Row("Buffer", "Lower = snappier, higher = safer on busy systems.", RangeSlider("buffer_ms", 40, 500, "{:.0f} ms", 10, cast=int)))
        v.addWidget(Caption("Transitions"))
        v.addWidget(Row("Gapless playback", "Seamless joins between consecutive tracks (live albums, DJ mixes).", toggle("gapless")))
        v.addWidget(Row("Crossfade", "Equal-power crossfade between tracks. 0 = off.", RangeSlider("crossfade", 0, 12, "{:.1f} s", 0.5)))
        v.addWidget(Row("Fade on pause / resume", "Click-free soft fades.", RangeSlider("fade_pause_ms", 0, 1000, "{:.0f} ms", 10, cast=int)))
        v.addWidget(Caption("Loudness"))
        v.addWidget(Row("Volume leveling", "ReplayGain from tags, or Smart: Umbra measures each track (EBU R128) as you listen.",
                        seg("leveling", [("off", "Off"), ("rg_track", "RG Track"), ("rg_album", "RG Album"), ("smart", "Smart LUFS")])))
        v.addWidget(Row("Smart target", "Target integrated loudness.", RangeSlider("leveling_target", -23, -8, "{:.0f} LUFS", 1)))
        v.addWidget(Row("Pre-amp", "Extra gain applied with leveling.", RangeSlider("leveling_preamp", -12, 12, "{:+.1f} dB", 0.5)))
        v.addWidget(Row("Soft limiter", "Transparent tanh limiter that prevents clipping.", toggle("limiter")))
        v.addWidget(Caption("Stereo"))
        v.addWidget(Row("Balance", "", RangeSlider("balance", -1, 1, "{:+.2f}", 0.05)))
        v.addWidget(Row("Stereo width", "0 = mono, 1 = original, 2 = extra wide (M/S).", RangeSlider("stereo_width", 0, 2, "{:.2f}×", 0.05)))
        v.addWidget(Row("Mono downmix", "", toggle("mono")))
        v.addWidget(Row("Swap channels", "", toggle("swap_channels")))
        v.addWidget(Caption("Behaviour"))
        v.addWidget(Row("Count a play after", "Fraction of a track that must be heard (or 4 min).",
                        RangeSlider("play_count_threshold", 0.1, 1.0, "{:.0%}", 0.05)))
        v.addWidget(Row("Resume last session", "Restore queue and position on launch.", toggle("resume_session")))

    def _eq(self, v):
        s = ctx.settings
        top = QHBoxLayout()
        top.setSpacing(10)
        en = toggle("eq_enabled")
        top.addWidget(label("Equalizer", 14, QFont.Bold))
        top.addWidget(en)
        top.addStretch()
        self.preset = QComboBox()
        self.preset.addItems(list(EQ_PRESETS) + list(s["eq_custom"].keys()))
        self.preset.setCurrentText(s["eq_preset"])
        self.preset.currentTextChanged.connect(self._apply_preset)
        top.addWidget(self.preset)
        sv = ChipButton("Save preset", "plus")
        sv.clicked.connect(self._save_preset)
        rs = ChipButton("Reset", "refresh")
        rs.clicked.connect(lambda: self._apply_preset("Flat"))
        top.addWidget(sv)
        top.addWidget(rs)
        v.addLayout(top)
        box = QWidget()
        bl = QVBoxLayout(box)
        bl.setContentsMargins(18, 14, 18, 14)
        box.paintEvent = lambda e: self._paint_box(box)
        bl.addWidget(EqCurve())
        sl = QHBoxLayout()
        sl.setSpacing(4)
        self.pre = VSlider("PRE", -12, 12, s["eq_preamp"])
        self.pre.valueChanged.connect(lambda x: s.set("eq_preamp", x))
        sl.addWidget(self.pre)
        sl.addSpacing(16)
        self.bands = []
        for i, lab in enumerate(EQ_LABELS):
            b = VSlider(lab, -12, 12, s["eq_gains"][i])
            b.valueChanged.connect(lambda x, i=i: self._band(i, x))
            sl.addWidget(b)
            self.bands.append(b)
        sl.addSpacing(16)
        self.bass = VSlider("BASS", 0, 12, s["bass_boost"])
        self.bass.valueChanged.connect(lambda x: s.set("bass_boost", x))
        sl.addWidget(self.bass)
        bl.addLayout(sl)
        box.setMinimumHeight(400)
        v.addWidget(box)
        v.addWidget(label("Double-click a fader to reset it · scroll for 0.5 dB steps · the soft limiter protects against clipping.", 8.4, alpha=110))

    def _paint_box(self, w):
        p = QPainter(w)
        p.setRenderHint(QPainter.Antialiasing)
        paint_glass(p, w, QRectF(w.rect()).adjusted(1, 1, -1, -1), None, 0.8)

    def _band(self, i, x):
        g = list(ctx.settings["eq_gains"])
        g[i] = x
        ctx.settings.set("eq_gains", g)
        if not ctx.settings["eq_enabled"]:
            ctx.settings.set("eq_enabled", True)

    def _apply_preset(self, name):
        s = ctx.settings
        g = EQ_PRESETS.get(name) or s["eq_custom"].get(name)
        if g is None:
            return
        s.set("eq_gains", [float(x) for x in g])
        s.set("eq_preset", name)
        for b, x in zip(self.bands, g):
            b.setValue(x)
        if self.preset.currentText() != name:
            self.preset.setCurrentText(name)

    def _save_preset(self):
        n = ask_text(ctx.win, "Save EQ preset", "Preset name", "My preset")
        if n:
            c = dict(ctx.settings["eq_custom"])
            c[n] = list(ctx.settings["eq_gains"])
            ctx.settings.set("eq_custom", c)
            self.preset.addItem(n)
            self.preset.setCurrentText(n)

    def _library(self, v):
        v.addWidget(Caption("Sources"))
        b = PillButton("Manage folders", "folder", primary=True)
        b.clicked.connect(lambda: ctx.win.navigate("folders"))
        v.addWidget(Row("Music folders", f"{len(ctx.lib.folders())} referenced folders.", b))
        v.addWidget(Row("Scan on startup", "Pick up changes made while Umbra was closed.", toggle("scan_on_start")))
        v.addWidget(Row("Watch folders", "Detect new, changed and removed files live.", toggle("watch_folders")))
        names = TextField(ctx.settings["folder_art_names"])
        names.setFixedWidth(280)
        names.editingFinished.connect(lambda: ctx.settings.set("folder_art_names", names.text()))
        v.addWidget(Row("Folder artwork names", "Used when a file has no embedded cover.", names))
        v.addWidget(Caption("Maintenance"))
        c1 = ChipButton("Clear", "trash")
        c1.clicked.connect(lambda: (shutil.rmtree(cache_dir("art"), ignore_errors=True), ctx.art.images.clear(),
                                    ctx.art.pix.clear(), ctx.toast("Artwork cache cleared", "trash")))
        v.addWidget(Row("Artwork cache", "Thumbnails are regenerated on demand.", c1))
        c2 = ChipButton("Reset", "refresh")
        c2.clicked.connect(self._reset_stats)
        v.addWidget(Row("Play statistics", "Reset play counts, skips and history.", c2))
        c3 = ChipButton("Re-read all", "tag")
        c3.clicked.connect(lambda: ctx.scanner.scan(full=True))
        v.addWidget(Row("Rebuild library", "Re-read every tag from disk.", c3))

    def _reset_stats(self):
        if confirm(ctx.win, "Reset statistics", "Reset all play counts, skips and history? This cannot be undone.", "Reset"):
            ctx.lib.x("UPDATE tracks SET play_count=0, skip_count=0, last_played=NULL")
            ctx.lib.x("DELETE FROM history")
            ctx.lib.invalidate()
            ctx.win.library_changed()

    def _lyrics(self, v):
        v.addWidget(Row("Online lyrics", "Fetch synced lyrics from LRCLIB when no .lrc or embedded lyrics exist.", toggle("online_lyrics")))
        v.addWidget(BatchLyricsCard())
        v.addWidget(Row("Text size", "", RangeSlider("lyrics_size", 16, 40, "{:.0f} pt", 1, cast=int)))
        v.addWidget(Row("Alignment", "", seg("lyrics_align", [("left", "Left"), ("center", "Center"), ("right", "Right")])))
        v.addWidget(Row("Sync offset", "Shift synced lyrics earlier / later.", RangeSlider("lyrics_offset", -3, 3, "{:+.1f} s", 0.1)))
        c = ChipButton("Clear", "trash")
        c.clicked.connect(lambda: (shutil.rmtree(cache_dir("lyrics"), ignore_errors=True), ctx.toast("Lyrics cache cleared", "trash")))
        v.addWidget(Row("Lyrics cache", "Downloaded lyrics are cached locally.", c))
        v.addWidget(label("Priority:  side-car .lrc  →  embedded tag (USLT / LYRICS)  →  LRCLIB.   Click any synced line to seek.", 8.6, alpha=120))

    def _streaming(self, v):
        def status(ok, yes, no):
            l = label(("●  " + yes) if ok else ("○  " + no), 9, QFont.DemiBold)
            l.setStyleSheet(f"color: {'#7de8a8' if ok else '#ff8a8a'}; background: transparent;")
            return l
        v.addWidget(Row("yt-dlp", "Streaming bridge for YouTube Music and Spotify imports.",
                        status(streaming.available(), "installed", "pip install yt-dlp")))
        v.addWidget(Row("FFmpeg", "Decodes streams and formats libsndfile can't (AAC/M4A, WMA, APE…).",
                        status(bool(decoder.FFMPEG), "found on PATH", "install FFmpeg & add to PATH")))
        v.addWidget(Row("ytmusicapi (optional)", "Cleaner YouTube Music song search with albums & artists.",
                        status(streaming.YTMusic is not None, "installed", "pip install ytmusicapi")))
        v.addWidget(Row("Enable streaming", "Show streaming services in the sidebar.", toggle("streaming_enabled")))
        v.addWidget(Caption("Downloads"))
        from ..library.downloader import default_dir
        dl_lbl = label(ctx.settings["download_dir"] or default_dir(), 8.6, alpha=150)
        pick = ChipButton("Change…", "folder")

        def choose():
            from PySide6.QtWidgets import QFileDialog
            d = QFileDialog.getExistingDirectory(self, "Download folder", ctx.settings["download_dir"] or default_dir())
            if d:
                ctx.settings.set("download_dir", d)
                dl_lbl.setText(d)
        pick.clicked.connect(choose)
        v.addWidget(Row("Download folder", "YouTube Music and Spotify tracks are saved here, tagged with cover art.", [dl_lbl, pick]))
        v.addWidget(Row("Format", "Re-encoding needs FFmpeg; without it the original stream (M4A/WebM) is kept.",
                        seg("download_format", [("m4a", "M4A"), ("mp3", "MP3 320"), ("opus", "Opus"), ("flac", "FLAC")])))
        v.addWidget(Row("Browser cookies", "If YouTube says \"confirm you're not a bot\", let yt-dlp use your signed-in browser's cookies.",
                        seg("ytdlp_cookies", [("none", "Off"), ("chrome", "Chrome"), ("edge", "Edge"), ("firefox", "Firefox"), ("brave", "Brave")])))
        v.addWidget(Row("Add downloads to library", "Watch the download folder as a library folder.", toggle("download_add_library")))
        v.addWidget(Row("Auto-download on sync", "When a saved Spotify / YouTube playlist is synced, download its new tracks.",
                        toggle("playlist_autodownload")))
        v.addWidget(Caption("Spotify"))
        cid = TextField(ctx.settings["spotify_client_id"] or "", "Client ID")
        cid.setFixedWidth(260)
        cid.editingFinished.connect(lambda: ctx.settings.set("spotify_client_id", cid.text().strip()))
        sec = TextField(ctx.settings["spotify_client_secret"] or "", "Client secret")
        sec.setEchoMode(TextField.Password)
        sec.setFixedWidth(260)
        sec.editingFinished.connect(lambda: ctx.settings.set("spotify_client_secret", sec.text().strip()))
        v.addWidget(Row("Spotify API (optional)", "Without keys Umbra reads the first 100 tracks of a playlist. Create a free app at "
                        "developer.spotify.com and paste its Client ID / secret to import full playlists.", [cid, sec]))
        v.addWidget(label("Spotify does not permit third-party audio streaming. Umbra imports public Spotify tracks, albums "
                          "and playlists as metadata and plays the closest match from YouTube.", 8.6, alpha=120, wrap=True))

    def _keys(self, v):
        keys = [("Space", "Play / pause"), ("Ctrl + → / ←", "Next / previous track"), ("→ / ←", "Seek ±5 s"),
                ("Shift + → / ←", "Seek ±30 s"), ("Ctrl + ↑ / ↓", "Volume"), ("M", "Mute"), ("Ctrl + K  /  Ctrl + F", "Search"),
                ("Ctrl + S", "Toggle shuffle"), ("Ctrl + R", "Cycle repeat"), ("Ctrl + D", "Favorite current track"),
                ("Ctrl + L", "Lyrics panel"), ("Ctrl + Q", "Queue panel"), ("Ctrl + E", "Edit tags of current track"),
                ("Ctrl + M", "Mini player"), ("Ctrl + Shift + M", "Small player"), ("F11", "Immersive Now Playing"), ("Ctrl + ,", "Settings"),
                ("Alt + ← / →", "Back / forward"), ("Media keys", "Global play/pause, next, previous, stop")]
        for k, d in keys:
            kl = label(k, 9, QFont.DemiBold)
            kl.setFont(font(9, QFont.DemiBold, mono=True))
            v.addWidget(Row(d, "", kl))
