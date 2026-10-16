# Reproducible service bundle used by menubar/build.sh --release (no separate launcher app).
from pathlib import Path
ROOT = Path(SPECPATH)
a = Analysis([str(ROOT / 'backend/main.py')], pathex=[str(ROOT)],
    binaries=[(str(ROOT / 'mac-evo16/mac-evo16'), 'mac-evo16')],
    datas=[(str(ROOT / 'web'), 'web')],
    hiddenimports=['backend.config', 'backend.runtime', 'backend.security', 'backend.presets',
                   'uvicorn.logging', 'uvicorn.loops.asyncio', 'uvicorn.protocols.http.h11_impl',
                   'uvicorn.lifespan.on'],
    excludes=['tkinter', 'matplotlib', 'numpy', 'pandas'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='EVO16Service', console=True)
coll = COLLECT(exe, a.binaries, a.datas, name='EVO16Service')
