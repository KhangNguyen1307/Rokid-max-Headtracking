# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Read-only activity console, with Vietnam/Thailand local timestamps."""
from datetime import datetime, timedelta, timezone
from collections import deque
import tkinter as tk
from tkinter import ttk
from app_theme import BACKGROUND, TEXT, MUTED, SUCCESS, WARNING

LOCAL_TIME = timezone(timedelta(hours=7))


def format_event(message, now=None):
    instant = now or datetime.now(LOCAL_TIME)
    return instant.astimezone(LOCAL_TIME).strftime('%H:%M:%S %d/%m/%Y') + '  ' + message


class EventConsole(ttk.Frame):
    def __init__(self, parent, on_exit, log_path=None, translate=lambda text: text):
        super().__init__(parent)
        self.log_path = log_path
        self.translate = translate
        self.history = deque(maxlen=500)
        self.count = 0
        self.latest = ''
        toolbar = ttk.Frame(self)
        toolbar.pack(fill='x', pady=(0, 4))
        ttk.Label(toolbar, text='Nhật ký hoạt động', font=('Segoe UI',10,'bold')).pack(side='left')
        ttk.Button(toolbar, text='Thoát hẳn', command=on_exit).pack(side='right')
        body = tk.Frame(self, background='#000000', highlightthickness=1,
                        highlightbackground='#536071', highlightcolor='#536071', borderwidth=0)
        body.pack(fill='both', expand=True)
        self.text = tk.Text(body, height=5, wrap='word', font=('Consolas',10),
                            background='#000000', foreground=TEXT,
                            selectbackground='#435064', selectforeground=TEXT,
                            borderwidth=0, highlightthickness=0, padx=10, pady=8,
                            insertwidth=0, state='disabled')
        self.text.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(body, orient='vertical', command=self.text.yview)
        scroll.pack(side='right', fill='y')
        self.text.configure(yscrollcommand=scroll.set)
        self.text.tag_configure('time', foreground=MUTED)
        self.text.tag_configure('success', foreground=SUCCESS)
        self.text.tag_configure('warning', foreground=WARNING)

    def append(self, message, tone='success'):
        instant = datetime.now(LOCAL_TIME)
        self.history.append((instant, message, tone))
        line = format_event(self.translate(message), instant)
        self.count += 1
        self.latest = line
        at_bottom = self.text.yview()[1] >= .99
        self.text.configure(state='normal')
        self.text.insert('end', line[:19], 'time')
        self.text.insert('end', line[19:]+'\n', tone)
        # Bound visible history so a long flight cannot grow memory indefinitely.
        lines = int(self.text.index('end-1c').split('.')[0])
        if lines > 501:
            self.text.delete('1.0', f'{lines-500}.0')
        self.text.configure(state='disabled')
        if at_bottom:
            self.text.see('end')
        if self.log_path:
            try:
                with self.log_path.open('a', encoding='utf-8') as stream:
                    stream.write(line+'\n')
            except OSError:
                pass

    def refresh_language(self):
        """Translate visible history without changing timestamps or duplicating the log file."""
        position = self.text.yview()
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        for instant, message, tone in self.history:
            line = format_event(self.translate(message), instant)
            self.text.insert('end', line[:19], 'time')
            self.text.insert('end', line[19:] + '\n', tone)
            self.latest = line
        self.text.configure(state='disabled')
        if position[1] >= .99:
            self.text.see('end')
        else:
            self.text.yview_moveto(position[0])


class ConnectionEvents:
    """Only log lifecycle transitions, never each sensor sample or retry."""
    def __init__(self):
        self.previous = None

    def observe(self, state):
        old = self.previous
        self.previous = dict(state)
        events = []
        if state['connected'] and (old is None or state['connection_session'] != old['connection_session']):
            events.append(('Đã kết nối với kính Rokid Max', 'success'))
        if state['ready'] and (old is None or not old['ready']):
            events.append(('Kính đã sẵn sàng theo dõi đầu', 'success'))
        if old and old['connected'] and not state['connected'] and state['connection_enabled']:
            events.append(('Mất kết nối với kính. Đang tự kết nối lại', 'warning'))
        if state['error'] and (old is None or old['error'] != state['error']):
            events.append((state['error'], 'warning'))
        return events
