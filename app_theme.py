# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Shared dark palette for the window, controls, model and activity console."""
from tkinter import ttk

BACKGROUND = '#20242b'
TEXT = '#e7ecf2'
MUTED = '#a8b4c5'
SUCCESS = '#86d9b4'
WARNING = '#f0c784'
GUIDE = '#536071'


def apply_dark_theme(root):
    root.configure(background=BACKGROUND)
    style = ttk.Style(root)
    style.theme_use('clam')
    button, hover, pressed, border = '#343c48', '#435064', '#293440', '#4a5666'
    style.configure('.', background=BACKGROUND, foreground=TEXT,
                    bordercolor=border, lightcolor=border, darkcolor=border,
                    troughcolor=BACKGROUND, selectbackground=hover, selectforeground=TEXT)
    style.configure('TFrame', background=BACKGROUND)
    style.configure('TLabel', background=BACKGROUND, foreground=TEXT, font=('Segoe UI',11))
    style.configure('TButton', background=button, foreground=TEXT, font=('Segoe UI',11),
                    padding=8, bordercolor=border, lightcolor=button, darkcolor=button)
    style.map('TButton', background=[('disabled',BACKGROUND),('pressed',pressed),('active',hover)],
              foreground=[('disabled','#8893a3')],
              lightcolor=[('active',hover)], darkcolor=[('active',hover)])
    for name, color, over, down in (
            ('GameConnected.TButton', '#256b4b', '#31855e', '#1d533a'),
            ('GameWaiting.TButton', '#943e43', '#af4c52', '#773238')):
        style.configure(name, background=color, foreground='#ffffff',
                        bordercolor=color, lightcolor=color, darkcolor=color)
        style.map(name, background=[('pressed',down),('active',over)],
                  foreground=[('disabled','#ffffff')],
                  lightcolor=[('pressed',down),('active',over)],
                  darkcolor=[('pressed',down),('active',over)])
    style.configure('TCheckbutton', background=BACKGROUND, foreground=TEXT,
                    font=('Segoe UI',10), indicatorbackground=button, indicatorforeground=TEXT)
    style.map('TCheckbutton', background=[('active',BACKGROUND)],
              indicatorbackground=[('selected','#347968'),('active',hover)],
              foreground=[('disabled','#8893a3')])
    style.configure('TCombobox', background=button, fieldbackground=button, foreground=TEXT,
                    arrowcolor=TEXT, selectbackground=hover, selectforeground=TEXT,
                    bordercolor=border, lightcolor=button, darkcolor=button, padding=4)
    style.map('TCombobox', fieldbackground=[('readonly',button),('disabled',BACKGROUND)],
              foreground=[('readonly',TEXT),('disabled','#8893a3')],
              background=[('active',hover)], arrowcolor=[('disabled','#8893a3')])
    root.option_add('*TCombobox*Listbox.background',button)
    root.option_add('*TCombobox*Listbox.foreground',TEXT)
    root.option_add('*TCombobox*Listbox.selectBackground',hover)
    root.option_add('*TCombobox*Listbox.selectForeground',TEXT)
    style.configure('TNotebook', background=BACKGROUND, bordercolor=border,
                    lightcolor=border, darkcolor=border)
    style.configure('TNotebook.Tab', background=button, foreground=MUTED,
                    padding=(12,7), font=('Segoe UI',10), lightcolor=button, darkcolor=button)
    style.map('TNotebook.Tab', background=[('selected',BACKGROUND),('active',hover)],
              foreground=[('selected',TEXT),('active',TEXT)],
              lightcolor=[('selected',border)], darkcolor=[('selected',border)])
    style.configure('TSeparator', background=border)
    style.configure('Vertical.TScrollbar', background=button, arrowcolor=TEXT,
                    troughcolor=BACKGROUND, lightcolor=button, darkcolor=button, bordercolor=BACKGROUND)
    style.map('Vertical.TScrollbar', background=[('active',hover),('pressed',pressed)])
    # Ask Windows to match this app's title bar to its dark content.
    try:
        import ctypes
        from ctypes import wintypes
        root.update_idletasks()
        user = ctypes.WinDLL('user32')
        user.GetAncestor.argtypes = (wintypes.HWND,wintypes.UINT)
        user.GetAncestor.restype = wintypes.HWND
        hwnd = user.GetAncestor(root.winfo_id(),2)
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = (wintypes.HWND,wintypes.DWORD,wintypes.LPCVOID,wintypes.DWORD)
        enabled = wintypes.BOOL(True)
        result = dwm.DwmSetWindowAttribute(hwnd,20,ctypes.byref(enabled),ctypes.sizeof(enabled))
        if result:
            dwm.DwmSetWindowAttribute(hwnd,19,ctypes.byref(enabled),ctypes.sizeof(enabled))
    except (AttributeError,OSError):
        pass
