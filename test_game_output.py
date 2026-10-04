# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Windows ABI, game handshake, lifecycle, and registry ownership checks."""
import ctypes
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
import winreg

from game_output import FTData, FTHeap, GameOutput, RegistryLocation, load_games

ROOT = Path(__file__).resolve().parent
CLIENTS = ROOT / 'game_clients'


class TirData(ctypes.Structure):
    _fields_ = [('status', ctypes.c_int16), ('frame', ctypes.c_int16),
                ('checksum', ctypes.c_uint32)] + [
        (name, ctypes.c_float) for name in ('roll', 'pitch', 'yaw', 'x', 'y', 'z')
    ] + [('padding', ctypes.c_float * 9)]


class GameOutputTests(unittest.TestCase):
    def test_separate_game_process_receives_poses(self):
        with tempfile.TemporaryDirectory() as directory:
            output = GameOutput(CLIENTS, directory, register=False, helper=False)
            output.start()
            child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--client-probe'],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            try:
                deadline = time.monotonic() + 5
                while child.poll() is None and time.monotonic() < deadline:
                    output.update((30., -12., 7.))
                    time.sleep(.01)
                stdout, stderr = child.communicate(timeout=1)
                self.assertEqual(child.returncode, 0, stderr)
                received = json.loads(stdout)
                self.assertEqual(received['frames'], 10)
                for actual, expected in zip(received['angles'], (-30., 12., 7.)):
                    self.assertAlmostEqual(actual, expected, places=4)
                self.assertEqual(output.game_id, 8151)
            finally:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=2)
                output.stop()

    def test_client_library_receives_real_shared_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            output = GameOutput(CLIENTS, directory, register=False, helper=False)
            output.start()
            try:
                client = ctypes.WinDLL(str(CLIENTS / 'NPClient64.dll'))
                client.NP_RegisterProgramProfileID.argtypes = (ctypes.c_ushort,)
                client.NP_GetData.argtypes = (ctypes.POINTER(TirData),)
                client.NP_RegisterProgramProfileID(8151)
                self.assertTrue(output.update((30., -12., 7.)))
                state = output.snapshot()
                self.assertEqual(state['registered_game_name'], 'MS Flight Simulator 2024')
                self.assertEqual(output.heap.GameID2, 8151)
                self.assertEqual(bytes(output.heap.table), bytes(8))
                data = TirData()
                client.NP_GetData(ctypes.byref(data))
                for actual, expected in ((data.yaw, -30.), (data.pitch, 12.), (data.roll, 7.)):
                    self.assertAlmostEqual(actual * 180 / 16383, expected, places=4)
                frame = data.frame
                counter = output.heap.data.DataID
                # Sensor loss must freeze output and must not invent new samples.
                self.assertFalse(output.update((90., 90., 90.), active=False))
                self.assertEqual(output.heap.data.DataID, counter)
                client.NP_GetData(ctypes.byref(data))
                self.assertNotEqual(data.frame, frame)
                self.assertAlmostEqual(data.yaw * 180 / 16383, -30., places=4)
                output.update((0., 0., 0.))
                client.NP_GetData(ctypes.byref(data))
                self.assertEqual((data.yaw, data.pitch, data.roll), (0., 0., 0.))
                # FreeTrack clients see radians and zero translations in the same map.
                output.update((-20., 5., -3.))
                free = ctypes.WinDLL(str(CLIENTS / 'freetrackclient64.dll'))
                free.FTGetData.argtypes = (ctypes.POINTER(FTData),)
                free.FTGetData.restype = ctypes.c_int
                packet = FTData()
                self.assertTrue(free.FTGetData(ctypes.byref(packet)))
                self.assertAlmostEqual(packet.Yaw, math.radians(20), places=6)
                self.assertAlmostEqual(packet.Pitch, math.radians(-5), places=6)
                self.assertAlmostEqual(packet.Roll, math.radians(-3), places=6)
                self.assertEqual((packet.X, packet.Y, packet.Z), (0., 0., 0.))
                output.stop()
                self.assertFalse(output.update((1., 2., 3.)))
                output.start()  # Client is still holding the mapping across a restart.
                output.update((9., 2., 1.))
                client.NP_GetData(ctypes.byref(data))
                self.assertAlmostEqual(data.yaw * 180 / 16383, -9., places=4)
            finally:
                output.stop()

    def test_duplicate_writer_invalid_pose_and_owned_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            name = 'KariussOutputTest.' + uuid.uuid4().hex
            output = GameOutput(CLIENTS, directory, register=False, helper=True, guard=False,
                                mapping_name=name, mutex_name=name + '.mutex')
            output.start()
            child = output.helper
            try:
                other = GameOutput(CLIENTS, directory, register=False, helper=False, guard=False,
                                   mapping_name=name, mutex_name=name + '.mutex')
                output.update((10, 20, 30))
                with self.assertRaisesRegex(RuntimeError, 'Kariuss khác'):
                    other.start()
                self.assertTrue(output.enabled)
                self.assertAlmostEqual(output.heap.data.Roll, math.radians(30), places=6)
                self.assertFalse(output.update((float('nan'), 0, 0)))
                self.assertFalse(output.update((float('inf'), 0, 0)))
                self.assertFalse(output.update((0, 0)))
                self.assertEqual(output.frames, 1)
            finally:
                output.stop()
            self.assertIsNotNone(child.poll())

    def test_games_csv_handshake_tables(self):
        games = load_games(CLIENTS / 'games.csv')
        self.assertEqual(games[8151], ('MS Flight Simulator 2024', bytes(8)))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'games.csv'
            path.write_text('1;Example;FreeTrack20;V170;;;123;0001020304050607080900\n'
                            '2;Unencrypted;FreeTrack20;V160;;;124;0001020304050607080900\n',
                            encoding='utf-8')
            games = load_games(path)
            self.assertEqual(games[123][1], bytes.fromhex('0504030209080706'))
            self.assertEqual(games[124][1], bytes(8))


