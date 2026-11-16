@echo off
rem Instala o WayHub no Windows (rode uma vez, com internet)
cd /d "%~dp0"
py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
if not exist .venv\Scripts\python.exe (echo ERRO: Python nao encontrado. Instale o Python 3.12 marcando "Add python.exe to PATH". & pause & exit /b 1)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
echo.
echo Pronto! Agora use o INICIAR_WAYHUB.bat
pause
