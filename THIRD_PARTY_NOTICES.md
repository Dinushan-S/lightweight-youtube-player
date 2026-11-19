# Third-party software

Lightweight YouTube Player's own code is MIT-licensed (see [LICENSE](LICENSE)). The Windows `.exe` release also bundles the programs and libraries below, each under its own license.

| Component | Version | License | Source |
|---|---|---|---|
| [mpv](https://mpv.io) (`mpv.exe`, with FFmpeg and libplacebo built in) | 0.41.0-dev (git 41f6a6450) | GPL-2.0-or-later | https://github.com/mpv-player/mpv |
| Vulkan loader (`vulkan-1.dll`, shipped with mpv) | from the mpv build | Apache-2.0 | https://github.com/KhronosGroup/Vulkan-Loader |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | 2026.10.26 | Unlicense | https://github.com/yt-dlp/yt-dlp |
| [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter) | 6.0.0 | as published on PyPI (see its repository) | https://github.com/TomSchimansky/CustomTkinter |
| [darkdetect](https://github.com/albertosottile/darkdetect) | 0.8.0 | BSD-3-Clause | https://github.com/albertosottile/darkdetect |
| [Pillow](https://python-pillow.org) | 13.0.0 | MIT-CMU | https://github.com/python-pillow/Pillow |
| [pywin32](https://github.com/mhammond/pywin32) | 312 | PSF | https://github.com/mhammond/pywin32 |
| Python | 3.12 | PSF License | https://www.python.org |
| [PyInstaller](https://pyinstaller.org) bootloader | 6.22.3 | GPL-2.0-or-later with the PyInstaller bootloader exception | https://github.com/pyinstaller/pyinstaller |

## About mpv

mpv runs as a separate program that the player starts and controls over a named pipe; the player's code is not linked with it. mpv is free software under the GNU General Public License, version 2 or later. You can get the complete corresponding source code for the bundled build from the mpv repository at the commit listed above (`git checkout 41f6a6450`). The GPL text is at https://www.gnu.org/licenses/old-licenses/gpl-2.0.html.

mpv and FFmpeg are trademarks or projects of their respective owners. This project is not affiliated with mpv, FFmpeg, yt-dlp or YouTube.
