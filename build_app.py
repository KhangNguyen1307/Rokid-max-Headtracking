# SPDX-License-Identifier: GPL-3.0-only
# Copyright (c) 2026 KhangNguyen1307
# See LICENSE; retained third-party notices apply to adapted portions.
"""Build a self-contained Windows folder from installed, pinned dependencies."""
import sys
import re
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path[:0] = [str(root / 'build_tools'), str(root / 'vendor')]
sys.path.insert(0, str(root / 'third_party'))
from PIL import Image, ImageDraw
import PyInstaller.__main__
version = re.search(r"^APP_VERSION = '([^']+)'", (root / 'rokid_tracker.py').read_text(encoding='utf-8'), re.M)[1]

assets = root / 'assets'
assets.mkdir(exist_ok=True)
# Geometric glasses icon drawn at 4x resolution for clean small Windows icons.
image = Image.new('RGBA', (1024, 1024))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((24, 24, 1000, 1000), radius=224, fill='#101e38')
draw.arc((104, 100, 920, 916), 210, 305, fill='#37d6e8', width=42)
draw.polygon([(862, 170), (918, 272), (800, 270)], fill='#37d6e8')
draw.rounded_rectangle((152, 384, 472, 654), radius=76, fill='#173952', outline='#eaf9ff', width=38)
draw.rounded_rectangle((552, 384, 872, 654), radius=76, fill='#173952', outline='#eaf9ff', width=38)
draw.line((466, 438, 510, 419, 558, 438), fill='#eaf9ff', width=36, joint='curve')
draw.line((152, 421, 106, 351), fill='#eaf9ff', width=38)
draw.line((872, 421, 918, 351), fill='#eaf9ff', width=38)
draw.line((245, 471, 296, 419), fill='#37d6e8', width=24)
draw.line((645, 471, 696, 419), fill='#37d6e8', width=24)
image.save(assets / 'kariuss.ico', sizes=[(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)])
image.resize((256, 256), Image.Resampling.LANCZOS).save(assets / 'kariuss.png')

PyInstaller.__main__.run([
    str(root / 'rokid_tracker.py'),
    '--name', 'Kariuss Max Headtracking', '--onedir', '--windowed', '--noupx', '--noconfirm',
    '--paths', str(root / 'third_party'),
    '--hidden-import', 'vqf.vqf', '--hidden-import', 'vqf.basicvqf',
    '--hidden-import', 'pystray._win32',
    '--copy-metadata', 'vqf', '--copy-metadata', 'hidapi', '--copy-metadata', 'pystray',
    '--add-data', str(assets / 'kariuss.ico') + ':assets',
    '--add-data', str(root / 'game_clients') + ':game_clients',
    '--add-data', str(root / 'licenses') + ':licenses',
    '--add-data', str(root / 'LICENSE') + ':licenses',
    '--add-data', str(root / 'THIRD_PARTY.md') + ':licenses',
    '--icon', str(assets / 'kariuss.ico'),
    '--distpath', str(root / 'releases' / version), '--workpath', str(root / 'build'),
    '--specpath', str(root), '--log-level', 'WARN',
])
import shutil
bundle = root / 'releases' / version / 'Kariuss Max Headtracking'
for name in ('LICENSE', 'THIRD_PARTY.md', 'THIRD_PARTY_EN.md', 'README.md', 'README_EN.md',
             'BUILDING.md', 'BUILDING_EN.md', 'Huong dan.txt', 'User Guide.txt'):
    shutil.copy2(root / name, bundle / name)
shutil.copytree(assets, bundle / 'assets', dirs_exist_ok=True)
shutil.copytree(root / 'licenses', bundle / 'licenses', dirs_exist_ok=True)
shutil.copytree(root / 'third_party' / 'pystray', bundle / 'third_party' / 'pystray',
                ignore=shutil.ignore_patterns('__pycache__', '*.pyc'), dirs_exist_ok=True)