class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.key = 'Software\\KariussOutputTests\\' + uuid.uuid4().hex
        self.directory = tempfile.TemporaryDirectory()
        self.journal = Path(self.directory.name) / 'backup.json'
        self.location = Path(self.directory.name) / 'clients'

    def tearDown(self):
        for view in RegistryLocation.VIEWS:
            try:
                winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, self.key, view, 0)
            except FileNotFoundError:
                pass
        self.directory.cleanup()

    def write(self, value):
        for view in RegistryLocation.VIEWS:
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, self.key, 0,
                                   winreg.KEY_WRITE | view) as handle:
                winreg.SetValueEx(handle, 'Path', 0, winreg.REG_SZ, value)

    def registration(self):
        return RegistryLocation(self.location, self.journal, keys=(self.key,))

    def test_restore_original_and_absent_value(self):
        self.write('original/')
        registry = self.registration()
        registry.install()
        self.assertEqual(registry.read(self.key, registry.VIEWS[0])[0], registry.location)
        registry.restore()
        self.assertEqual(registry.read(self.key, registry.VIEWS[0])[0], 'original/')
        for view in registry.VIEWS:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.key, 0, winreg.KEY_WRITE | view) as handle:
                try:
                    winreg.DeleteValue(handle, 'Path')
                except FileNotFoundError:
                    pass
        registry = self.registration()
        registry.install()
        registry.restore()
        self.assertIsNone(registry.read(self.key, registry.VIEWS[0]))
        self.assertFalse(self.journal.exists())

    def test_restore_preserves_another_programs_new_location(self):
        self.write('original/')
        registry = self.registration()
        registry.install()
        self.write('other-program/')
        registry.restore()
        self.assertEqual(registry.read(self.key, registry.VIEWS[0])[0], 'other-program/')

    def test_crash_journal_keeps_original_before_repeated_start(self):
        self.write('original/')
        first = self.registration()
        first.install()  # Simulate no restore on process interruption.
        second = self.registration()
        second.install()
        second.restore()
        self.assertEqual(second.read(self.key, second.VIEWS[0])[0], 'original/')

    def test_invalid_journal_is_preserved_without_registry_changes(self):
        self.write('original/')
        self.journal.write_text('{broken', encoding='utf-8')
        registry = self.registration()
        with self.assertRaises(json.JSONDecodeError):
            registry.install()
        registry.restore()
        self.assertEqual(registry.read(self.key, registry.VIEWS[0])[0], 'original/')
        self.assertTrue(self.journal.exists())


if __name__ == '__main__':
    if '--client-probe' in sys.argv:
        client = ctypes.WinDLL(str(CLIENTS / 'NPClient64.dll'))
        client.NP_RegisterProgramProfileID.argtypes = (ctypes.c_ushort,)
        client.NP_GetData.argtypes = (ctypes.POINTER(TirData),)
        client.NP_RegisterProgramProfileID(8151)
        client.NP_StartDataTransmission()
        data = TirData()
        frames = set()
        deadline = time.monotonic() + 3
        while len(frames) < 10 and time.monotonic() < deadline:
            client.NP_GetData(ctypes.byref(data))
            if abs(data.yaw) > 1:
                frames.add(data.frame)
            time.sleep(.01)
        print(json.dumps({'frames': len(frames), 'angles': [
            value * 180 / 16383 for value in (data.yaw, data.pitch, data.roll)]}))
        raise SystemExit(0 if len(frames) == 10 else 1)
    unittest.main()
