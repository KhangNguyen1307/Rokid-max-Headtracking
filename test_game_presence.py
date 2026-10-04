# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Connection colour must not rely on a profile ID left behind by an exited game."""
import ctypes
from pathlib import Path
import subprocess
import sys
import unittest

from game_presence import GamePresence, running_clients


class GamePresenceTests(unittest.TestCase):
    def test_registration_and_live_client_both_required(self):
        clients = [{'pid': 123, 'name': 'game.exe'}]
        calls = []
        def scan():
            calls.append(True)
            return list(clients)
        presence = GamePresence(scan)
        presence.request(True, 0)
        presence.poll()
        self.assertFalse(presence.snapshot()['connected'])
        self.assertFalse(calls)
        presence.request(True, 8151)
        presence.poll()
        self.assertTrue(presence.snapshot()['connected'])
        clients.clear()  # The process exits; the old shared-memory ID remains.
        presence.poll()
        self.assertFalse(presence.snapshot()['connected'])
        clients.append({'pid': 124, 'name': 'game.exe'})
        presence.poll()
        self.assertTrue(presence.snapshot()['connected'])
        presence.request(False, 8151)
        self.assertFalse(presence.snapshot()['connected'])
        self.assertEqual(presence.snapshot()['clients'], [])

    def test_old_scan_cannot_restore_disabled_connection(self):
        presence = GamePresence()
        def scan():
            presence.request(False, 0)
            return [{'pid': 123, 'name': 'game.exe'}]
        presence.scan = scan
        presence.request(True, 8151)
        presence.poll()
        self.assertFalse(presence.snapshot()['connected'])
        self.assertEqual(presence.snapshot()['clients'], [])

    def test_real_client_process_exit_without_game_memory_mutation(self):
        # Load only the DLL: do not register a game ID or touch the live output map.
        library = Path(__file__).resolve().parent / 'game_clients' / 'NPClient64.dll'
        script = 'import ctypes,sys; ctypes.WinDLL(sys.argv[1]); print("ready",flush=True); sys.stdin.readline()'
        child = subprocess.Popen([sys.executable, '-c', script, str(library)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'ready')
            self.assertIn(child.pid, [p['pid'] for p in running_clients()])
            child.communicate('\n', timeout=3)
            self.assertEqual(child.returncode, 0)
            self.assertNotIn(child.pid, [p['pid'] for p in running_clients()])
        finally:
            if child.poll() is None:
                child.communicate('\n', timeout=3)


if __name__ == '__main__':
    unittest.main()
