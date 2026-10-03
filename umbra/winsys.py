"""Windows integration: accent colour, wallpaper, acrylic blur, media keys. Safe no-ops elsewhere."""
import ctypes
import sys

IS_WIN = sys.platform == "win32"


def accent_color():
    """Return '#rrggbb' of the Windows accent colour or None."""
    if not IS_WIN:
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\DWM") as k:
            try:
                v, _ = winreg.QueryValueEx(k, "AccentColor")       # 0xAABBGGRR
                r, g, b = v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF
            except OSError:
                v, _ = winreg.QueryValueEx(k, "ColorizationColor")  # 0xAARRGGBB
                r, g, b = (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return None


def wallpaper_path():
    if not IS_WIN:
        return None
    try:
        buf = ctypes.create_unicode_buffer(520)
        ctypes.windll.user32.SystemParametersInfoW(0x0073, 520, buf, 0)  # SPI_GETDESKWALLPAPER
        return buf.value or None
    except Exception:
        return None


class _ACCENT(ctypes.Structure):
    _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]


class _WCAD(ctypes.Structure):
    _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.c_void_p), ("SizeOfData", ctypes.c_size_t)]


def set_acrylic(hwnd: int, enable=True, tint=0x99101014):
    """Real Windows acrylic blur behind a frameless translucent window (Win10 1803+/Win11)."""
    if not IS_WIN:
        return False
    try:
        accent = _ACCENT()
        accent.AccentState = 4 if enable else 0        # ACCENT_ENABLE_ACRYLICBLURBEHIND
        accent.AccentFlags = 2
        # GradientColor is AABBGGRR
        a, r, g, b = (tint >> 24) & 0xFF, (tint >> 16) & 0xFF, (tint >> 8) & 0xFF, tint & 0xFF
        accent.GradientColor = (a << 24) | (b << 16) | (g << 8) | r
        data = _WCAD()
        data.Attribute = 19                             # WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.c_void_p)
        data.SizeOfData = ctypes.sizeof(accent)
        ctypes.windll.user32.SetWindowCompositionAttribute(ctypes.c_void_p(hwnd), ctypes.byref(data))
        return True
    except Exception:
        return False


def set_dark_frame(hwnd: int):
    if not IS_WIN:
        return
    try:
        dwm = ctypes.windll.dwmapi
        v = ctypes.c_int(1)
        dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 20, ctypes.byref(v), 4)   # immersive dark mode
        pref = ctypes.c_int(2)
        dwm.DwmSetWindowAttribute(ctypes.c_void_p(hwnd), 33, ctypes.byref(pref), 4)  # round corners
    except Exception:
        pass


def set_app_id(app_id="Umbra.MusicPlayer"):
    if IS_WIN:
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass


# ── Global media keys via RegisterHotKey + Qt native event filter
VK = {"playpause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2}

if IS_WIN:
    from PySide6.QtCore import QAbstractNativeEventFilter
    from ctypes import wintypes

    class MediaKeyFilter(QAbstractNativeEventFilter):
        def __init__(self, callback):
            super().__init__()
            self.cb = callback
            self.ids = {}
            for i, (name, vk) in enumerate(VK.items(), start=0xBE00):
                if ctypes.windll.user32.RegisterHotKey(None, i, 0x4000, vk):  # MOD_NOREPEAT
                    self.ids[i] = name

        def nativeEventFilter(self, etype, message):
            try:
                if etype == b"windows_generic_MSG" or etype == "windows_generic_MSG":
                    msg = wintypes.MSG.from_address(int(message))
                    if msg.message == 0x0312 and msg.wParam in self.ids:
                        self.cb(self.ids[msg.wParam])
                        return True, 0
            except Exception:
                pass
            return False, 0
else:
    MediaKeyFilter = None
