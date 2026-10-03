# Contributing to Umbra

Thanks for helping make Umbra better! ✦

## Reporting bugs & ideas

Use the [issue forms](https://github.com/sadult/umbra/issues/new/choose). Please search existing issues first.

## Development setup

```powershell
git clone https://github.com/sadult/umbra.git
cd umbra
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt pyflakes
python main.py
```

FFmpeg on `PATH` is recommended (`winget install Gyan.FFmpeg`).

## Pull requests

1. Fork the repo and create a branch: `git checkout -b feature/my-idea`
2. Keep changes focused — one feature or fix per PR
3. Follow the existing style: PySide6, hand-painted widgets, no external UI assets
4. Run `python -m pyflakes umbra` before committing
5. Add screenshots for UI changes and update `CHANGELOG.md` for user-facing changes
6. Open the PR against `main`

## Commit messages

```
Add: sleep timer in mini player
Fix: lyrics not loading for FLAC files
Improve: faster library scan
Docs: update screenshots
```

By contributing you agree that your work is released under the [MIT License](LICENSE).
