# SPDX-FileCopyrightText: 2026 BOTProT800
# SPDX-License-Identifier: MIT

"""Receta de PyInstaller para el ejecutable de Windows.

Un solo archivo y sin consola: el destinatario es quien no tiene Python. La
licencia y los créditos viajan dentro del binario porque la MIT obliga a
acompañar el aviso de copyright allá donde se redistribuya el software.

No se excluyen módulos de la biblioteca estándar: recortar el bundle a mano
ahorra unos megas y arriesga un fallo de importación que solo aparece en la
máquina del usuario, ya congelado y sin consola donde leer el error.
"""

analysis = Analysis(
    ["run_darkstractor.py"],
    pathex=[],
    binaries=[],
    datas=[("LICENSE", "."), ("CREDITS.md", "."), ("CHANGELOG.md", ".")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="Darkstractor",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
