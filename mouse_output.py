# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
"""Relative head-to-mouse output, with no clicks or keyboard events.

PhoenixHeadTracker's Mouse Track uses changes in yaw/pitch and Win32 SendInput.
This is an independent implementation of that approach: preserve fractional
movement, unwrap angle boundaries and discard history across control actions.
"""
import ctypes
import math
import os
import time
from ctypes import wintypes

from motion_filter import wrap

MOUSE_SENSITIVITY_CHOICES = ('20%', '40%', '60%', '80%', '100%', '120%', '150%', '200%')
MOUSE_STYLES = {'Giữ phím để đưa đầu về giữa': 'relative',
                'Giữ đầu lệch để quay liên tục': 'continuous'}
CLUTCH_KEYS = {'F6': 0x75, 'F7': 0x76, 'F9': 0x78, 'F10': 0x79,
               'Nút phụ chuột 1': 0x05, 'Nút phụ chuột 2': 0x06}
TURN_SPEEDS = {'Chậm': 800., 'Bình thường': 1600., 'Nhanh': 3200., 'Rất nhanh': 6400.}
DEADZONE_CHOICES = tuple(f'{angle}°' for angle in range(181))
TURN_ANGLE_CHOICES = tuple(f'{angle}°' for angle in range(0, 181, 15))


class MouseInput(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG),
                ('mouseData', wintypes.DWORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class KeyboardInput(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD),
                ('dwExtraInfo', ctypes.c_size_t)]


class HardwareInput(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]


class InputUnion(ctypes.Union):
    _fields_ = [('mouse', MouseInput), ('keyboard', KeyboardInput), ('hardware', HardwareInput)]


class Input(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('data', InputUnion)]


class MonitorInfo(ctypes.Structure):
    _fields_ = [('cbSize', wintypes.DWORD), ('rcMonitor', wintypes.RECT),
                ('rcWork', wintypes.RECT), ('dwFlags', wintypes.DWORD)]


class WindowsMouse:
    def __init__(self):
        self.user = ctypes.WinDLL('user32', use_last_error=True)
        self.user.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
        self.user.SendInput.restype = wintypes.UINT
        self.user.GetForegroundWindow.restype = wintypes.HWND
        self.user.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
        self.user.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user.GetCursorPos.argtypes = (ctypes.POINTER(wintypes.POINT),)
        self.user.GetCursorPos.restype = wintypes.BOOL
        self.user.MonitorFromPoint.argtypes = (wintypes.POINT, wintypes.DWORD)
        self.user.MonitorFromPoint.restype = wintypes.HANDLE
        self.user.GetMonitorInfoW.argtypes = (wintypes.HANDLE, ctypes.POINTER(MonitorInfo))
        self.user.GetMonitorInfoW.restype = wintypes.BOOL
        self.user.SetCursorPos.argtypes = (ctypes.c_int, ctypes.c_int)
        self.user.SetCursorPos.restype = wintypes.BOOL

    def available(self):
        # Leave Kariuss controls usable while its own window is in front.
        hwnd = self.user.GetForegroundWindow()
        pid = wintypes.DWORD()
        if not hwnd or not self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            return False
        return pid.value != os.getpid()

    def move(self, dx, dy):
        packet = Input(type=0, data=InputUnion(mouse=MouseInput(dx=dx, dy=dy, dwFlags=0x0001)))
        if self.user.SendInput(1, ctypes.byref(packet), ctypes.sizeof(Input)) != 1:
            raise OSError('Windows không nhận chuyển động chuột. Kiểm tra quyền chạy của app và game.')

    def key_down(self, key):
        return bool(self.user.GetAsyncKeyState(key) & 0x8000)

    def center(self):
        point = wintypes.POINT()
        if not self.user.GetCursorPos(ctypes.byref(point)):
            raise OSError('Không đọc được vị trí chuột.')
        monitor = self.user.MonitorFromPoint(point, 2)
        info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
        if not monitor or not self.user.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise OSError('Không xác định được màn hình của chuột.')
        rect = info.rcMonitor
        x, y = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
        if not self.user.SetCursorPos(x, y):
            raise OSError('Không đưa được chuột về giữa màn hình.')
        return x, y


