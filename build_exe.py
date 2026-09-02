"""Скрипт для сборки .exe файла с PyInstaller.

Собирается тонкий клиент: только tkinter + python-dotenv.
Telethon/aiogram/AI не нужны — вся работа идёт на сервере.
"""
import sys

import PyInstaller.__main__

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PyInstaller.__main__.run([
    '--onefile',
    '--name=LeadHunter',
    '--icon=NONE',
    '--hidden-import=dotenv',
    '--console',
    'main_gui.py'
])

print("\n✅ Сборка завершена!")
print("📁 .exe файл находится в: dist/LeadHunter.exe")
print("📋 Рядом с .exe нужен файл .env с двумя строками:")
print("   SERVER_URL=http://82.202.170.14:8080")
print("   API_TOKEN=<токен с сервера>")
