@echo off
title AI Coding Agent - Stop
setlocal

set ROOT=%~dp0

echo ============================================
echo   AI Coding Agent Platform - Stop / Cleanup
echo ============================================
echo.

:: ---------------------------------------------------------------------------
:: Locate docker (handle PATH not refreshed after install).
:: ---------------------------------------------------------------------------
where docker >nul 2>nul
if not errorlevel 1 goto DOCKER_OK
if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "PATH=%ProgramFiles%\Docker\Docker\resources\bin;%PATH%"
if exist "%LOCALAPPDATA%\Docker\Docker\resources\bin\docker.exe" set "PATH=%LOCALAPPDATA%\Docker\Docker\resources\bin;%PATH%"
:DOCKER_OK

:: ---------------------------------------------------------------------------
:: Stop and remove all project containers (frees the WSL/Docker memory).
:: Volumes (your DB, Qdrant data) are KEPT - this does NOT delete data.
:: ---------------------------------------------------------------------------
echo [INFO] Stopping AI Coding Agent containers...
docker compose -f "%ROOT%docker-compose.yml" down
if errorlevel 1 (
    echo [WARN] "docker compose down" reported an error ^(is Docker running?^).
)

:: ---------------------------------------------------------------------------
:: Stop the Ollama server we started (frees its CPU/RAM).
:: ---------------------------------------------------------------------------
echo [INFO] Stopping Ollama server...
taskkill /IM ollama.exe /F >nul 2>nul
if errorlevel 1 (
    echo [INFO] Ollama was not running.
) else (
    echo [INFO] Ollama stopped.
)

echo.
echo ============================================
echo   AI CODING AGENT STOPPED
echo ============================================
echo   - All project containers are down.
echo   - Ollama is stopped.
echo   - Your data ^(Postgres / Qdrant volumes^) is preserved.
echo.
echo   Tip: to release Docker's remaining memory fully, you can also run:
echo          wsl --shutdown
echo ============================================
echo.
echo Press any key to close.
pause >nul
endlocal
