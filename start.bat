@echo off
title Heatseeker
taskkill /f /im python.exe 2>nul
timeout /t 1 /nobreak >nul
start http://localhost:5000
python app.py
