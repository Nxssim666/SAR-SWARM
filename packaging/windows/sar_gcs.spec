# PyInstaller spec of the Windows package (M6): the fleet service with the built console
# (copied into fleet_service/static/console before the build), in one folder:
# SAR-GCS/sar-gcs.exe and SAR-GCS/_internal/. Built by .github/workflows/package.yml.
#
#   cd fleet-service && uv run --with pyinstaller pyinstaller ../packaging/windows/sar_gcs.spec
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

datas, binaries, hiddenimports = [], [], []
# The service's migrations are Python files that Alembic loads by path; its vendored Swagger
# UI and the packaged console are data.
datas += collect_data_files("fleet_service", include_py_files=True)
hiddenimports += collect_submodules("fleet_service")
# Native libraries and data files loaded at run time.
for package in ("mavsdk", "pyproj", "shapely", "contourpy", "argon2", "_argon2_cffi_bindings"):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h
# Imported by name at run time (uvicorn's protocols, SQLAlchemy's async SQLite dialect).
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("websockets")
hiddenimports += collect_submodules("aiosqlite")
hiddenimports += ["sqlalchemy.dialects.sqlite.aiosqlite", "sqlalchemy.dialects.sqlite.pysqlite"]
hiddenimports += collect_submodules("alembic")

a = Analysis(
    ["sar_gcs.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="sar-gcs",
    console=True,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="SAR-GCS")
