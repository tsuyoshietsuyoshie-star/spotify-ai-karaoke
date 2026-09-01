@echo off
title Spotify AI Karaoke & Fullscreen Visualizer
echo ========================================================
echo   Spotify AI Karaoke & Fullscreen Visualizer (Desktop App)
echo   Startet als eigenstaendige Windows-Anwendung!
echo ========================================================
echo.

set PYTHONDONTWRITEBYTECODE=1
set PYTHONPYCACHEPREFIX=%TEMP%\pycache

"D:\Aurora Projekt\TTS\All-in-One Voice Studio AI\backend_env\Scripts\python.exe" -B "%~dp0spotify_karaoke_app.py"
