# PyInstaller spec for a local-only Windows desktop bundle.
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules

repo_root = Path(SPECPATH).parent.parent
hidden = collect_submodules("fastapi") + collect_submodules("uvicorn")
a = Analysis(
    [str(repo_root / "packaging" / "desktop_entry.py")],
    pathex=[str(repo_root)],
    binaries=[],
    datas=[(str(repo_root / "web"), "web")],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [], name="SCALPER",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, disable_windowed_traceback=False, argv_emulation=False,
    target_arch=None, codesign_identity=None, entitlements_file=None,
)
