# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
import re
import tkinter as tk
import unittest
from datetime import datetime, timezone
from event_console import EventConsole, ConnectionEvents, format_event


class LogTests(unittest.TestCase):
    def test_timestamp_and_usb_transitions(self):
        self.assertEqual(format_event('Đã reset góc nhìn', datetime(2026,10,4,13,0,0,tzinfo=timezone.utc)),
                         '20:00:00 04/10/2026  Đã reset góc nhìn')
        observer = ConnectionEvents()
        state = dict(connected=False, ready=False, connection_enabled=True,
                     connection_session=0, error='Chưa thấy kính')
        self.assertEqual(len(observer.observe(state)),1)
        self.assertEqual(observer.observe(state),[])
        state.update(connected=True, connection_session=1, error=None)
        self.assertEqual(observer.observe(state),[('Đã kết nối với kính Rokid Max','success')])
        self.assertEqual(observer.observe(state),[])
        state['ready'] = True
        self.assertEqual(len(observer.observe(state)),1)
        self.assertEqual(observer.observe(state),[])
        state.update(connected=False, ready=False, error='Mất kết nối')
        self.assertEqual(len(observer.observe(state)),2)
        self.assertEqual(observer.observe(state),[])
        state.update(connected=True, connection_session=2, error=None)
        self.assertEqual(len(observer.observe(state)),1)

    def test_read_only_scrolling_history(self):
        root = tk.Tk()
        root.withdraw()
        try:
            console = EventConsole(root, lambda:None)
            for i in range(550):
                console.append('Hành động ' + str(i))
            text = console.text.get('1.0','end-1c')
            lines = text.splitlines()
            self.assertEqual(len(lines),500)
            self.assertTrue(lines[-1].endswith('Hành động 549'))
            self.assertRegex(lines[-1], r'^\d{2}:\d{2}:\d{2} \d{2}/\d{2}/\d{4}  ')
            self.assertEqual(console.text.cget('state'),'disabled')
            self.assertEqual(console.count,550)
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
