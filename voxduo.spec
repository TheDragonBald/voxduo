# Сборка voxduo.exe для тех, у кого нет Python.
#
# Что входит и почему именно так:
#
# * Распознавание — только на процессоре. Библиотеки CUDA от NVIDIA занимают
#   около гигабайта и распространяются под проприетарной лицензией, поэтому в
#   бинарник не кладутся. Кому нужна видеокарта — ставит из исходников.
# * Синтез — edge-tts и Piper. Silero требует torch, а это ещё четверть
#   гигабайта ради одного движка; в собранной версии он просто покажется
#   недоступным.
# * Модели не входят вовсе: они качаются при первом запуске в
#   %LOCALAPPDATA%/VoxDuo/models. Иначе .exe весил бы под четыре гигабайта.
#
# Сборка: just build

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

datas = []
hiddenimports = []

# customtkinter возит с собой темы и шрифты отдельными файлами
datas += collect_data_files("customtkinter")

# faster_whisper держит рядом модель Silero VAD в формате onnx
datas += collect_data_files("faster_whisper")

# edge_tts тянет certifi для проверки сертификатов
datas += collect_data_files("certifi")

# Piper нужен espeak-ng для фонемизации, но вместе с ним приезжают данные
# для языков, которых у нас нет: огласовки иврита весят 21 МБ, арабского —
# ещё 4.6 МБ. Плюс картинки и шаблоны его собственного веб-интерфейса.
_PIPER_SKIP = ("piper/hebrew", "piper/tashkeel", "piper/img", "piper/templates")
datas += [
    entry
    for entry in collect_data_files("piper")
    if not any(entry[1].replace("\\", "/").startswith(skip) for skip in _PIPER_SKIP)
]

# Без метаданных importlib.metadata.version() не находит пакеты, и сводка
# по --check показывает «не установлен» для всего подряд — ровно там, где
# она нужнее всего: в баг-репортах от пользователей без Python.
for _package in (
    "faster-whisper",
    "ctranslate2",
    "onnxruntime",
    "customtkinter",
    "edge-tts",
    "piper-tts",
    "sounddevice",
    "soundfile",
    "numpy",
):
    datas += copy_metadata(_package)

# Подтягиваются динамически, статический анализ их не находит
hiddenimports += collect_submodules("edge_tts")
hiddenimports += ["sounddevice", "soundfile", "_soundfile_data"]

# Что не нужно в бинарнике
excludes = [
    "torch",            # только для Silero, четверть гигабайта
    "torchaudio",
    "torchvision",
    "nvidia",           # проприетарные библиотеки CUDA, около гигабайта
    "matplotlib",
    "scipy",
    "pandas",
    "IPython",
    "pytest",
    "notebook",
    "transformers",
    # Стек вертикального среза Ф0: он живёт в spike/ и на пути запуска
    # Tkinter-версии не встречается (проверено обходом импортов). Строки
    # здесь — страховка: случайный импорт не утащит полсотни мегабайт в
    # бандл незаметно. Имена модульные, а не имена дистрибутивов, поэтому
    # webview, а не pywebview: excludes сверяется с тем, что пишут в import.
    "webview",
    "fastapi",
    "uvicorn",
    "websockets",
    "starlette",
    "pydantic",
    # av сюда НЕ вносить: tts/player.py декодирует им MP3.
]

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="voxduo",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # приложение оконное, чёрная консоль рядом не нужна
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="voxduo",
)
