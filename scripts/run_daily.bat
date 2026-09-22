@echo off
rem Chay pipeline hang ngay. Duong dan tinh theo vi tri file nay nen chay duoc tren moi may.
rem Dung Python trong venv cua du an. Muon dung Python khac: set PYTHON_EXE=duong\dan\python.exe truoc khi chay.
setlocal
cd /d "%~dp0.."
if not defined PYTHON_EXE set "PYTHON_EXE=%CD%\venv\Scripts\python.exe"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
"%PYTHON_EXE%" -m weather_platform.daily_update
exit /b %ERRORLEVEL%
