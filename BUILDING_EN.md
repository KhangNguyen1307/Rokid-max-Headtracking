# Run and build from source

**English · [Tiếng Việt](BUILDING.md)**

Build environment used: Windows x64, Python 3.12.14, and the pinned versions in `requirements-build.txt`. End users of the packaged app do not need Python.

## Prepare

Open PowerShell in the source directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
```

## Run

```powershell
.\.venv\Scripts\python.exe rokid_tracker.py
```

An unmodified copy of pystray 0.19.5 is included in `third_party/pystray`. To modify or replace it, edit those files and run or rebuild the app. There is no signature or lock preventing replacement. Retain the library's LGPL license and author notices.

Translations are in `localization.py`. Saved smoothing identifiers and button action identifiers are independent of display language. To add a language, provide a complete catalog, a language selector entry, and checks for switching without changing tracking settings.

## Test

```powershell
.\.venv\Scripts\python.exe -m unittest test_localization test_game_presence test_output_scheduler test_motion_filter test_connection test_event_console
.\.venv\Scripts\python.exe rokid_tracker.py --self-check
.\.venv\Scripts\python.exe rokid_tracker.py --ui-check --ui-language vi
.\.venv\Scripts\python.exe rokid_tracker.py --ui-check --ui-language en
```

UI checks use temporary settings and logs. They may briefly read the glasses but do not enable Windows game registration. The checks exercise both languages, selection mapping, settings preservation, game button states, reset, pause/resume, and background operation.

`test_game_output` uses actual game libraries and the shared FreeTrack memory area. Run it only when Kariuss, OpenTrack, and games using head tracking are closed:

```powershell
.\.venv\Scripts\python.exe -m unittest test_game_output
```

## Package

```powershell
.\.venv\Scripts\python.exe build_app.py
```

The result is `releases/<version>/Kariuss Max Headtracking/`. Zip the entire directory when distributing it; keep `_internal` alongside the executable.

Client libraries in `game_clients/` are unmodified files from OpenTrack 2026.1.0. NPClient source is in `game_clients/npclient/`; other component sources and notices are listed in [THIRD_PARTY_EN.md](THIRD_PARTY_EN.md). When replacing client libraries, preserve compatible filenames, exported interfaces, and data layout.
