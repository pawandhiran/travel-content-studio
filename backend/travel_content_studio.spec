# PyInstaller spec for Travel Content Studio Backend
# Cross-platform: works on Windows and macOS

import sys
import platform

block_cipher = None

is_windows = sys.platform == 'win32'
is_macos = sys.platform == 'darwin'

icon_file = '../installer/assets/icon.ico' if is_windows else None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('prompts', 'prompts'),
        ('data', 'data'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'aiosqlite',
        'sqlalchemy.dialects.sqlite',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'PIL',
        'scipy',
    ],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='travel-content-studio-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=not is_macos,  # UPX not reliable on macOS ARM
    console=True,
    icon=icon_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=not is_macos,
    upx_exclude=[],
    name='travel-content-studio-backend',
)
