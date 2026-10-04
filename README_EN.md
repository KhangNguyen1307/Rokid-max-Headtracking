# Kariuss Max Headtracking

**English · [Tiếng Việt](README.md)**

<img src="assets/kariuss.png" alt="Kariuss Max Headtracking" width="96">

Head tracking with **Rokid Max on Windows**, connected directly to games through FreeTrack / TrackIR. You do not need to run the OpenTrack application separately.

**Trial release 1.8.0 — English / Vietnamese.** The tracking functionality has been tested by the user with Rokid Max and Microsoft Flight Simulator 2024. Other glasses and games have not been verified.

## Download

Open [Releases](https://github.com/KhangNguyen1307/Rokid-max-Headtracking/releases), download the **Windows x64** ZIP, extract the entire archive, and open **Kariuss Max Headtracking.exe**. Keep the `_internal` folder beside the executable. Python is not required for the packaged application.

## Quick start

1. Connect Rokid Max to a USB port on your PC that supports data transfer.
2. Open the app. Use the device dropdown if more than one pair of glasses is connected. Device names do not display serial numbers.
3. **Place the glasses on a flat surface for 6 seconds to calibrate.**
4. Put on the glasses, look straight ahead, and click **Reset view** or press **F8**.
5. Close OpenTrack if it is running. Click **Connect to game**, open your game, and enter the cockpit.
6. If your game does not detect tracking, leave the Kariuss game connection enabled and restart the game. Enable head tracking / TrackIR in the game's settings if it has such an option.

Use the **English / Tiếng Việt** dropdown in the top-right corner to change language instantly. Buttons, connection status, visible activity history, and system tray menus follow the selected language. The app remembers your choice, without changing tracking settings. Existing users upgrading from 1.7.1 keep Vietnamese. New installations default to English unless the Windows display language is Vietnamese.

| Connect to game button | Meaning |
|---|---|
| Green | A game has registered and its receiving component is loaded in a running process |
| Red | Connection is enabled but no game is connected, or enabling the connection failed |
| Gray | Game connection is disabled |

The app checks running game processes about once per second. Green indicates a detected connection, not confirmation that the game consumed every update.

## Features

- Compact 3D glasses model on the home screen, showing turn left/right, look up/down, and head tilt.
- Reset view, pause/resume, and invert each axis independently.
- USB reconnection after unplugging and reconnecting the cable; Connect / Disconnect and Rescan USB controls.
- Close the window with × to keep tracking in the system tray. Reopen it from the tray icon near the Windows clock, or launch the app again. Choose **Quit app** to stop completely.
- Timestamped activity log and automatically saved settings.
- Assign extra actions to glasses buttons. By default, two opposite volume presses within 0.8 seconds reset the view.

### Smoothing and sensitivity

| Level | Effect |
|---|---|
| Off | Disables the additional smoothing layer |
| Light | Less filtering, faster response |
| Medium | Default; uses adaptive smoothing derived from OpenTrack's Accela filter |
| Strong | More smoothing, slower response |

Default sensitivity is **80%**: after the filter catches up, a 30° head turn produces approximately 24° sent to the game. The model shows the actual glasses orientation rather than the sensitivity-scaled game output.

**Output rate:** 44.4 / 50 / 80 / 100 / 140 / 200 Hz; default 100 Hz. This controls outgoing view updates per second, independently of incoming sensor packets. Actual output may be lower when the PC is busy. Reset is processed immediately. Changing the language preserves the selected level, sensitivity, rate, and axis directions.

### Glasses buttons

Each button can keep its original function, reset the view, or pause/resume tracking. These extra actions cannot suppress the glasses' own brightness or volume behavior.

To reset without changing brightness, use **F8** or press volume up then down (or down then up) within **0.8 seconds**, returning to the original volume level. At maximum volume, use down then up; at minimum volume, use up then down. With the paired gesture enabled, individual volume actions may wait up to 0.8 seconds. Pressing a button at its limit may not produce a detectable state change.

Pausing freezes the orientation sent to the game; the model continues to show movement. Resuming uses your current direction as the new center.

## Displaying video and future FPV support

The app reads motion sensors. Displaying video on the glasses requires a separate video connection from the PC. A data-only USB-C port cannot provide a picture. If using an HDMI/DisplayPort-to-USB-C adapter, check that it also carries USB data back to the PC so the glasses remain detectable.

**Real FPV camera control is not implemented.** Output rate choices help prepare for future development, but there are no PPM, PWM, SBUS, or CRSF outputs. [HeadTracker](https://github.com/headtracker/HeadTracker) was consulted for rate references; its firmware code is not included in this app.

## Limitations

- Only three rotational axes are tracked; position X/Y/Z sent to the game is always zero.
- The heading may drift. Press F8 to reset the center.
- The app cannot block the glasses' original brightness and volume button functions.
- Direct game output uses bundled compatibility libraries from OpenTrack. A small `TrackIR.exe` helper runs in the background; the OpenTrack application is not launched.
- There is no installer or automatic updater. This is a trial release, not FPV flight-control software.
- Activity log timestamps currently use UTC+7 and the format `HH:mm:ss DD/MM/YYYY`. Switching language retranslates visible history while preserving event timestamps; previously written log file lines stay as originally recorded.

## Source and building

See [BUILDING_EN.md](BUILDING_EN.md) for running, testing, and packaging on Windows x64 with Python 3.12. Dependency sources and replacement instructions are listed in [THIRD_PARTY_EN.md](THIRD_PARTY_EN.md).

Packaged app settings and logs are stored in `%LOCALAPPDATA%/Kariuss Max Headtracking`. These files are excluded from the repository. Redact personal information from screenshots or logs before posting an issue.

To upgrade manually, quit the running app, extract the new Windows ZIP into a new folder, and open its executable. Preferences in the location above are reused.

## License and credits

Kariuss source is released under **GNU GPL v3.0**; see [LICENSE](LICENSE). Third-party components retain their own licenses and author notices; see [THIRD_PARTY_EN.md](THIRD_PARTY_EN.md) and `licenses/`.

Credits: [OpenTrack](https://github.com/opentrack/opentrack), [VQF](https://github.com/dlaidig/vqf), [ar-drivers-rs](https://github.com/badicsalex/ar-drivers-rs) for the Rokid packet layout reference, [pystray](https://github.com/moses-palmer/pystray), and [cython-hidapi](https://github.com/trezor/cython-hidapi).
