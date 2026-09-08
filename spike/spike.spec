# Сборка проверочного приложения.
#
# Смысл этого файла — выяснить, что ломается при упаковке связки
# FastAPI + uvicorn + pywebview, пока цена ошибки мала.
#
# Сборка: uv run --frozen --no-sync python -m PyInstaller spike/spike.spec --noconfirm

from PyInstaller.utils.hooks import collect_submodules

# uvicorn грузит протоколы и обработчики жизненного цикла по строковым именам,
# статический анализ их не видит и в бандл не кладёт
hiddenimports = (
    collect_submodules("uvicorn")
    + collect_submodules("webview")
    + ["anyio", "h11"]
)

# Собранный фронт кладём внутрь бандла: server.static_dir() ищет его
# относительно sys._MEIPASS
datas = [("frontend/dist", "frontend/dist")]

a = Analysis(
    ["backend/desktop.py"],
    pathex=["backend"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["torch", "nvidia", "matplotlib", "scipy", "pandas", "faster_whisper"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="voxduo-spike",
    debug=False,
    strip=False,
    upx=False,
    # Консоль оставлена намеренно: это проверочная сборка, и вывод об
    # ошибках старта нужнее, чем чистый вид
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="voxduo-spike",
)
