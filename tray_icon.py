# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Windows notification icon. All UI actions are queued for the Tk thread."""
import threading
from PIL import Image
import pystray


class TrayIcon:
    def __init__(self, commands, image_path, title, translate=lambda text: text):
        self.commands = commands
        self.ready = threading.Event()
        self.error = None
        self.translate = translate
        self.icon = pystray.Icon(
            'KariussMaxHeadtracking', Image.open(image_path).convert('RGBA'), title,
            menu=pystray.Menu(
                pystray.MenuItem(lambda item: translate('Mở cửa sổ'), self.command('show'), default=True),
                pystray.MenuItem(lambda item: translate('Nhìn về giữa'), self.command('center')),
                pystray.MenuItem(lambda item: translate('Tạm dừng / tiếp tục'), self.command('pause')),
                pystray.MenuItem(lambda item: translate('Kết nối / Ngắt kết nối'), self.command('connection')),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(lambda item: translate('Thoát hẳn'), self.command('quit')),
            ))
        self.thread = threading.Thread(target=self.run, daemon=True)

    def command(self, name):
        def callback(icon, item):
            self.commands.put(name)
        return callback

    def run(self):
        def setup(icon):
            icon.visible = True
            self.ready.set()
        try:
            self.icon.run(setup)
        except Exception as exc:
            self.error = str(exc)
        finally:
            self.ready.clear()

    def start(self):
        self.thread.start()

    def stop(self):
        self.icon.stop()
        self.thread.join(timeout=1)

    def title(self, text):
        if self.ready.is_set():
            self.icon.title = self.translate(text)[:127]

    def refresh_language(self):
        if self.ready.is_set():
            self.icon.update_menu()
