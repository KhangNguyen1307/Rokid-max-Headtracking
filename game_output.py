# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Direct Windows game output, compatible with opentrack's FreeTrack/NPClient ABI.

Only this writer runs in Kariuss. The small, unmodified opentrack client libraries
are loaded by games; no opentrack application is launched. Protocol reference:
https://github.com/opentrack/opentrack/blob/master/proto-ft/ftnoir_protocol_ft.cpp
"""
import csv
import ctypes
from ctypes import wintypes
import json
import math
import mmap
from pathlib import Path
import subprocess
import winreg


class FTData(ctypes.Structure):
    _fields_ = [('DataID', ctypes.c_uint32), ('CamWidth', ctypes.c_int32),
                ('CamHeight', ctypes.c_int32)] + [
        (name, ctypes.c_float) for name in (
            'Yaw', 'Pitch', 'Roll', 'X', 'Y', 'Z', 'RawYaw', 'RawPitch', 'RawRoll',
            'RawX', 'RawY', 'RawZ', 'X1', 'Y1', 'X2', 'Y2', 'X3', 'Y3', 'X4', 'Y4')]


class FTHeap(ctypes.Structure):
    _fields_ = [('data', FTData), ('GameID', ctypes.c_int32),
                ('table', ctypes.c_ubyte * 8), ('GameID2', ctypes.c_int32)]


assert ctypes.sizeof(FTData) == 92 and ctypes.sizeof(FTHeap) == 108


class ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]


def kernel_api():
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(ProcessEntry))
    kernel.Process32FirstW.restype = wintypes.BOOL
    kernel.Process32NextW.argtypes = kernel.Process32FirstW.argtypes
    kernel.Process32NextW.restype = wintypes.BOOL
    return kernel


def process_names():
    kernel = kernel_api()
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        names = set()
        found = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while found:
            names.add(entry.szExeFile.lower())
            found = kernel.Process32NextW(handle, ctypes.byref(entry))
        return names
    finally:
        kernel.CloseHandle(handle)


def load_games(path):
    games = {}
    with Path(path).open(encoding='utf-8-sig', errors='replace', newline='') as stream:
        for row in csv.reader(stream, delimiter=';'):
            if len(row) < 8:
                continue
            try:
                game_id = int(row[6])
                code = bytes.fromhex(row[7]) if row[3] != 'V160' and len(row[7]) == 22 else b''
            except ValueError:
                continue
            table = code[2:6][::-1] + code[6:10][::-1] if code else bytes(8)
            games.setdefault(game_id, (row[1], table))
    return games


class RegistryLocation:
    """Restore only values still owned by us, including after an interrupted run.

    Both registry views are captured before any write, because HKCU keys can be
    shared between the views. A journal preserves the original value on crashes.
    """
    KEYS = (r'Software\NaturalPoint\NATURALPOINT\NPClient Location',
            r'Software\Freetrack\FreetrackClient')
    VIEWS = (winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY)

    def __init__(self, location, journal_path, keys=None):
        self.location = Path(location).resolve().as_posix().rstrip('/') + '/'
        self.journal_path = Path(journal_path)
        self.keys = keys or self.KEYS
        self.records = []
        self.journal_written = False

    @staticmethod
    def read(key, view):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | view) as handle:
                return winreg.QueryValueEx(handle, 'Path')
        except FileNotFoundError:
            return None

    def install(self):
        # Recover a journal only if it belongs to these exact keys and views.
        recovered = {}
        if self.journal_path.exists():
            old = json.loads(self.journal_path.read_text(encoding='utf-8'))
            if old.get('keys') != list(self.keys):
                raise RuntimeError('Không đọc được bản lưu kết nối game. Chưa thay đổi cài đặt Windows.')
            recovered = {(r['key'], r['view']): r for r in old['records']}
        for key in self.keys:
            for view in self.VIEWS:
                previous = self.read(key, view)
                old_record = recovered.get((key, view))
                if old_record and previous and previous[0] == old.get('location'):
                    previous = old_record['previous']
                self.records.append({'key': key, 'view': view, 'previous': previous})
        self.journal_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.journal_path.with_suffix('.tmp')
        temp.write_text(json.dumps({'keys': list(self.keys), 'location': self.location,
                                    'records': self.records}, ensure_ascii=False), encoding='utf-8')
        temp.replace(self.journal_path)
        self.journal_written = True
        try:
            for record in self.records:
                with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, record['key'], 0,
                                       winreg.KEY_WRITE | record['view']) as handle:
                    winreg.SetValueEx(handle, 'Path', 0, winreg.REG_SZ, self.location)
        except Exception:
            self.restore()
            raise

    def restore(self):
        if not self.journal_written:
            return
        for record in self.records:
            current = self.read(record['key'], record['view'])
            if not current or current[0] != self.location:
                continue  # Another program changed it; its setting wins.
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, record['key'], 0,
                                winreg.KEY_WRITE | record['view']) as handle:
                previous = record['previous']
                if previous is None:
                    winreg.DeleteValue(handle, 'Path')
                else:
                    winreg.SetValueEx(handle, 'Path', 0, previous[1], previous[0])
        self.records.clear()
        self.journal_path.unlink(missing_ok=True)
        self.journal_written = False


class GameOutput:
    def __init__(self, resources, data_root, *, register=True, helper=True, guard=True,
                 mapping_name='FT_SharedMem', mutex_name='FT_Mutext'):
        self.resources = Path(resources)
        self.data_root = Path(data_root)
        self.register = register
        self.helper_enabled = helper
        self.guard = guard
        self.mapping_name = mapping_name
        self.mutex_name = mutex_name
        self.kernel = kernel_api()
        self.memory = self.heap = self.mutex = self.writer = self.registry = self.helper = None
        self.enabled = False
        self.game_id = 0
        self.game_name = ''
        self.frames = 0
        self.games = load_games(self.resources / 'games.csv')

    def start(self):
        if self.enabled:
            return
        for filename in ('NPClient.dll', 'NPClient64.dll', 'freetrackclient.dll',
                         'freetrackclient64.dll', 'TrackIR.exe'):
            if not (self.resources / filename).is_file():
                raise RuntimeError('Thiếu thành phần kết nối game: ' + filename)
        if self.guard and 'opentrack.exe' in process_names():
            raise RuntimeError('Hãy tắt OpenTrack trước khi bật kết nối game trong Kariuss.')
        try:
            self.writer = self.kernel.CreateMutexW(None, False, 'Local\\Kariuss.GameWriter.' + self.mapping_name)
            if not self.writer:
                raise ctypes.WinError(ctypes.get_last_error())
            if ctypes.get_last_error() == 183:
                raise RuntimeError('Đã có một Kariuss khác gửi chuyển động vào game.')
            self.mutex = self.kernel.CreateMutexW(None, False, self.mutex_name)
            if not self.mutex:
                raise ctypes.WinError(ctypes.get_last_error())
            self.memory = mmap.mmap(-1, ctypes.sizeof(FTHeap), tagname=self.mapping_name,
                                    access=mmap.ACCESS_WRITE)
            self.heap = FTHeap.from_buffer(self.memory)
            # A running game may still hold the map: preserve its registration ID.
            self.heap.data = FTData(DataID=1, CamWidth=100, CamHeight=250)
            self.heap.GameID2 = 0
            self.heap.table[:] = bytes(8)
            self.game_id = 0
            self.game_name = ''
            self.frames = 0
            if self.register:
                self.registry = RegistryLocation(self.resources, self.data_root / 'game_registry_backup.json')
                self.registry.install()
            if self.helper_enabled:
                startup = subprocess.STARTUPINFO()
                startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow = 0
                self.helper = subprocess.Popen([str(self.resources / 'TrackIR.exe')],
                                               cwd=self.resources, startupinfo=startup,
                                               creationflags=subprocess.CREATE_NO_WINDOW)
            self.enabled = True
        except Exception:
            self.stop()
            raise

    def update(self, angles, active=True):
        if not self.enabled:
            return False
        if len(angles) != 3 or not all(math.isfinite(a) for a in angles):
            return False
        # FreeTrack clients take this mutex; NPClient uses aligned 32-bit fields,
        # just like opentrack. Never block the GUI waiting for a game reader.
        result = self.kernel.WaitForSingleObject(self.mutex, 0)
        if result not in (0, 0x80):
            return False
        try:
            game_id = self.heap.GameID
            if game_id != self.heap.GameID2:
                name, table = self.games.get(game_id, (f'Game {game_id}', bytes(8)))
                self.heap.table[:] = table
                self.heap.GameID2 = game_id
                self.heap.data.DataID = 0
                self.game_id = game_id
                self.game_name = name if game_id else ''
            if not active:
                return False
            yaw, pitch, roll = angles
            data = self.heap.data
            data.Yaw = math.radians(-yaw)
            data.Pitch = math.radians(-(89.86 if abs(pitch - 90) < .15 else pitch))
            data.Roll = math.radians(roll)
            data.RawYaw = math.radians(-yaw)
            data.RawPitch = math.radians(pitch)
            data.RawRoll = math.radians(roll)
            data.DataID = (data.DataID + 1) % (1 << 29)
            self.frames += 1
            return True
        finally:
            self.kernel.ReleaseMutex(self.mutex)

    def snapshot(self):
        # GameID is a registration, not a live acknowledgement for every frame.
        return {'enabled': self.enabled, 'registered_game_id': self.game_id,
                'registered_game_name': self.game_name, 'frames_written': self.frames,
                'client_directory': str(self.resources), 'protocol': 'FreeTrack / TrackIR'}

    def stop(self):
        self.enabled = False
        try:
            try:
                if self.helper is not None:
                    # Terminate only the child handle created by this instance.
                    if self.helper.poll() is None:
                        self.helper.terminate()
                        self.helper.wait(timeout=2)
            finally:
                self.helper = None
                if self.registry is not None:
                    self.registry.restore()
        finally:
            self.registry = None
            self.heap = None
            if self.memory is not None:
                self.memory.close()
                self.memory = None
            for name in ('mutex', 'writer'):
                handle = getattr(self, name)
                if handle:
                    self.kernel.CloseHandle(handle)
                    setattr(self, name, None)
            self.game_id = 0
            self.game_name = ''
