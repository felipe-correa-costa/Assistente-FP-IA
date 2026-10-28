@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "assistente_gui.pyw"
    exit /b
)
where pyw >nul 2>&1
if not errorlevel 1 (
    start "" pyw -3 "assistente_gui.pyw"
    exit /b
)
where pythonw >nul 2>&1
if not errorlevel 1 (
    start "" pythonw "assistente_gui.pyw"
    exit /b
)
echo Python nao encontrado. Instale o Python 3 para Windows.
pause
