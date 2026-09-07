"""Точка входа для собранного .exe.

PyInstaller не умеет запускать пакет как `python -m voxduo`, ему нужен
обычный скрипт. Здесь он и есть — вся логика остаётся в voxduo/__main__.py.
"""

from __future__ import annotations

import sys

from voxduo.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
