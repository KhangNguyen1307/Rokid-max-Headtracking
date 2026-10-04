# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Exercise USB lifecycle with real worker/fusion and a simulated unplugged device."""
import struct
import threading
import time
import unittest
from rokid_tracker import Reader


class Bus:
    def __init__(self):
        self.present = threading.Event()
        self.present.set()
        self.path = b'first-usb-path'
        self.opened = []
        self.closed = []

    def enumerate(self):
        return [{'path': self.path, 'serial_number': 'same-glasses'}] if self.present.is_set() else []

    def device(self):
        bus = self
        class Device:
            timestamp = 0
            def open_path(self, path):
                if not bus.present.is_set() or path != bus.path:
                    raise OSError('device disappeared while opening')
                self.path = path
                bus.opened.append(path)
            def read(self, size, timeout):
                time.sleep(0.002)
                if not bus.present.is_set() or self.path != bus.path:
                    raise OSError('device unplugged')
                self.timestamp += 2264000
                packet = bytearray(64)
                packet[0] = 17
                struct.pack_into('<Q', packet, 1, self.timestamp)
                struct.pack_into('<9f', packet, 9, 0, 9.81, 0, 0, 0, 0, 0, 0, 0)
                packet[59], packet[60] = 80, 60
                return packet
            def close(self):
                bus.closed.append(self.path)
        return Device()


def wait_for(condition, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if condition():
            return
        time.sleep(0.01)
    raise AssertionError('USB lifecycle transition timed out')


class ConnectionTest(unittest.TestCase):
    def test_unplug_new_port_and_manual_disconnect(self):
        bus = Bus()
        reader = Reader(bus.enumerate, bus.device, settle_seconds=0.3, retry_seconds=0.04)
        reader.thread.start()
        try:
            wait_for(lambda: reader.snapshot()['ready'])
            first_session = reader.snapshot()['connection_session']
            reader.request_connection(False)
            self.assertFalse(reader.snapshot()['ready'])
            wait_for(lambda: len(bus.closed) == 1)
            opened = len(bus.opened)
            time.sleep(0.12)
            self.assertEqual(len(bus.opened), opened)
            selection = bus.enumerate()[0]
            reader.request_connection(True, selection)
            wait_for(lambda: reader.snapshot()['ready'])
            bus.present.clear()
            wait_for(lambda: not reader.snapshot()['connected'])
            self.assertFalse(reader.snapshot()['ready'])
            bus.path = b'different-usb-port'
            bus.present.set()
            wait_for(lambda: reader.snapshot()['ready'])
            self.assertEqual(bus.opened[-1], b'different-usb-port')
            self.assertGreater(reader.snapshot()['connection_session'], first_session)
            self.assertIsNone(reader.snapshot()['error'])
            self.assertLess(max(abs(v) for v in reader.snapshot()['angles_deg']), 0.01)
            self.assertEqual(reader.take_buttons(), [])  # Reconnect establishes a fresh baseline.
        finally:
            reader.stop.set()
            reader.wake.set()
            reader.thread.join(timeout=1)
            self.assertFalse(reader.thread.is_alive())

    def test_absent_start_then_connect(self):
        bus = Bus()
        bus.present.clear()
        reader = Reader(bus.enumerate, bus.device, settle_seconds=0.3, retry_seconds=0.04)
        reader.thread.start()
        try:
            wait_for(lambda: reader.snapshot()['error'] is not None)
            reader.request_connection(False)
            bus.present.set()
            time.sleep(0.12)
            self.assertEqual(bus.opened, [])
            reader.request_connection(True)
            wait_for(lambda: reader.snapshot()['ready'])
            self.assertEqual(len(bus.opened), 1)
        finally:
            reader.stop.set()
            reader.wake.set()
            reader.thread.join(timeout=1)


if __name__ == '__main__':
    unittest.main()
