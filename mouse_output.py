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
from ctypes import wintypes

from motion_filter import wrap

MOUSE_SENSITIVITY_CHOICES = ('20%', '40%', '60%', '80%', '100%', '120%', '150%', '200%')


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
        self.reset()

    def reset(self):
        self.previous = None
        self.remainder = [0., 0.]
        self.last_delta = [0, 0]

    def start(self):
        self.reset()
        self.frames = 0
        self.enabled = True

    def stop(self):
        self.enabled = False
        self.reset()

    def center(self):
        self.reset()
        return self.sink.center()

    def update(self, pose, active=True):
        if not self.enabled or not active or not self.sink.available():
            self.reset()
            return False
        if len(pose) != 3 or not all(math.isfinite(a) for a in pose):
            raise ValueError('Invalid mouse orientation')
        if self.previous is None:
            self.previous = list(pose)
            return False
        delta = [wrap(pose[0] - self.previous[0]), -wrap(pose[1] - self.previous[1])]
        self.previous = list(pose)
        gain = self.units_per_degree * self.sensitivity
        movement = [d * gain + r for d, r in zip(delta, self.remainder)]
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
                'available': self.enabled and self.sink.available()}
