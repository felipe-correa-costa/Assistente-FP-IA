@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo =========================================
echo  Assistente FP - instalar microfone / voz
 echo =========================================
if not exist ".venv\Scripts\python.exe" (
    where py >nul 2>&1
    if errorlevel 1 (
        echo O Python nao foi encontrado. Instale Python para Windows.
        pause
        exit /b 1
    )
    py -3 -m venv .venv
    if errorlevel 1 (
        echo Falha na criacao do ambiente virtual.
        pause
        exit /b 1
    )
)
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requisitos_voz.txt
if errorlevel 1 (
    echo Instalacao nao concluida. Copie a mensagem de erro para diagnosticar.
    echo O chat por texto continua funcionando.
    pause
    exit /b 1
)
echo.
echo Pronto! Agora abra "Abrir Assistente.bat".
echo No primeiro uso do microfone o modelo Whisper sera baixado.
pause