class MouseOutput:
    def __init__(self, sink=None, sensitivity=.8, units_per_degree=20.):
        self.sink = sink if sink is not None else WindowsMouse()
        self.sensitivity = sensitivity
        self.units_per_degree = units_per_degree
        self.enabled = False
        self.frames = 0
        self.style = 'relative'
        self.clutch_key = CLUTCH_KEYS['F6']
        self.deadzone = 6.
        self.turn_angle = 30.
        self.turn_speed = TURN_SPEEDS['Bình thường']
        self.continuous_vertical = False
        self.clutch_held = False
        self.reset()

    def reset(self):
        self.previous = None
        self.remainder = [0., 0.]
        self.last_delta = [0, 0]
        self.neutral = None
        self.last_time = None

    def configure(self, *, style, clutch_key, deadzone, turn_angle, turn_speed, continuous_vertical):
        if (style not in MOUSE_STYLES.values() or clutch_key not in CLUTCH_KEYS.values()
                or deadzone not in range(181) or turn_angle not in range(0, 181, 15)
                or turn_speed not in TURN_SPEEDS.values()):
            raise ValueError('Invalid mouse control settings')
        self.style, self.clutch_key = style, clutch_key
        self.deadzone, self.turn_angle, self.turn_speed = deadzone, turn_angle, turn_speed
        self.continuous_vertical = bool(continuous_vertical)
        self.reset()

    def held_key(self):
        return bool(getattr(self.sink, 'key_down', lambda key: False)(self.clutch_key))

    def start(self):
        self.reset()
        self.clutch_held = False
        self.frames = 0
        self.enabled = True

    def stop(self):
        self.enabled = False
        self.clutch_held = False
        self.reset()

    def center(self):
        # Preserve the desktop cursor reset and discard the old head reference.
        # This does not claim to recenter an FPS game's camera.
        self.reset()
        return self.sink.center()

    def update(self, pose, active=True, now=None):
        now = time.perf_counter() if now is None else now
        if not self.enabled or not active or not self.sink.available():
            self.reset()
            return False
        if len(pose) != 3 or not all(math.isfinite(a) for a in pose):
            raise ValueError('Invalid mouse orientation')
        if self.previous is None:
            self.previous = list(pose)
            self.neutral = list(pose)
            self.last_time = now
            return False
        dt = min(.05, max(0., now - self.last_time))
        self.last_time = now
        delta = [wrap(pose[0] - self.previous[0]), -wrap(pose[1] - self.previous[1])]
        previous = self.previous
        self.previous = list(pose)
        gain = self.units_per_degree * self.sensitivity
        movement = [d * gain + r for d, r in zip(delta, self.remainder)]
        if self.style == 'continuous':
            for axis in (0, 1) if self.continuous_vertical else (0,):
                offset = wrap(pose[axis] - self.neutral[axis]) * (-1 if axis == 1 else 1)
                previous_offset = wrap(previous[axis] - self.neutral[axis]) * (-1 if axis == 1 else 1)
                if abs(offset) <= self.deadzone:
                    # The inner zone remains a normal head-controlled mouse.
                    # When returning from continuous turning, count only the
                    # part of this movement that occurred inside the zone.
                    relative = delta[axis]
                    if abs(previous_offset) > self.deadzone:
                        distance = abs(wrap(offset - math.copysign(self.deadzone, previous_offset)))
                        relative = math.copysign(min(abs(relative), distance), relative)
                    movement[axis] = relative * gain + self.remainder[axis]
                    continue
                elif self.turn_angle <= self.deadzone:
                    # Equal/reversed thresholds mean immediate maximum speed
                    # beyond the start angle, with no divide-by-zero or reversal.
                    strength = 1.
                else:
                    strength = min(1., (abs(offset) - self.deadzone) /
                                        (self.turn_angle - self.deadzone))
                movement[axis] = (math.copysign(strength, offset) * self.turn_speed *
                                  self.sensitivity * dt + self.remainder[axis])
                if abs(previous_offset) <= self.deadzone:
                    # Preserve the part of the outgoing move up to the boundary
                    # before switching to timed continuous output.
                    distance = abs(wrap(math.copysign(self.deadzone, offset) - previous_offset))
                    relative = math.copysign(min(abs(delta[axis]), distance), delta[axis])
                    movement[axis] += relative * gain
        dx, dy = [math.trunc(value) for value in movement]
        self.remainder = [movement[0] - dx, movement[1] - dy]
        self.last_delta = [dx, dy]
        if not dx and not dy:
            return False
        self.sink.move(dx, dy)
        self.frames += 1
        return True

    def snapshot(self):
        return {'enabled': self.enabled, 'frames_written': self.frames,
                'last_delta': list(self.last_delta), 'protocol': 'Windows mouse',
                'style': self.style, 'clutch_held': self.clutch_held,
                'available': self.enabled and self.sink.available()}
