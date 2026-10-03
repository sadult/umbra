"""Shared application context (set up by the main window)."""


class _Ctx:
    lib = None
    player = None
    settings = None
    theme = None
    art = None
    win = None
    scanner = None
    lyrics = None
    downloads = None
    lyrics_batch = None

    def toast(self, text, icon="check"):
        if self.win:
            self.win.toast.show_msg(text, icon)


ctx = _Ctx()
