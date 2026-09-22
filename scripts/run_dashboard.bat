@echo off
rem Mo dashboard tai http://localhost:8501
setlocal
cd /d "%~dp0.."
if not defined PYTHON_EXE set "PYTHON_EXE=%CD%\venv\Scripts\python.exe"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
"%PYTHON_EXE%" -m streamlit run dashboard\dashboard.py
exit /b %ERRORLEVEL%
