# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
import tkinter as tk
import unittest
import gc
from pathlib import Path
from tempfile import TemporaryDirectory
from localization import Translator, TranslatedStringVar, default_language
from event_console import EventConsole


class LocalizationTests(unittest.TestCase):
    def test_defaults_and_upgrade_preferences(self):
        self.assertEqual(default_language({}, 0x0409), 'en')
        self.assertEqual(default_language({}, 0x042a), 'vi')
        self.assertEqual(default_language({'motion_smoothing': 'Mượt vừa'}, 0x0409), 'vi')
        self.assertEqual(default_language({'language': 'en'}, 0x042a), 'en')
        self.assertEqual(default_language({'language': 'vi'}, 0x0409), 'vi')

    def test_dynamic_status_and_errors(self):
        translator = Translator('en')
        self.assertEqual(translator.tr('Tìm thấy 2 kính qua USB.'), 'Found 2 glasses via USB.')
        self.assertEqual(translator.tr('Game đã nhận kết nối: Flight Simulator 2024'),
                         'Game connected: Flight Simulator 2024')
        self.assertEqual(translator.tr('Đã chỉnh độ mượt: Mượt vừa; độ nhạy: 80%'),
                         'Smoothing set to: Medium; sensitivity: 80%')
        self.assertEqual(translator.tr('Không bật được kết nối game: Hãy tắt OpenTrack trước khi bật kết nối game trong Kariuss.'),
                         'Could not enable game connection: Close OpenTrack before enabling the game connection in Kariuss.')

    def test_combo_selection_keeps_canonical_value(self):
        root = tk.Tcl()
        translator = Translator('vi')
        variable = TranslatedStringVar(translator, master=root, value='Mượt vừa')
        status = TranslatedStringVar(translator, master=root, value='Tìm thấy 2 kính qua USB.')
        translator.set_language('en')
        self.assertEqual(root.getvar(variable._name), 'Medium')
        self.assertEqual(variable.get(), 'Mượt vừa')
        self.assertEqual(root.getvar(status._name), 'Found 2 glasses via USB.')
        root.setvar(variable._name, 'Strong')  # A selection written directly by a Tk combobox.
        self.assertEqual(variable.get(), 'Mượt nhiều')
        translator.set_language('vi')
        self.assertEqual(variable.get(), 'Mượt nhiều')
        self.assertEqual(root.getvar(variable._name), 'Mượt nhiều')
        self.assertEqual(status.get(), 'Tìm thấy 2 kính qua USB.')
        del variable, status, root
        gc.collect()

    def test_log_switch_preserves_time_count_and_disk_history(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with TemporaryDirectory() as directory:
                path = Path(directory) / 'activity.log'
                translator = Translator()
                console = EventConsole(root, lambda: None, path, translator.tr)
                console.append('Đã reset góc nhìn')
                original = console.latest
                file_contents = path.read_bytes()
                translator.set_language('en')
                console.refresh_language()
                self.assertEqual(console.latest[:19], original[:19])
                self.assertTrue(console.latest.endswith('View reset'))
                self.assertEqual(console.count, 1)
                self.assertEqual(path.read_bytes(), file_contents)
                translator.set_language('vi')
                console.refresh_language()
                self.assertEqual(console.latest, original)
                self.assertEqual(console.text.cget('state'), 'disabled')
        finally:
            root.destroy()
            gc.collect()


if __name__ == '__main__':
    unittest.main()
