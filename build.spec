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
        'flask.json',
        'werkzeug',
        'jinja2',
        'click',
        'itsdangerous',
        'cv2',
        'numpy',
        'skimage',
        'skimage.color',
        'PIL',
        'PIL.Image',
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
    [],
    exclude_binaries=True,
    name='TestStripDetection',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TestStripDetection',
)
