@echo off
title SRJahir Tech Power Manager - Build EXE
color 0B
echo.
echo  ========================================
echo    Building Power Manager EXE
echo    SRJahir Tech - srjahir.in
echo  ========================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found!
    pause
    exit /b
)

echo  [1/3] Installing build dependencies...
pip install pyinstaller customtkinter psutil --quiet --break-system-packages 2>nul || pip install pyinstaller customtkinter psutil --quiet
pip install qbittorrent-api --quiet --break-system-packages 2>nul || pip install qbittorrent-api --quiet 2>nul

echo  [2/3] Building EXE...
pyinstaller --onefile --windowed --icon=app_icon.ico --name="SRJahir-Power-Manager" --add-data="app_icon.ico;." power_manager.py

echo  [3/3] Done!
echo.
echo  EXE location: dist\SRJahir-Power-Manager.exe
echo.
pause
