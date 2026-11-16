@echo off
rem Abre o WayHub no navegador (http://localhost:8501). Feche esta janela para parar.
cd /d "%~dp0"
start "" cmd /c "timeout /t 8 >nul & start http://localhost:8501"
.venv\Scripts\python -m streamlit run app.py --server.headless true --server.port 8501
pause
