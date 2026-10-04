# Third-party components and licenses

**English · [Tiếng Việt](THIRD_PARTY.md)**

Kariuss's GPL-3.0 license does not replace the separate licenses of the components below. Releases include these notices and the `licenses/` directory.

| Component | Version / source | License and notices |
|---|---|---|
| Accela smoothing approach and spline response curve | Adapted to Python from OpenTrack; Stanislaw Halik, 2012–2019 | Permission and warranty notices retained in `motion_filter.py` and `game_clients/README-KARIUSS.txt` |
| NPClient32/64, FreeTrack32/64, TrackIR helper, game list | Unmodified files from OpenTrack 2026.1.0 | `game_clients/OPENTRACK-LICENSING.txt`, `FACETRACKNOIR-COPYING.txt`; source: https://github.com/opentrack/opentrack |
| NPClient / linuxtrack | Source in `game_clients/npclient/`; Tulthix, uglyDwarf | MIT; `licenses/linuxtrack-MIT.txt`; https://github.com/uglyDwarf/linuxtrack |
| pystray | 0.19.5; unmodified source in `third_party/pystray/` | LGPL-3.0-or-later; `licenses/pystray-LGPL-3.0.txt`, `licenses/GPL-3.0.txt`; https://github.com/moses-palmer/pystray/tree/v0.19.5 |
| VQF | 2.1.2 | MIT; `licenses/vqf-LICENSE.txt`; https://github.com/dlaidig/vqf |
| cython-hidapi / HIDAPI | 0.15.0 | BSD / original license chosen for this component; notices and alternative licenses in `licenses/hidapi-*.txt`; https://github.com/trezor/cython-hidapi |
| NumPy | 2.3.5 | BSD and bundled library notices; `licenses/numpy-LICENSE.txt`; https://github.com/numpy/numpy |
| Pillow | 12.3.0 | HPND / PIL and bundled component licenses; `licenses/Pillow-LICENSE*`; https://github.com/python-pillow/Pillow |
| six | 1.17.0 | MIT; `licenses/six-LICENSE`; https://github.com/benjaminp/six |
| Python and Tcl/Tk | Python 3.12 runtime | Runtime licenses in `licenses/`, `_internal/_tcl_data/license.terms`, and `_internal/_tk_data/license.terms` in packaged builds |
| PyInstaller bootloader | 6.22.0 | GPL with bootloader exception; `licenses/pyinstaller-COPYING.txt`; https://github.com/pyinstaller/pyinstaller |

Kariuss source, build instructions, and the bundled pystray source allow rebuilding the app with a modified library. Other dependencies have pinned versions in `requirements*.txt`; official sources are listed above.

The Rokid packet layout was referenced from https://github.com/badicsalex/ar-drivers-rs/blob/master/src/rokid.rs. Motion fusion uses VQF. No HeadTracker firmware code is included; FPV output rates were referenced from https://github.com/headtracker/HeadTracker.

Kariuss is a community project and does not claim certification or endorsement by Rokid, OpenTrack, or Microsoft.
