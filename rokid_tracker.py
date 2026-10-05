# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Local Rokid Max HID reader with direct game output. No commands are sent to glasses.

Packet layout: https://github.com/badicsalex/ar-drivers-rs/blob/master/src/rokid.rs
Fusion: https://github.com/dlaidig/vqf (MIT); hidapi Python bindings (BSD).
"""
import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FROZEN = bool(getattr(sys, 'frozen', False))
APP_NAME = 'Kariuss Max Headtracking'
APP_VERSION = '1.9.0'
CALIBRATION_MESSAGE = 'Đặt trên mặt phẳng 6 giây để kính hiệu chỉnh'
CONTROL_ROOT = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / APP_NAME
CONTROL_ROOT.mkdir(parents=True, exist_ok=True)
DATA_ROOT = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / APP_NAME if FROZEN else ROOT
DATA_ROOT.mkdir(parents=True, exist_ok=True)
if not FROZEN:
    sys.path.insert(0, str(ROOT / 'vendor'))
    sys.path.insert(0, str(ROOT / 'third_party'))
if sys.stdout is None:
    sys.stdout = (DATA_ROOT / 'app.log').open('a', encoding='utf-8', buffering=1)
if sys.stderr is None:
    sys.stderr = sys.stdout
import argparse
import collections
import json
import queue
import math
import struct
import threading
import time
import numpy as np
import hid
from vqf import VQF


def decode(packet):
    if len(packet) != 64 or packet[0] != 17:
        return None
    timestamp = struct.unpack_from('<Q', bytes(packet), 1)[0]
    values = np.array(struct.unpack_from('<9f', bytes(packet), 9), dtype=np.float64)
    if not np.isfinite(values).all():
        return None
    return timestamp, values[:3], values[3:6]


def multiply(a, b):
    w, x, y, z = a
    v, i, j, k = b
    return np.array([w*v-x*i-y*j-z*k, w*i+x*v+y*k-z*j,
                     w*j-x*k+y*v+z*i, w*k+x*j-y*i+z*v])


def angles(reference, current):
    relative = multiply(reference * np.array([1, -1, -1, -1]), current)
    relative /= np.linalg.norm(relative)
    w, x, y, z = relative
    # Sensor Y is vertical on the original Rokid Max. Y-X-Z decomposition.
    pitch = math.asin(max(-1.0, min(1.0, 2*(w*x-y*z))))
    yaw = math.atan2(2*(x*z+w*y), 1-2*(x*x+y*y))
    roll = math.atan2(2*(x*y+w*z), 1-2*(x*x+z*z))
    return tuple(math.degrees(a) for a in (yaw, pitch, roll))


ACTION_LABELS = {'native': 'Giữ chức năng gốc', 'center': 'Nhìn về giữa',
                 'pause': 'Tạm dừng / tiếp tục nhìn theo đầu'}
BUTTON_LABELS = {'volume_up': 'Nút tăng âm lượng', 'volume_down': 'Nút giảm âm lượng',
                 'brightness': 'Nút độ sáng', 'volume_pair': 'Bấm tăng rồi giảm, hoặc giảm rồi tăng'}


class ButtonRouter:
    """Detect a volume round trip, deferring single actions to avoid double firing.

    Changes are device state observations, not key-down events. Native actions
    already happened on the glasses; this class never claims to suppress them.
    """
    window = 0.8

    def __init__(self, mappings):
        self.mappings = mappings
        self.pending = None

    def reset(self):
        self.pending = None

    def action(self, button):
        action = self.mappings.get(button, 'native')
        return [] if action == 'native' else [(button, action)]

    def flush(self, now):
        if self.pending is not None and now - self.pending[3] > self.window:
            button, _, _, _ = self.pending
            self.pending = None
            return self.action(button)
        return []

    def feed(self, event):
        kind, before, after, now = event
        actions = self.flush(now)
        if before == after:
            return actions
        if kind == 'brightness':
            return actions + self.action('brightness')
        if kind != 'volume':
            return actions
        button = 'volume_up' if after > before else 'volume_down'
        if self.mappings.get('volume_pair', 'native') == 'native':
            return actions + self.action(button)
        if self.pending is not None:
            first_button, baseline, previous, _ = self.pending
            self.pending = None
            if before == previous and after == baseline:
                return actions + self.action('volume_pair')
            actions += self.action(first_button)
        self.pending = (button, before, after, now)
        return actions


def find_glasses():
    return [d for d in hid.enumerate(0x04d2, 0x162f)
            if d.get('interface_number') == 2 or d.get('usage_page') == 0xff00]


class UsbDiscovery:
    """Enumerate away from the UI so a slow USB driver cannot freeze the window."""
    def __init__(self):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.devices = []
        self.thread = threading.Thread(target=self.run, daemon=True)

    def snapshot(self):
        with self.lock:
            return list(self.devices)

    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            try:
                devices = find_glasses()
            except Exception:
                devices = []
            with self.lock:
                self.devices = devices
            self.wake.wait(1.5)


class Reader:
    def __init__(self, enumerator=find_glasses, device_factory=hid.device,
                 settle_seconds=6, retry_seconds=0.75):
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.center_requested = threading.Event()
        self.pose = (0.0, 0.0, 0.0)
        self.reference = None
        self.q = None
        self.rate = 0.0
        self.count = 0
        self.updated = 0.0
        self.ready = False
        self.status = 'Đang tìm kính…'
        self.error = None
        self.button_state = None
        self.button_events = collections.deque(maxlen=128)
        self.center_generation = 0
        self.enumerator = enumerator
        self.device_factory = device_factory
        self.settle_seconds = settle_seconds
        self.retry_seconds = retry_seconds
        self.connection_enabled = True
        self.connected = False
        self.selection = None
        self.connection_revision = 0
        self.connection_session = 0
        self.wake = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def snapshot(self):
        with self.lock:
            return dict(status=self.status, ready=self.ready, error=self.error,
                        samples=self.count, samples_per_second=round(self.rate, 1),
                        buttons=dict(self.button_state) if self.button_state else None,
                        center_generation=self.center_generation,
                        connection_enabled=self.connection_enabled, connected=self.connected,
                        connection_session=self.connection_session,
                        angles_deg=list(self.pose), age_s=round(time.monotonic()-self.updated, 3)
                        if self.updated else None)

    def take_buttons(self):
        with self.lock:
            events = list(self.button_events)
            self.button_events.clear()
            return events

    def reset_connection(self):
        # Caller holds self.lock. Never keep a pose or button baseline from an old handle.
        self.ready = self.connected = False
        self.updated = self.rate = 0.0
        self.reference = self.q = self.button_state = None
        self.pose = (0.0, 0.0, 0.0)
        self.button_events.clear()
        self.center_requested.clear()

    def request_connection(self, enabled, selection=None):
        with self.lock:
            self.connection_enabled = bool(enabled)
            self.selection = dict(selection) if selection else None
            self.connection_revision += 1
            self.reset_connection()
            self.error = None
            self.status = 'Đang kết nối với kính…' if enabled else 'Đã ngắt kết nối. Bấm Kết nối kính để dùng lại.'
        self.wake.set()

    def current_connection(self, revision):
        with self.lock:
            return self.connection_enabled and self.connection_revision == revision

    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            with self.lock:
                enabled, revision, selection = self.connection_enabled, self.connection_revision, self.selection
            if not enabled:
                self.wake.wait(0.5)
                continue
            self.read_connection(revision, selection)
            if self.stop.is_set():
                break
            with self.lock:
                if self.connection_revision == revision:
                    self.reset_connection()
            if self.current_connection(revision):
                self.wake.wait(self.retry_seconds)

    def read_connection(self, revision, selection):
        device = None
        try:
            candidates = self.enumerator()
            if selection:
                serial = selection.get('serial_number')
                candidates = [d for d in candidates if
                              (d.get('serial_number') == serial if serial else d.get('path') == selection.get('path'))]
            if not candidates:
                raise RuntimeError('Chưa thấy kính. Cắm kính vào PC; app sẽ tự nhận.')
            if not self.current_connection(revision):
                return
            device = self.device_factory()
            device.open_path(candidates[0]['path'])
            history = []
            timestamps = collections.deque(maxlen=450)
            last_timestamp = None
            fusion = None
            start = time.monotonic()
            gaps = 0
            with self.lock:
                if self.connection_revision != revision:
                    return
                self.reset_connection()
                self.error = None
                self.connected = True
                self.connection_session += 1
                self.status = CALIBRATION_MESSAGE
            while not self.stop.is_set() and self.current_connection(revision):
                packet = device.read(128, 100)
                if not self.current_connection(revision):
                    break
                parsed = decode(packet)
                if parsed is None:
                    if self.updated and time.monotonic()-self.updated > 1:
                        raise RuntimeError('Mất kết nối với kính. Kiểm tra dây; app sẽ tự nhận lại.')
                    if not self.updated and time.monotonic()-start > 3:
                        raise RuntimeError('Chưa nhận chuyển động từ kính. App đang thử kết nối lại…')
                    continue
                timestamp, acc, gyr = parsed
                now = time.monotonic()
                observed = {'brightness': packet[59], 'volume': packet[60]}
                with self.lock:
                    if self.connection_revision != revision:
                        return
                    # A reconnect or long gap establishes a fresh baseline.
                    if self.button_state is not None and now - self.updated < 0.5:
                        for kind, value in observed.items():
                            before = self.button_state[kind]
                            if value != before:
                                self.button_events.append((kind, before, value, now))
                    else:
                        self.button_events.clear()
                    self.button_state = observed
                if last_timestamp is not None:
                    dt = (timestamp-last_timestamp)*1e-9
                    if dt <= 0 or dt > 0.05:
                        gaps += 1
                        fusion = None
                        history = []
                        start = time.monotonic()
                        with self.lock:
                            self.ready = False
                            self.reference = None
                    elif fusion is None:
                        history.append(dt)
                    elif dt > 1.5 * period:
                        # Preserve elapsed sensor time across a small dropped-report gap.
                        for _ in range(min(20, max(0, round(dt/period)-1))):
                            fusion.update(gyr, acc)
                last_timestamp = timestamp
                timestamps.append(timestamp)
                if fusion is None and len(history) >= 100:
                    period = float(np.median(history))
                    fusion = VQF(period)
                if fusion is not None:
                    fusion.update(gyr, acc)
                    q = fusion.getQuat6D().copy()
                    with self.lock:
                        if self.connection_revision != revision:
                            return
                        self.q = q
                        if time.monotonic()-start >= self.settle_seconds:
                            if self.reference is None or self.center_requested.is_set():
                                self.reference = q.copy()
                                self.center_requested.clear()
                                self.center_generation += 1
                            self.pose = angles(self.reference, q)
                            self.ready = True
                            self.status = 'Đã nhận chuyển động'
                        else:
                            self.status = CALIBRATION_MESSAGE
                with self.lock:
                    if self.connection_revision != revision:
                        return
                    self.count += 1
                    self.updated = time.monotonic()
                    if len(timestamps) > 1 and timestamps[-1] > timestamps[0]:
                        self.rate = (len(timestamps)-1)*1e9/(timestamps[-1]-timestamps[0])
        except Exception as exc:
            with self.lock:
                if self.connection_revision == revision:
                    self.reset_connection()
                    self.error = str(exc)
                    self.status = str(exc)
        finally:
            if device is not None:
                try:
                    device.close()
                except Exception:
                    pass


def gui(resume_send=False, ui_check=False, ui_language=None):
    import tkinter as tk
    from tkinter import ttk
    import ctypes
    import tempfile
    from functools import partial
    from localization import Translator, TranslatedStringVar, LANGUAGES, default_language
    temporary_data = tempfile.TemporaryDirectory(prefix='kariuss-ui-') if ui_check else None
    data_root = Path(temporary_data.name) if temporary_data else DATA_ROOT
    preferences_path = data_root / 'preferences.json'
    try:
        preferences = json.loads(preferences_path.read_text(encoding='utf-8'))
        if not isinstance(preferences, dict):
            preferences = {}
    except (OSError, ValueError, AttributeError):
        preferences = {}
    wanted_language = (ui_language or 'vi') if ui_check else default_language(preferences)
    localizer = Translator()
    tr = localizer.tr
    StringVar = partial(TranslatedStringVar, localizer)
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Kariuss.MaxHeadtracking')
    reader = Reader()
    reader.thread.start()
    discovery = UsbDiscovery()
    discovery.thread.start()
    commands = queue.SimpleQueue()
    tray = None
    stopping = False
    root = tk.Tk()
    root.title(APP_NAME)
    icon = ROOT / 'assets' / 'kariuss.ico'
    if icon.exists():
        root.iconbitmap(str(icon))
    root.geometry('800x840')
    root.minsize(780, 820)
    if ui_check:
        root.withdraw()
    ui_errors = []
    if ui_check:
        def report_ui_error(kind, value, tb):
            import traceback
            traceback.print_exception(kind, value, tb)
            ui_errors.append(value)
        root.report_callback_exception = report_ui_error
    from app_theme import apply_dark_theme, MUTED, WARNING
    apply_dark_theme(root)
    frame = ttk.Frame(root, padding=22)
    frame.pack(fill='both', expand=True)
    header = ttk.Frame(frame)
    header.pack(fill='x')
    ttk.Label(header, text=tr(APP_NAME), font=('Segoe UI', 20, 'bold')).pack(side='left')
    language_choice = tk.StringVar(value=LANGUAGES['vi'])
    language_box = ttk.Combobox(header, textvariable=language_choice, values=list(LANGUAGES.values()),
                               state='readonly', width=11)
    language_box.pack(side='right', padx=(12, 0))
    connection_row = ttk.Frame(frame)
    connection_row.pack(fill='x', pady=(12,0))
    usb_choices = {}
    selected_usb_device = None
    usb_choice = StringVar(value='Đang tìm kính…')
    usb_combo = ttk.Combobox(connection_row, textvariable=usb_choice, values=[], state='readonly')
    usb_combo.pack(side='left', fill='x', expand=True, padx=(0, 8))
    def toggle_connection():
        enabled = not reader.snapshot()['connection_enabled']
        reader.request_connection(enabled, selected_usb_device)
        refresh_connection_button(reader.snapshot())
        console.append('Đang kết nối với kính' if enabled else 'Đã ngắt kết nối với kính')
        discovery.wake.set()
    connect_button = ttk.Button(connection_row, text=tr('Kết nối kính'), width=16, command=toggle_connection)
    connect_button.pack(side='left', padx=(0, 8))
    def refresh_connection_button(state):
        connection = ('off' if not state['connection_enabled'] else
                      'connected' if state['connected'] and not state['error'] else 'waiting')
        connect_button.configure(style={'off': 'TButton', 'connected': 'GameConnected.TButton',
                                        'waiting': 'GameWaiting.TButton'}[connection])
        return connection
    def refresh_usb():
        console.append('Đang tìm lại kết nối USB')
        discovery.wake.set()
        if reader.snapshot()['connection_enabled']:
            reader.request_connection(True, selected_usb_device)
    ttk.Button(connection_row, text=tr('Tìm lại USB'), command=refresh_usb).pack(side='left')
    def change_usb(event=None):
        nonlocal selected_usb_device
        selected_usb_device = usb_choices.get(usb_choice.get())
        if selected_usb_device is None:
            return
        console.append('Đã chọn thiết bị: ' + usb_choice.get())
        if reader.snapshot()['connection_enabled']:
            reader.request_connection(True, selected_usb_device)
    usb_combo.bind('<<ComboboxSelected>>', change_usb)
    usb_info = StringVar(value='Đang tìm kết nối USB của kính…')
    ttk.Label(frame, textvariable=usb_info, font=('Segoe UI', 10), foreground=MUTED).pack(anchor='w', pady=(4, 8))
    tabs = ttk.Notebook(frame)
    tabs.pack(fill='both', expand=True)
    tracking = ttk.Frame(tabs, padding=14)
    controls = ttk.Frame(tabs, padding=14)
    tabs.add(tracking, text=tr('Theo dõi chuyển động'))
    tabs.add(controls, text=tr('Nút trên kính'))
    status = StringVar(value='Đang tìm kính…')
    ttk.Label(tracking, textvariable=status, wraplength=600).pack(anchor='w', pady=(0, 10))
    from glasses_view import GlassesView
    visual_row = ttk.Frame(tracking)
    visual_row.pack(fill='x', pady=(0, 10))
    model = GlassesView(visual_row, tr)
    model.pack(side='left', padx=(12, 28), anchor='center')
    numbers = ttk.Frame(visual_row)
    numbers.pack(side='left', fill='both', expand=True)
    labels = []
    inverse = []
    saved_inverse = preferences.get('inverse', [True, False, False])
    if not isinstance(saved_inverse, list) or len(saved_inverse) != 3 or not all(type(v) is bool for v in saved_inverse):
        saved_inverse = [True, False, False]
    saved_mappings = preferences.get('button_mappings', {})
    if not isinstance(saved_mappings, dict):
        saved_mappings = {}
    mappings = {button: saved_mappings.get(button, 'center' if button == 'volume_pair' else 'native')
                for button in BUTTON_LABELS}
    mappings = {button: action if action in ACTION_LABELS else 'native' for button, action in mappings.items()}
    router = ButtonRouter(mappings)
    from motion_filter import MotionFilter, SMOOTHING_CHOICES, SMOOTHING_ALIASES, SENSITIVITY_CHOICES
    from game_output import GameOutput, process_names
    from game_presence import GamePresence
    from output_scheduler import TrackingOutput, RATE_CHOICES
    from mouse_output import MouseOutput, MOUSE_SENSITIVITY_CHOICES
    saved_smoothing = preferences.get('motion_smoothing', 'Mượt vừa')
    if isinstance(saved_smoothing, str):
        saved_smoothing = SMOOTHING_ALIASES.get(saved_smoothing, saved_smoothing)
    if not isinstance(saved_smoothing, str) or saved_smoothing not in SMOOTHING_CHOICES:
        saved_smoothing = 'Mượt vừa'
    saved_sensitivity = preferences.get('motion_sensitivity', '80%')
    if saved_sensitivity not in SENSITIVITY_CHOICES:
        saved_sensitivity = '80%'
    smoothing_choice = StringVar(value=saved_smoothing)
    sensitivity_choice = StringVar(value=saved_sensitivity)
    motion = MotionFilter(SMOOTHING_CHOICES[saved_smoothing], int(saved_sensitivity[:-1]) / 100)
    saved_mouse_smoothing = preferences.get('mouse_smoothing', 'Mượt vừa')
    if not isinstance(saved_mouse_smoothing, str) or saved_mouse_smoothing not in SMOOTHING_CHOICES:
        saved_mouse_smoothing = 'Mượt vừa'
    saved_mouse_sensitivity = preferences.get('mouse_sensitivity', '80%')
    if saved_mouse_sensitivity not in MOUSE_SENSITIVITY_CHOICES:
        saved_mouse_sensitivity = '80%'
    mouse_smoothing_choice = StringVar(value=saved_mouse_smoothing)
    mouse_sensitivity_choice = StringVar(value=saved_mouse_sensitivity)
    mouse_motion = MotionFilter(SMOOTHING_CHOICES[saved_mouse_smoothing], 1.)
    # Layout checks never synthesize real input or move the user's cursor.
    class CheckMouse:
        moves = []
        centers = 0
        def available(self):
            return True
        def move(self, dx, dy):
            self.moves.append((dx, dy))
        def center(self):
            self.centers += 1
            return (960, 540)
    mouse_output = MouseOutput(CheckMouse() if ui_check else None,
                               int(saved_mouse_sensitivity[:-1]) / 100)
    saved_rate = preferences.get('output_frequency', '100 Hz')
    if not isinstance(saved_rate, str) or saved_rate not in RATE_CHOICES:
        saved_rate = '100 Hz'
    rate_choice = StringVar(value=saved_rate)
    game_output = GameOutput(ROOT / 'game_clients', data_root)
    output = TrackingOutput(reader, game_output, motion, saved_inverse, RATE_CHOICES[saved_rate],
                            mouse=mouse_output, mouse_motion=mouse_motion)
    # Always open in Headtracking; never start mouse movement on app launch.
    output_mode = tk.StringVar(value='headtracking')
    previous_output_mode = preferences.get('output_mode', 'headtracking')
    if previous_output_mode == 'mouse':
        preferences['game_output_enabled'] = False
    game_presence = GamePresence()
    def save_preferences():
        preferences.update(inverse=[inv.get() for inv in inverse], button_mappings=dict(mappings),
                           motion_smoothing=smoothing_choice.get(), motion_sensitivity=sensitivity_choice.get(),
                           mouse_smoothing=mouse_smoothing_choice.get(), mouse_sensitivity=mouse_sensitivity_choice.get(),
                           output_mode=output_mode.get(),
                           output_frequency=rate_choice.get(), language=localizer.language)
        preferences_path.write_text(json.dumps(preferences, ensure_ascii=False, indent=2), encoding='utf-8')
    def change_inverse():
        output.configure(inverse=[inv.get() for inv in inverse])
        save_preferences()
        console.append('Đã lưu chiều chuyển động: ' + ', '.join(
            name + (' đảo chiều' if inv.get() else ' bình thường')
            for name,inv in zip(('trái/phải','ngẩng/cúi','nghiêng'),inverse)))
    for index, text in enumerate(('Quay trái / phải', 'Ngẩng / cúi', 'Nghiêng đầu')):
        row = ttk.Frame(numbers)
        row.pack(fill='x', pady=4)
        ttk.Label(row, text=tr(text), width=18).pack(anchor='w')
        value_row = ttk.Frame(row)
        value_row.pack(fill='x')
        variable = StringVar(value='0.0°')
        ttk.Label(value_row, textvariable=variable, font=('Segoe UI', 17, 'bold'), width=8).pack(side='left')
        inv = tk.BooleanVar(value=saved_inverse[index])
        ttk.Checkbutton(value_row, text=tr('Đảo chiều'), variable=inv, command=change_inverse).pack(side='right')
        labels.append(variable)
        inverse.append(inv)
    paused = False
    held_pose = [0.0, 0.0, 0.0]
    last_output_pose = [0.0, 0.0, 0.0]
    waiting_center = None
    action_count = 0
    last_action = StringVar(value='Chưa bấm nút điều khiển.')
    def request_center():
        nonlocal held_pose, last_output_pose, waiting_center, action_count
        state = reader.snapshot()
        if output_mode.get() != 'mouse' and (not state['ready'] or state['age_s'] is None or state['age_s'] >= 0.5):
            last_action.set('Kính chưa sẵn sàng. Chờ nhận chuyển động rồi thử lại.')
            return
        waiting_center = state['center_generation']
        held_pose = last_output_pose = [0.0, 0.0, 0.0]
        try:
            output.center(waiting_center)
        except Exception as exc:
            last_action.set('Không reset được chuột: ' + str(exc))
            return
        reader.center_requested.set()
        action_count += 1
        last_action.set('Đã đưa chuột về giữa màn hình' if output_mode.get() == 'mouse' else 'Đã reset góc nhìn')
    def toggle_pause():
        nonlocal paused, held_pose, action_count
        paused = not paused
        if paused:
            held_pose = output.pause(True)
            action_count += 1
            last_action.set('Đã tạm dừng điều khiển chuột' if output_mode.get() == 'mouse' else 'Đã tạm dừng theo dõi đầu trong game')
        else:
            if output_mode.get() != 'mouse':
                request_center()
            output.pause(False)
            last_action.set('Đã tiếp tục điều khiển chuột' if output_mode.get() == 'mouse' else 'Đã tiếp tục theo dõi đầu')
        refresh_mode_controls()
    action_row = ttk.Frame(tracking)
    action_row.pack(fill='x', pady=(8, 7))
    center = ttk.Button(action_row, text=tr('Reset góc nhìn'), command=request_center)
    center.pack(side='left', fill='x', expand=True, padx=(0, 8))
    pause_button = ttk.Button(action_row, text=tr('Tạm dừng theo dõi đầu'), command=toggle_pause)
    pause_button.pack(side='right', fill='x', expand=True)
    # Keep a user's choice across launches, but don't touch the Windows game
    # registration during a layout check.
    sending = tk.BooleanVar(value=False)
    output_error = ''
    observed_game_id = 0
    observed_game_connected = False
    mode_row = ttk.Frame(tracking)
    mode_row.pack(fill='x', pady=(3, 0))
    def select_mode(mode):
        nonlocal paused, waiting_center, output_error, observed_game_id, observed_game_connected
        if mode == output_mode.get():
            return
        try:
            output.set_mode(mode)
            output_error = ''
        except Exception as exc:
            sending.set(False)
            output_error = str(exc)
            console.append('Không bật được kết nối game: ' + output_error, 'warning')
        output_mode.set(output.mode)
        paused = False
        waiting_center = None
        observed_game_id = 0
        observed_game_connected = False
        game_presence.request(sending.get() and mode == 'headtracking', 0)
        refresh_mode_controls()
        if not ui_check:
            preferences['game_output_enabled'] = sending.get()
        save_preferences()
        console.append('Đã chọn chế độ: ' + ('Mouse Control (FPS)' if mode == 'mouse' else 'Headtracking (Simulator)'))
    head_mode_button = ttk.Button(mode_row, text='Headtracking (Simulator)', command=lambda: select_mode('headtracking'))
    head_mode_button.pack(side='left', fill='x', expand=True, padx=(0, 8))
    mouse_mode_button = ttk.Button(mode_row, text='Mouse Control (FPS)', command=lambda: select_mode('mouse'))
    mouse_mode_button.pack(side='left', fill='x', expand=True)
    def change_sending():
        nonlocal output_error, observed_game_id
        output_error = ''
        try:
            if sending.get():
                output.set_enabled(True)
                console.append('Đã bật điều khiển chuột. Chuyển sang game để sử dụng.' if output_mode.get() == 'mouse' else
                               'Đã bật kết nối game trực tiếp. Mở game để sử dụng.')
            else:
                output.set_enabled(False)
                observed_game_id = 0
                console.append('Đã tắt kết nối với game')
        except Exception as exc:
            sending.set(False)
            output_error = str(exc)
            console.append('Không bật được kết nối game: ' + output_error, 'warning')
        if not ui_check:
            preferences['game_output_enabled'] = sending.get()
            save_preferences()
        game_presence.request(sending.get() and output_mode.get() == 'headtracking', 0)
        game_button.configure(style='GameWaiting.TButton' if sending.get() or output_error else 'TButton')
    def toggle_game():
        sending.set(not sending.get())
        change_sending()
    game_button = ttk.Button(tracking, text=tr('Kết nối game'), width=18, command=toggle_game)
    game_button.pack(anchor='w', pady=8)
    game_info = StringVar(value='Chưa bật kết nối với game.')
    ttk.Label(tracking, textvariable=game_info, foreground=MUTED, wraplength=600).pack(anchor='w')
    info = StringVar()
    rate_row = ttk.Frame(tracking)
    rate_row.pack(fill='x', pady=(5, 0))
    ttk.Label(rate_row, text=tr('Tần số gửi:')).pack(side='left', padx=(0, 7))
    rate_box = ttk.Combobox(rate_row, values=list(RATE_CHOICES), textvariable=rate_choice,
                           state='readonly', width=12)
    rate_box.pack(side='left')
    ttk.Label(rate_row, textvariable=info, font=('Segoe UI',10), foreground=MUTED).pack(side='left', padx=(15,0))
    def change_rate(event=None):
        output.configure(frequency=RATE_CHOICES[rate_choice.get()])
        save_preferences()
        console.append('Đã chọn tần số gửi: ' + rate_choice.get())
    rate_box.bind('<<ComboboxSelected>>', change_rate)
    feel_row = ttk.Frame(tracking)
    feel_row.pack(fill='x', pady=(7, 0))
    feel_smoothing_label = ttk.Label(feel_row, text=tr('Độ mượt:'))
    feel_smoothing_label.pack(side='left', padx=(0, 7))
    smooth_box = ttk.Combobox(feel_row, values=list(SMOOTHING_CHOICES),
                             textvariable=smoothing_choice, state='readonly', width=15)
    smooth_box.pack(side='left')
    feel_sensitivity_label = ttk.Label(feel_row, text=tr('Độ nhạy:'))
    feel_sensitivity_label.pack(side='left', padx=(14, 7))
    sensitive_box = ttk.Combobox(feel_row, values=list(SENSITIVITY_CHOICES),
                                textvariable=sensitivity_choice, state='readonly', width=8)
    sensitive_box.pack(side='left')
    def refresh_mode_controls():
        is_mouse = output_mode.get() == 'mouse'
        head_mode_button.configure(style='TButton' if is_mouse else 'GameConnected.TButton')
        mouse_mode_button.configure(style='GameConnected.TButton' if is_mouse else 'TButton')
        feel_smoothing_label.configure(text=tr('Độ mượt chuột:' if is_mouse else 'Độ mượt:'))
        feel_sensitivity_label.configure(text=tr('Độ nhạy chuột:' if is_mouse else 'Độ nhạy:'))
        smooth_box.configure(textvariable=mouse_smoothing_choice if is_mouse else smoothing_choice)
        sensitive_box.configure(textvariable=mouse_sensitivity_choice if is_mouse else sensitivity_choice,
                                 values=MOUSE_SENSITIVITY_CHOICES if is_mouse else SENSITIVITY_CHOICES)
        center.configure(text=tr('Reset chuột' if is_mouse else 'Reset góc nhìn'))
        state = reader.snapshot()
        ready = state['ready'] and state['age_s'] is not None and state['age_s'] < .5
        center.configure(state='normal' if is_mouse or ready else 'disabled')
        pause_button.configure(text=tr(('Tiếp tục điều khiển chuột' if paused else 'Tạm dừng điều khiển chuột')
                                      if is_mouse else ('Tiếp tục theo dõi đầu' if paused else 'Tạm dừng theo dõi đầu')))
    def change_feel(event=None):
        if output_mode.get() == 'mouse':
            output.configure(mouse_smoothing=SMOOTHING_CHOICES[mouse_smoothing_choice.get()],
                             mouse_sensitivity=int(mouse_sensitivity_choice.get()[:-1]) / 100)
            message = 'Đã chỉnh độ mượt chuột: ' + mouse_smoothing_choice.get() + '; độ nhạy: ' + mouse_sensitivity_choice.get()
        else:
            output.configure(smoothing=SMOOTHING_CHOICES[smoothing_choice.get()],
                             sensitivity=int(sensitivity_choice.get()[:-1]) / 100)
            message = 'Đã chỉnh độ mượt: ' + smoothing_choice.get() + '; độ nhạy: ' + sensitivity_choice.get()
        save_preferences()
        console.append(message)
    smooth_box.bind('<<ComboboxSelected>>', change_feel)
    sensitive_box.bind('<<ComboboxSelected>>', change_feel)
    ttk.Label(controls, text=tr('Chọn thêm việc app làm khi bạn bấm nút.'), wraplength=600).pack(anchor='w', pady=(0, 10))
    action_boxes = {}
    for button in ('volume_up', 'volume_down', 'brightness'):
        row = ttk.Frame(controls)
        row.pack(fill='x', pady=5)
        ttk.Label(row, text=tr(BUTTON_LABELS[button]), width=20).pack(side='left')
        combo = ttk.Combobox(row, values=list(ACTION_LABELS.values()), state='readonly', width=36)
        combo.set(ACTION_LABELS[mappings[button]])
        action_boxes[button] = combo
        combo.pack(side='right', fill='x', expand=True)
        def changed(event, key=button, box=combo):
            mappings[key] = next(k for k, v in ACTION_LABELS.items() if tr(v) == box.get())
            router.reset()
            save_preferences()
            console.append('Đã gán ' + BUTTON_LABELS[key].lower() + ': ' + ACTION_LABELS[mappings[key]])
        combo.bind('<<ComboboxSelected>>', changed)
    ttk.Separator(controls).pack(fill='x', pady=12)
    ttk.Label(controls, text=tr('Hai lần bấm âm lượng ngược nhau trong 0,8 giây:'), wraplength=600).pack(anchor='w')
    pair_combo = ttk.Combobox(controls, values=list(ACTION_LABELS.values()), state='readonly')
    pair_combo.set(ACTION_LABELS[mappings['volume_pair']])
    pair_combo.pack(fill='x', pady=7)
    def change_pair(event):
        mappings['volume_pair'] = next(k for k, v in ACTION_LABELS.items() if tr(v) == pair_combo.get())
        router.reset()
        save_preferences()
        console.append('Đã gán bấm đôi âm lượng: ' + ACTION_LABELS[mappings['volume_pair']])
    pair_combo.bind('<<ComboboxSelected>>', change_pair)
    ttk.Label(controls, text=tr('Để giữ độ sáng: dùng hai lần bấm âm lượng ở trên, hoặc F8. '
              'Âm lượng đổi tạm rồi trở lại mức ban đầu.'), wraplength=600).pack(anchor='w', pady=(4, 8))
    ttk.Label(controls, text=tr('App chưa chặn được chức năng gốc: nút độ sáng vẫn đổi độ sáng; '
              'nút âm lượng vẫn đổi âm lượng. Ở mức âm lượng cao nhất, bấm giảm rồi tăng; '
              'ở mức thấp nhất, bấm tăng rồi giảm.'), foreground=WARNING, wraplength=600).pack(anchor='w', pady=4)
    button_info = StringVar(value='Đang chờ kính…')
    ttk.Label(controls, textvariable=button_info, foreground=MUTED, wraplength=600).pack(anchor='w', pady=8)
    from event_console import EventConsole, ConnectionEvents
    console = EventConsole(frame, lambda: close(), None if ui_check else data_root / 'activity.log', tr)
    console.pack(fill='x', pady=(10,0))
    connection_events = ConnectionEvents()
    last_action.trace_add('write', lambda *_: None if localizer.refreshing else console.append(last_action.get()))
    # Capture static labels once; dynamic status strings keep their original values.
    static_text = []
    def collect_text(parent):
        for widget in parent.winfo_children():
            if 'text' in widget.keys() and not ('textvariable' in widget.keys() and widget.cget('textvariable')):
                original = str(widget.cget('text'))
                if original:
                    static_text.append((widget, original))
            collect_text(widget)
    collect_text(frame)
    def apply_language(language, log=True):
        localizer.set_language(language)
        language_choice.set(LANGUAGES[language])
        for widget, original in static_text:
            widget.configure(text=tr(original))
        tabs.tab(tracking, text=tr('Theo dõi chuyển động'))
        tabs.tab(controls, text=tr('Nút trên kính'))
        smooth_box.configure(values=[tr(name) for name in SMOOTHING_CHOICES])
        for key, box in action_boxes.items():
            box.configure(values=[tr(name) for name in ACTION_LABELS.values()])
            box.set(tr(ACTION_LABELS[mappings[key]]))
        pair_combo.configure(values=[tr(name) for name in ACTION_LABELS.values()])
        pair_combo.set(tr(ACTION_LABELS[mappings['volume_pair']]))
        connect_button.configure(text=tr('Kết nối kính'))
        refresh_connection_button(reader.snapshot())
        refresh_mode_controls()
        console.refresh_language()
        model.draw()
        if tray is not None:
            tray.refresh_language()
            tray.title(APP_NAME + (' — đang chạy' if reader.snapshot()['ready'] else ' — chưa kết nối'))
        save_preferences()
        if log:
            console.append('Đã đổi ngôn ngữ: ' + LANGUAGES[language])
    language_box.bind('<<ComboboxSelected>>', lambda event: apply_language(
        next(code for code, label in LANGUAGES.items() if label == language_choice.get())))
    apply_language(wanted_language, log=False)
    console.append('Đã mở Kariuss Max Headtracking')
    save_preferences()
    if not ui_check and previous_output_mode != 'mouse' and (resume_send or preferences.get('game_output_enabled') is True):
        sending.set(True)
        change_sending()
    if not ui_check:
        game_presence.thread.start()
        output.thread.start()
    key_was_down = False
    last_saved = 0.0
    last_scan = 0.0
    last_command_check = 0.0
    previous_session = 0
    last_model_draw = 0.0
    def show_window():
        root.deiconify()
        root.lift()
        root.focus_force()
        console.append('Đã mở lại cửa sổ')
    def hide_window():
        if tray is not None and tray.ready.is_set():
            console.append('Đã chuyển app sang chạy ngầm')
            root.withdraw()
        else:
            root.iconify()
            last_action.set('Biểu tượng cạnh đồng hồ chưa sẵn sàng; app được thu xuống thanh tác vụ.')
    def tick():
        nonlocal key_was_down, last_saved, last_output_pose, waiting_center, last_scan, last_command_check
        nonlocal previous_session, paused, held_pose
        nonlocal last_model_draw, observed_game_id, observed_game_connected, output_error
        if stopping:
            return
        now = time.monotonic()
        if now - last_command_check > 0.25:
            request_file = CONTROL_ROOT / 'window_request.txt'
            try:
                request = request_file.read_text(encoding='utf-8').strip()
                request_file.unlink(missing_ok=True)
                if request in ('show', 'quit'):
                    commands.put(request)
            except OSError:
                pass
            last_command_check = now
        while not commands.empty():
            command = commands.get()
            if command == 'quit':
                close()
                return
            if command == 'show':
                show_window()
            elif command == 'center':
                request_center()
            elif command == 'pause' and reader.snapshot()['ready']:
                toggle_pause()
            elif command == 'connection':
                toggle_connection()
        state = reader.snapshot()
        for message,tone in connection_events.observe(state):
            console.append(message,tone)
        if state['connection_session'] != previous_session:
            previous_session = state['connection_session']
            router.reset()
            waiting_center = None
            paused = False
            held_pose = last_output_pose = [0.0, 0.0, 0.0]
            refresh_mode_controls()
        active = state['ready'] and state['age_s'] is not None and state['age_s'] < 0.5
        glasses_connection = refresh_connection_button(state)
        if now - last_scan > 1:
            if not ui_check and sending.get() and output_mode.get() == 'headtracking' and 'opentrack.exe' in process_names():
                sending.set(False)
                change_sending()
                output_error = 'OpenTrack đang mở. Tắt OpenTrack rồi bật lại Kết nối với game.'
                console.append(output_error, 'warning')
            devices = discovery.snapshot()
            usb_choices.clear()
            for index, device in enumerate(devices):
                name = device.get('product_string') or 'Rokid Max'
                usb_choices[name + ' · USB ' + str(index + 1)] = device
            usb_combo.configure(values=list(usb_choices))
            if devices:
                selected_label = next((label for label, device in usb_choices.items()
                                       if selected_usb_device is not None and
                                       (device.get('serial_number') == selected_usb_device['serial_number']
                                        if selected_usb_device.get('serial_number') else
                                        device.get('path') == selected_usb_device.get('path'))), None)
                usb_choice.set(selected_label or (next(iter(usb_choices)) if selected_usb_device is None else
                                                 'Thiết bị đã chọn chưa kết nối'))
                usb_info.set(f'Tìm thấy {len(devices)} kính qua USB.')
            else:
                usb_choice.set('Chưa phát hiện kính')
                usb_info.set('Chưa thấy kính qua USB. Cắm dây hoặc bấm Tìm lại USB.')
            last_scan = now
        events = reader.take_buttons()
        actions = []
        if active:
            for event in events:
                if now - event[3] < 0.4:
                    actions += router.feed(event)
                else:
                    router.reset()
            actions += router.flush(now)
        else:
            router.reset()
        for button, action in actions:
            if action == 'center':
                request_center()
            elif action == 'pause':
                toggle_pause()
        if waiting_center is not None and state['center_generation'] > waiting_center:
            waiting_center = None
        pose = [a * (-1 if inv.get() else 1) for a, inv in zip(state['angles_deg'], inverse)]
        for label, value in zip(labels, pose):
            label.set(f'{value:+.1f}°')
        status.set(state['status'])
        center.configure(state='normal' if active or output_mode.get() == 'mouse' else 'disabled')
        pause_button.configure(state='normal' if active else 'disabled')
        key_down = bool(ctypes.windll.user32.GetAsyncKeyState(0x77) & 0x8000)
        if key_down and not key_was_down and (active or output_mode.get() == 'mouse'):
            request_center()
        key_was_down = key_down
        if ui_check:
            output.enabled = sending.get()
            output.step(state, now, force=True)
        dispatch = output.snapshot()
        transmitting = bool(sending.get() and dispatch['sending_to_game'])
        output_pose = dispatch['output_angles_deg']
        # The model observes the glasses, including while game output is paused.
        if now-last_model_draw >= 0.04 and root.state() != 'withdrawn' and tabs.select() == str(tracking):
            if active:
                message = 'Đang theo dõi · tạm dừng gửi' if paused else 'Đang theo dõi đầu'
            elif state['connected']:
                message = 'Đang hiệu chỉnh kính…'
            elif state['connection_enabled']:
                message = 'Đang tìm kính…'
            else:
                message = 'Đã ngắt kết nối'
            display_pose = [0.,0.,0.] if waiting_center is not None else pose
            model.update_pose(display_pose, active, message, paused)
            last_model_draw = now
        if sending.get() and dispatch['error']:
            sending.set(False)
            change_sending()
            output_error = dispatch['error']
            console.append('Kết nối game bị gián đoạn: ' + output_error, 'warning')
            transmitting = False
        game_state = dispatch['game_output']
        is_mouse = output_mode.get() == 'mouse'
        game_presence.request(sending.get() and not is_mouse and game_state['enabled'], game_state['registered_game_id'])
        game_connection = game_presence.snapshot()
        game_connected = (sending.get() and active and dispatch['mouse_output'].get('available', False)) if is_mouse else game_connection['connected']
        game_button.configure(style='GameConnected.TButton' if game_connected else
                              'GameWaiting.TButton' if sending.get() or output_error else 'TButton')
        if game_state['registered_game_id'] != observed_game_id:
            observed_game_id = game_state['registered_game_id']
        if game_connected != observed_game_connected:
            if game_connected:
                console.append('Đang điều khiển chuột' if is_mouse else 'Game đã nhận kết nối Kariuss: ' + game_state['registered_game_name'])
            elif sending.get():
                console.append('Đang chờ điều khiển chuột' if is_mouse else 'Game đã ngắt kết nối Kariuss')
            observed_game_connected = game_connected
        if output_error:
            game_info.set(output_error)
        elif sending.get():
            if is_mouse:
                game_info.set('Đang điều khiển chuột' if game_connected else
                              'Điều khiển chuột đã bật. Chuyển sang game; chuột tạm dừng khi cửa sổ Kariuss ở phía trước.')
            else:
                game_info.set('Game đã nhận kết nối: ' + game_state['registered_game_name']
                              if game_connected else 'Chưa có game kết nối. Mở game và vào buồng lái.')
        else:
            game_info.set('Chưa bật kết nối với game.')
        if transmitting:
            last_output_pose = list(output_pose)
        elif not paused:
            last_output_pose = list(output_pose)
        info.set(('Đang tạm dừng điều khiển chuột' if paused else 'Đang điều khiển chuột') if is_mouse and game_connected else
                 'Đang tạm dừng theo dõi đầu.' if transmitting and paused else
                 'Đang gửi hướng nhìn.' if transmitting and not is_mouse else 'Chưa gửi hướng nhìn.')
        button_info.set('Đã nhận nút kính. Các lựa chọn được lưu tự động.' if active and state['buttons'] else
                        'Chờ kính sẵn sàng rồi bấm nút để thử.')
        if now-last_saved >= 1:
            state['sending_to_game'] = transmitting
            state['game_output'] = game_state
            state['game_output_error'] = output_error
            state['game_connected'] = game_connected
            state['game_client_processes'] = game_connection['clients']
            state['game_button_state'] = 'connected' if game_connected else 'waiting' if sending.get() or output_error else 'off'
            state['glasses_button_state'] = glasses_connection
            state['inverse'] = [inv.get() for inv in inverse]
            state['button_mappings'] = dict(mappings)
            state['paused'] = paused
            state['output_angles_deg'] = output_pose
            state['output_mode'] = output_mode.get()
            state['mouse_output'] = dispatch['mouse_output']
            state['mouse_smoothing'] = mouse_smoothing_choice.get()
            state['mouse_sensitivity'] = mouse_sensitivity_choice.get()
            state['motion_smoothing'] = smoothing_choice.get()
            state['motion_sensitivity'] = sensitivity_choice.get()
            state['motion_filter'] = 'Accela rotation (adapted)'
            state['output_frequency'] = rate_choice.get()
            state['output_target_hz'] = dispatch['target_hz']
            state['output_measured_hz'] = dispatch['measured_hz']
            state['last_action'] = last_action.get()
            state['action_count'] = action_count
            state['app_version'] = APP_VERSION
            state['language'] = localizer.language
            state['standalone_app'] = FROZEN
            state['window_hidden'] = root.state() == 'withdrawn'
            state['tray_ready'] = tray is not None and tray.ready.is_set()
            state['usb_devices_found'] = len(discovery.snapshot())
            state['selected_usb'] = usb_choice.get()
            state['model_angles_deg'] = list(model.pose)
            state['log_event_count'] = console.count
            state['last_log_event'] = console.latest
            (data_root/'last_status.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
            if tray is not None:
                tray.title(APP_NAME + (' — đang chạy' if active else ' — chưa kết nối'))
            last_saved = now
        root.after(10, tick)
    def close():
        nonlocal stopping
        if stopping:
            return
        stopping = True
        console.append('Đã thoát Kariuss Max Headtracking')
        reader.stop.set()
        reader.wake.set()
        discovery.stop.set()
        discovery.wake.set()
        reader.thread.join(timeout=1)
        discovery.thread.join(timeout=1)
        game_presence.close()
        if tray is not None:
            tray.stop()
        try:
            output.close()
        except Exception as exc:
            print('Game output cleanup:', exc, file=sys.stderr)
        root.destroy()
    if not ui_check:
        try:
            from tray_icon import TrayIcon
            tray = TrayIcon(commands, icon, APP_NAME, tr)
            tray.start()
        except Exception as exc:
            print('Tray startup:', exc, file=sys.stderr)
    root.protocol('WM_DELETE_WINDOW', hide_window)
    tick()
    if ui_check:
        def check_layout():
            nonlocal game_output, tray, last_scan
            try:
                for page in (tracking, controls):
                    tabs.select(page)
                    root.update_idletasks()
                    def check_children(parent):
                        for widget in parent.winfo_children():
                            assert widget.winfo_y() + widget.winfo_height() <= parent.winfo_height(), (
                                widget.winfo_class(), widget.winfo_y(), widget.winfo_height(), parent.winfo_height())
                            assert widget.winfo_x() + widget.winfo_width() <= parent.winfo_width(), (
                                widget.winfo_class(), widget.winfo_x(), widget.winfo_width(), parent.winfo_width())
                            if widget is not tabs:
                                check_children(widget)
                    check_children(page)
                check_children(connection_row)
                check_children(console)
                check_children(frame)
                motion.smoothing = 0.
                motion.sensitivity = 1.
                reader.stop.set()
                reader.thread.join(timeout=1)
                # Auto-detection is enabled initially, but no open USB connection
                # must show red. Green includes the six-second calibration period.
                reader.request_connection(True)
                tick()
                assert connect_button.cget('text') == tr('Kết nối kính')
                assert connect_button.cget('style') == 'GameWaiting.TButton'
                with reader.lock:
                    reader.connected = True
                    reader.ready = False
                    reader.error = None
                    reader.status = CALIBRATION_MESSAGE
                tick()
                assert connect_button.cget('style') == 'GameConnected.TButton'
                assert status.get() == CALIBRATION_MESSAGE
                with reader.lock:
                    reader.reset_connection()  # A removed cable must immediately lose green.
                tick()
                assert connect_button.cget('style') == 'GameWaiting.TButton'
                connect_button.invoke()
                assert not reader.snapshot()['connection_enabled']
                assert connect_button.cget('style') == 'TButton'
                connect_button.invoke()
                assert reader.snapshot()['connection_enabled']
                assert connect_button.cget('style') == 'GameWaiting.TButton'
                game_output.stop()
                class CaptureGameOutput:
                    enabled = True
                    packets = []
                    game_id = 0
                    def update(self, pose, active=True):
                        if active:
                            self.packets.append(tuple(pose))
                    def start(self):
                        self.enabled = True
                    def stop(self):
                        self.enabled = False
                    def snapshot(self):
                        return {'registered_game_id': self.game_id, 'registered_game_name': 'MS Flight Simulator 2024' if self.game_id else '',
                                'enabled': self.enabled}
                game_output = CaptureGameOutput()
                output.backend = game_output
                game_presence.scan = lambda: [{'pid': 123, 'name': 'FlightSimulator2024.exe'}]
                # Actual button toggles output. Green also requires a living
                # client, so exiting a game cannot leave a stale green button.
                assert game_button.cget('text') == tr('Kết nối game')
                game_button.invoke()
                tick()
                assert sending.get() and game_button.cget('style') == 'GameWaiting.TButton'
                game_output.game_id = 8151
                tick()
                game_presence.poll()
                tick()
                assert game_button.cget('style') == 'GameConnected.TButton'
                game_presence.scan = lambda: []
                game_presence.poll()
                tick()
                assert game_button.cget('style') == 'GameWaiting.TButton'
                game_button.invoke()
                tick()
                assert not sending.get() and game_button.cget('style') == 'TButton'
                assert usb_combo.winfo_class() == 'TCombobox'
                assert not any('Nhìn từ sau kính' in model.itemcget(i, 'text')
                               for i in model.find_all() if model.type(i) == 'text')
                discovery.stop.set()
                discovery.wake.set()
                discovery.thread.join(timeout=1)
                with discovery.lock:
                    discovery.devices = [
                        {'product_string': 'Rokid Max', 'serial_number': 'private-id-1', 'path': b'usb-one'},
                        {'product_string': 'Rokid Max', 'serial_number': 'private-id-2', 'path': b'usb-two'}]
                last_scan = 0
                tick()
                assert len(usb_combo.cget('values')) == 2
                assert all('private-id' not in label for label in usb_combo.cget('values'))
                assert 'private-id' not in usb_choice.get() + usb_info.get()
                usb_combo.current(1)
                change_usb()
                assert reader.selection['path'] == b'usb-two'
                assert 'private-id' not in console.latest
                assert smooth_box.cget('values') == tuple(tr(name) for name in SMOOTHING_CHOICES)
                assert SMOOTHING_CHOICES['Mượt vừa'] == 1.5
                # Changing display language must not change tracking or saved identifiers.
                original_language = localizer.language
                before_settings = ([inv.get() for inv in inverse], dict(mappings),
                                   motion.smoothing, motion.sensitivity, rate_choice.get(),
                                   sending.get(), paused, reader.selection['path'])
                original_count = console.count
                original_log = console.history[-1][0]
                apply_language('en', log=False)
                assert connect_button.cget('text') == 'Connect glasses'
                assert connect_button.cget('style') == 'GameWaiting.TButton'
                assert game_button.cget('text') == 'Connect to game'
                assert center.cget('text') == 'Reset view'
                assert smooth_box.cget('values') == ('Off', 'Light', 'Medium', 'Strong')
                assert pair_combo.get() == 'Reset view'
                assert tabs.tab(controls, 'text') == 'Glasses buttons'
                assert console.count == original_count and console.history[-1][0] == original_log
                assert 'Selected device:' in console.latest
                smooth_box.current(2)
                change_feel()
                assert smoothing_choice.get() == 'Mượt vừa' and motion.smoothing == 1.5
                action_boxes['brightness'].set('Pause / resume head tracking')
                action_boxes['brightness'].event_generate('<<ComboboxSelected>>')
                assert mappings['brightness'] == 'pause'
                action_boxes['brightness'].set('Keep original function')
                action_boxes['brightness'].event_generate('<<ComboboxSelected>>')
                apply_language('vi', log=False)
                assert connect_button.cget('text') == 'Kết nối kính'
                assert game_button.cget('text') == 'Kết nối game'
                assert pair_combo.get() == 'Nhìn về giữa'
                assert smoothing_choice.get() == 'Mượt vừa'
                # Restore the original filter configuration used by behavioral checks below.
                motion.smoothing, motion.sensitivity = before_settings[2:4]
                assert ([inv.get() for inv in inverse], dict(mappings), motion.smoothing,
                        motion.sensitivity, rate_choice.get(), sending.get(), paused,
                        reader.selection['path']) == before_settings
                apply_language(original_language, log=False)
                saved = json.loads(preferences_path.read_text(encoding='utf-8'))
                assert saved['language'] == original_language
                assert saved['motion_smoothing'] == 'Mượt vừa'
                with reader.lock:
                    reader.ready = True
                    reader.updated = time.monotonic()
                    reader.pose = (12.0, -3.0, 2.0)
                sending.set(True)
                tick()
                original = game_output.packets[-1]
                pause_button.invoke()
                assert console.latest.endswith(tr('Đã tạm dừng theo dõi đầu trong game'))
                with reader.lock:
                    reader.pose = (80.0, 40.0, 20.0)
                tick()
                assert game_output.packets[-1] == original  # Turning the head while paused stays frozen.
                center.invoke()
                assert console.latest.endswith(tr('Đã reset góc nhìn'))
                tick()
                assert game_output.packets[-1] == (0.0,) * 3
                pause_button.invoke()
                assert console.latest.endswith(tr('Đã tiếp tục theo dõi đầu'))
                assert not paused and reader.center_requested.is_set()
                with reader.lock:
                    reader.center_generation += 1
                    reader.pose = (0.0, 0.0, 0.0)
                tick()
                with reader.lock:
                    reader.pose = (15.0, 0.0, 0.0)
                tick()
                assert abs(game_output.packets[-1][0]) == 15.0
                # The real filter feeds the game, while the model/labels keep
                # the physical pose. Pause holds the filtered pose, and reset
                # bypasses its history immediately.
                motion.smoothing = 1.5
                motion.sensitivity = .8
                motion.reset((0.,0.,0.))
                motion.last_time = time.monotonic() - .02
                with reader.lock:
                    reader.pose = (30.,0.,0.)
                tick()
                smooth_output = game_output.packets[-1]
                assert 0 < abs(smooth_output[0]) < 24.
                assert abs(float(labels[0].get().rstrip('°'))) == 30.
                pause_button.invoke()
                with reader.lock:
                    reader.pose = (60.,0.,0.)
                tick()
                assert game_output.packets[-1] == smooth_output
                center.invoke()
                tick()
                assert game_output.packets[-1] == (0.,0.,0.)
                pause_button.invoke()
                with reader.lock:
                    reader.center_generation += 1
                    reader.pose = (0.,0.,0.)
                tick()
                assert game_output.packets[-1] == (0.,0.,0.)
                motion.smoothing = 0.
                motion.sensitivity = 1.
                sending.set(False)
                count = len(game_output.packets)
                tick()
                assert len(game_output.packets) == count
                class TestTray:
                    ready = threading.Event()
                    def stop(self):
                        pass
                    def title(self, text):
                        pass
                    def refresh_language(self):
                        pass
                tray = TestTray()
                tray.ready.set()
                hide_window()
                assert root.state() == 'withdrawn'
                sending.set(True)
                count = len(game_output.packets)
                tick()
                assert len(game_output.packets) > count  # Hidden window keeps sending.
                commands.put('show')
                tick()
                assert root.state() == 'normal'
                root.withdraw()
                connect_button.invoke()
                assert not reader.snapshot()['connection_enabled']
                assert connect_button.cget('style') == 'TButton'
                count = len(game_output.packets)
                tick()
                assert len(game_output.packets) == count
                connect_button.invoke()
                assert reader.snapshot()['connection_enabled']
                assert connect_button.cget('style') == 'GameWaiting.TButton'
                # The mode buttons act as a rocker: either button selects it
                # immediately, without a separate deselection step.
                if sending.get():
                    game_button.invoke()
                assert output_mode.get() == 'headtracking'
                assert head_mode_button.cget('style') == 'GameConnected.TButton'
                mouse_mode_button.invoke()
                assert output_mode.get() == 'mouse' and output.mode == 'mouse'
                assert mouse_mode_button.cget('style') == 'GameConnected.TButton'
                assert head_mode_button.cget('style') == 'TButton'
                assert not head_mode_button.instate(['disabled'])
                head_mode_button.invoke()
                assert output_mode.get() == 'headtracking'
                mouse_mode_button.invoke()
                old_head_feel = motion.smoothing, motion.sensitivity
                smooth_box.current(1)
                sensitive_box.set('120%')
                change_feel()
                assert mouse_motion.smoothing == .75 and mouse_output.sensitivity == 1.2
                assert (motion.smoothing, motion.sensitivity) == old_head_feel
                assert center.cget('text') == tr('Reset chuột')
                resets = mouse_output.sink.centers
                center.invoke()  # Mouse reset also works without connected glasses.
                assert mouse_output.sink.centers == resets + 1
                assert console.latest.endswith(tr('Đã đưa chuột về giữa màn hình'))
                apply_language('en', log=False)
                assert center.cget('text') == 'Reset mouse'
                assert feel_smoothing_label.cget('text') == 'Mouse smoothing:'
                assert smooth_box.get() == 'Light'
                assert sensitive_box.get() == '120%'
                game_button.invoke()
                assert sending.get() and mouse_output.enabled and not game_output.enabled
                head_mode_button.invoke()  # A live connection follows the selected mode.
                assert sending.get() and game_output.enabled and not mouse_output.enabled
                assert output_mode.get() == 'headtracking'
                assert smoothing_choice.get() == 'Mượt vừa'
                mouse_mode_button.invoke()
                assert mouse_smoothing_choice.get() == 'Mượt nhẹ'
                assert mouse_sensitivity_choice.get() == '120%'
                game_button.invoke()
                assert not mouse_output.enabled and not game_output.enabled
                head_mode_button.invoke()
                apply_language(original_language, log=False)
                print('UI fits; bilingual controls, glasses/game states, reset, pause, background, exclusive rocker modes and independent mouse settings passed.')
            finally:
                close()
        root.after(100, check_layout)
    root.mainloop()
    if temporary_data:
        temporary_data.cleanup()
    if ui_errors:
        raise RuntimeError('UI check failed: ' + str(ui_errors[0]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--probe', type=float, default=0)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--ui-check', action='store_true')
    parser.add_argument('--ui-language', choices=('vi', 'en'), help='Language for isolated UI checks')
    parser.add_argument('--resume-send', action='store_true', help='Restore active sending after an app update')
    parser.add_argument('--quit', action='store_true', help='Exit the running app, including its tray icon')
    args = parser.parse_args()
    if args.quit:
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenMutexW.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
        kernel.OpenMutexW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
        mutex = kernel.OpenMutexW(0x100000, False, 'Local\\KariussMaxHeadtracking')
        if mutex:
            (CONTROL_ROOT / 'window_request.txt').write_text('quit', encoding='utf-8')
            kernel.CloseHandle(mutex)
        return
    if args.self_check:
        identity = np.array([1., 0, 0, 0])
        for axis, output in ((1, 1), (2, 0), (3, 2)):
            q = np.zeros(4); q[0] = math.cos(math.radians(15)); q[axis] = math.sin(math.radians(15))
            result = angles(identity, q)
            assert abs(result[output]-30) < 1e-8, result
            assert max(abs(v) for i, v in enumerate(result) if i != output) < 1e-8
            assert max(abs(v) for v in angles(q, q)) < 1e-8
        assert decode([0]*64) is None
        assert decode([17]*63) is None
        settings = {'brightness': 'center', 'volume_up': 'pause', 'volume_down': 'pause',
                    'volume_pair': 'center'}
        router = ButtonRouter(settings)
        assert router.feed(('volume', 20, 30, 1.0)) == []
        assert router.feed(('volume', 30, 20, 1.4)) == [('volume_pair', 'center')]
        assert router.flush(2.5) == []  # No delayed single after a pair.
        assert router.feed(('volume', 20, 10, 3.0)) == []
        assert router.feed(('volume', 10, 20, 3.5)) == [('volume_pair', 'center')]
        assert router.feed(('volume', 20, 30, 4.0)) == []
        assert router.flush(4.7) == []
        assert router.flush(4.9) == [('volume_up', 'pause')]
        assert router.flush(5.0) == []  # Single fires only once.
        assert router.feed(('volume', 30, 20, 5.1)) == []
        assert router.feed(('volume', 20, 10, 5.3)) == [('volume_down', 'pause')]
        assert router.flush(6.2) == [('volume_down', 'pause')]  # Same direction isn't a pair.
        assert router.feed(('brightness', 80, 60, 7.0)) == [('brightness', 'center')]
        assert router.feed(('brightness', 60, 60, 7.1)) == []
        router.feed(('volume', 10, 20, 8.0))
        router.reset()
        assert router.flush(10.0) == []  # Disconnect/preferences change cancels pending action.
        settings['volume_pair'] = 'native'
        assert router.feed(('volume', 20, 30, 11.0)) == [('volume_up', 'pause')]
        settings['volume_up'] = 'native'
        assert router.feed(('volume', 30, 40, 12.0)) == []
        print('Axes, centering, volume gestures, timing, single actions, and cancellation passed.')
    elif args.probe:
        reader = Reader(); reader.thread.start()
        time.sleep(args.probe)
        reader.stop.set(); reader.thread.join(timeout=2)
        state = reader.snapshot()
        (DATA_ROOT / 'probe_result.json').write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(state, ensure_ascii=True))
        if state['error'] or not state['ready']:
            raise SystemExit(1)
    else:
        # One app instance prevents competing streams and double button actions.
        mutex = None
        if not args.ui_check:
            import ctypes
            from ctypes import wintypes
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
            kernel.CreateMutexW.restype = wintypes.HANDLE
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            mutex = kernel.CreateMutexW(None, False, 'Local\\KariussMaxHeadtracking')
            if not mutex:
                raise ctypes.WinError(ctypes.get_last_error())
            if ctypes.get_last_error() == 183:
                (CONTROL_ROOT / 'window_request.txt').write_text('show', encoding='utf-8')
                user = ctypes.WinDLL('user32', use_last_error=True)
                user.FindWindowW.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR)
                user.FindWindowW.restype = wintypes.HWND
                user.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
                user.SetForegroundWindow.argtypes = (wintypes.HWND,)
                window = user.FindWindowW(None, APP_NAME)
                if window:
                    user.ShowWindow(window, 9)
                    user.SetForegroundWindow(window)
                kernel.CloseHandle(mutex)
                return
        try:
            gui(resume_send=args.resume_send, ui_check=args.ui_check, ui_language=args.ui_language)
        finally:
            if mutex:
                kernel.CloseHandle(mutex)


if __name__ == '__main__':
    main()
