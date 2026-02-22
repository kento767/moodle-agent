@echo off
REM Moodle リマインドを実行（タスクスケジューラから呼ぶ想定）
cd /d "%~dp0"
if exist "venv\Scripts\activate.bat" (
  call venv\Scripts\activate.bat
  python main.py
) else (
  python main.py
)
