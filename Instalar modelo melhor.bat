@echo off
cd /d "%~dp0"
set "OLLAMA=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if exist "%OLLAMA%" (
  "%OLLAMA%" pull qwen3:4b-instruct
) else (
  ollama pull qwen3:4b-instruct
)
if errorlevel 1 echo Falha ao baixar modelo. Confira Ollama e conexao.
pause
