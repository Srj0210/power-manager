@echo off
title SRJahir Tech Power Manager v2.0 - Setup
color 0B
echo.
echo  ========================================
echo    SRJahir Tech Power Manager v2.0
echo    https://srjahir.in
echo  ========================================
echo.

python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo  [ERROR] Python not found! Install from python.org
    pause
    exit /b
)

echo  [1/2] Installing dependencies...
pip install customtkinter psutil --quiet --break-system-packages 2>nul || pip install customtkinter psutil --quiet
echo  [OK] Core dependencies installed.
echo.
echo  [Optional] qBittorrent API support...
pip install qbittorrent-api --quiet --break-system-packages 2>nul || pip install qbittorrent-api --quiet 2>nul
echo.
echo  [2/2] Launching...
start "" python "%~dp0power_manager.py"
