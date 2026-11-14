@echo off
cd /d "%~dp0"

if not exist ".venv313\Scripts\python.exe" (
    echo Python 3.13 environment not found.
    echo Create it with: py -3.13 -m venv .venv313
    echo Then install dependencies with:
    echo .venv313\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)

".venv313\Scripts\python.exe" -m flask --app app.index:app run --debug --host 127.0.0.1
pause
