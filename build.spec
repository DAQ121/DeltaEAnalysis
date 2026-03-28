# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['build_windows.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('backend/*.py', 'backend'),
        ('frontend/*', 'frontend'),
        ('frontend/css/*', 'frontend/css'),
        ('frontend/js/*', 'frontend/js'),
    ],
    hiddenimports=[
        'flask',
        'flask_cors',
        'cv2',
        'numpy',
        'skimage',
        'PIL',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='试纸色差检测系统',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
