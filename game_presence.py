# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Observe running game clients without blocking drawing or head tracking."""
import ctypes
from ctypes import wintypes
import os
import threading

from game_output import ProcessEntry, kernel_api


class ModuleEntry(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('th32ModuleID', wintypes.DWORD),
                ('th32ProcessID', wintypes.DWORD), ('GlblcntUsage', wintypes.DWORD),
                ('ProccntUsage', wintypes.DWORD), ('modBaseAddr', wintypes.LPVOID),
                ('modBaseSize', wintypes.DWORD), ('hModule', wintypes.HMODULE),
                ('szModule', wintypes.WCHAR * 256), ('szExePath', wintypes.WCHAR * 260)]


def running_clients():
    """The profile ID alone survives game exit; also require a live client DLL."""
    kernel = kernel_api()
    kernel.Module32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ModuleEntry))
    kernel.Module32FirstW.restype = wintypes.BOOL
    kernel.Module32NextW.argtypes = kernel.Module32FirstW.argtypes
    kernel.Module32NextW.restype = wintypes.BOOL
    invalid = ctypes.c_void_p(-1).value
    processes = kernel.CreateToolhelp32Snapshot(2, 0)
    if processes == invalid:
        return []
    clients = []
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(processes, ctypes.byref(entry))
        while found:
            pid, name = entry.th32ProcessID, entry.szExeFile
            if pid != os.getpid() and name.lower() not in ('trackir.exe', 'opentrack.exe'):
                modules = kernel.CreateToolhelp32Snapshot(0x8 | 0x10, pid)
                if modules != invalid:
                    try:
                        module = ModuleEntry()
                        module.dwSize = ctypes.sizeof(module)
                        has_module = kernel.Module32FirstW(modules, ctypes.byref(module))
                        while has_module:
                            if module.szModule.lower() in ('npclient.dll', 'npclient64.dll',
                                                           'freetrackclient.dll', 'freetrackclient64.dll'):
                                clients.append({'pid': pid, 'name': name})
                                break
                            has_module = kernel.Module32NextW(modules, ctypes.byref(module))
                    finally:
                        kernel.CloseHandle(modules)
            found = kernel.Process32NextW(processes, ctypes.byref(entry))
    finally:
        kernel.CloseHandle(processes)
    return clients


class GamePresence:
    def __init__(self, scan=running_clients):
        self.scan = scan
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.registration = (False, 0)
        self.clients = []
        self.thread = threading.Thread(target=self.run, daemon=True, name='Kariuss-game-presence')

    def request(self, enabled, game_id):
        registration = (bool(enabled), int(game_id))
        with self.lock:
            if registration == self.registration:
                return
            self.registration = registration
            self.clients = []
        self.wake.set()

    def poll(self):
        with self.lock:
            registration = self.registration
        try:
            clients = self.scan() if registration[0] and registration[1] else []
        except OSError:
            clients = []
        with self.lock:
            # A slow process scan cannot restore an old connection after Stop.
            if registration == self.registration:
                self.clients = clients

    def snapshot(self):
        with self.lock:
            return {'connected': bool(self.registration[0] and self.registration[1] and self.clients),
                    'clients': list(self.clients)}

    def run(self):
        while not self.stop.is_set():
            self.wake.clear()
            self.poll()
            self.wake.wait(1.)

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread.is_alive():
            self.thread.join(timeout=1)
