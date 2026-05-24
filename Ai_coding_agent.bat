@echo off
title AI Coding Agent - Launcher
setlocal enabledelayedexpansion

set ROOT=%~dp0
set BACKEND_PORT=8000
set FRONTEND_PORT=3000
set FRONTEND_URL=http://localhost:%FRONTEND_PORT%
set BACKEND_URL=http://localhost:%BACKEND_PORT%

echo ============================================
echo   AI Coding Agent Platform - Launcher
echo ============================================
echo.

:: ---------------------------------------------------------------------------
:: Prerequisites: Docker Desktop must be installed and running.
:: If docker is missing from PATH, try the common install dirs (handles the
:: case where Docker was just installed and PATH isn't refreshed yet).
:: ---------------------------------------------------------------------------
where docker >nul 2>nul
if not errorlevel 1 goto DOCKER_OK
if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" set "PATH=%ProgramFiles%\Docker\Docker\resources\bin;%PATH%"
if exist "%ProgramW6432%\Docker\Docker\resources\bin\docker.exe" set "PATH=%ProgramW6432%\Docker\Docker\resources\bin;%PATH%"
if exist "%LOCALAPPDATA%\Docker\Docker\resources\bin\docker.exe" set "PATH=%LOCALAPPDATA%\Docker\Docker\resources\bin;%PATH%"
where docker >nul 2>nul
if not errorlevel 1 goto DOCKER_OK
echo [ERROR] docker not found on this machine.
echo.
echo         Install Docker Desktop:
echo           https://www.docker.com/products/docker-desktop/
echo.
echo         After install:
echo           1. Reboot Windows.
echo           2. Launch Docker Desktop from the Start menu.
echo           3. Wait for the tray icon to say "Docker Desktop is running".
echo           4. Run this file again.
echo.
echo         If you just installed Docker, close this window and open a NEW
echo         one, or restart Windows, then run this file again.
echo.
pause
exit /b 1
:DOCKER_OK

docker compose version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] "docker compose" v2 not available. Update Docker Desktop.
    echo.
    pause
    exit /b 1
)

docker info >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Docker daemon is not running. Start Docker Desktop and try again.
    echo.
    pause
    exit /b 1
)

:: ---------------------------------------------------------------------------
:: Start Ollama (local LLM provider used by Chat and AI review).
:: Ollama runs on the Windows HOST, not in Docker; the api container reaches it
:: via host.docker.internal:11434. We start it here on demand so it does not
:: consume CPU/RAM when the project is not running.
:: ---------------------------------------------------------------------------
echo [INFO] Checking Ollama...
curl -s http://localhost:11434/api/tags >nul 2>nul
if not errorlevel 1 goto OLLAMA_OK

set "OLLAMA_EXE="
where ollama >nul 2>nul
if not errorlevel 1 set "OLLAMA_EXE=ollama"
if not defined OLLAMA_EXE if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "OLLAMA_EXE=%LOCALAPPDATA%\Programs\Ollama\ollama.exe"
if not defined OLLAMA_EXE (
    echo [WARN] Ollama not found on this machine.
    echo        Chat / AI review will not work until it is installed.
    echo        Install from: https://ollama.com/download
    goto OLLAMA_DONE
)

echo [INFO] Starting Ollama server...
start "ACA Ollama" /min "%OLLAMA_EXE%" serve

set /a TRIES=0
:WAIT_OLLAMA
timeout /t 2 /nobreak >nul
curl -s http://localhost:11434/api/tags >nul 2>nul
if not errorlevel 1 goto OLLAMA_OK
set /a TRIES+=1
if !TRIES! lss 10 goto WAIT_OLLAMA
echo [WARN] Ollama did not respond in time; Chat may fail until it warms up.
goto OLLAMA_DONE
:OLLAMA_OK
echo [INFO] Ollama is running.
:OLLAMA_DONE

:: ---------------------------------------------------------------------------
:: First-run bootstrap: copy .env.example -> .env if missing.
:: The shipped JWT_SECRET placeholder is 32 chars (passes min_length=16) so
:: the stack will boot. Replace it before exposing this to anyone else.
:: ---------------------------------------------------------------------------
if not exist "%ROOT%.env" (
    echo [INFO] No .env found. Creating from .env.example...
    copy /Y "%ROOT%.env.example" "%ROOT%.env" >nul
    echo [WARN] .env uses the default JWT_SECRET placeholder. Edit .env to change it.
    echo.
)

:: ---------------------------------------------------------------------------
:: Start infrastructure (postgres, redis, qdrant) in the background.
:: These are reused across launches; no separate window needed.
:: ---------------------------------------------------------------------------
echo [INFO] Starting infrastructure (postgres, redis, qdrant)...
docker compose up -d postgres redis qdrant
if errorlevel 1 (
    echo [ERROR] Failed to start infrastructure containers.
    pause
    exit /b 1
)

:: Observability stack (Prometheus + Grafana). Non-fatal if it fails to start.
echo [INFO] Starting observability (prometheus, grafana)...
docker compose up -d prometheus grafana
if errorlevel 1 (
    echo [WARN] Observability stack failed to start; continuing without it.
)

:: Wait up to ~30s for Postgres to report healthy. The api migration won't run
:: until postgres is accepting connections.
echo [INFO] Waiting for Postgres health...
set /a TRIES=0
:WAIT_PG
timeout /t 2 /nobreak >nul
docker compose ps postgres 2>nul | findstr "healthy" >nul
if not errorlevel 1 goto PG_READY
set /a TRIES+=1
if !TRIES! lss 15 goto WAIT_PG
echo [WARN] Postgres health not confirmed yet, continuing anyway...
:PG_READY

:: ---------------------------------------------------------------------------
:: Start Backend window: api + worker (+ flower for Celery monitoring).
:: Logs stream into this window so you can watch requests / tasks live.
:: Closing this window (X or Ctrl+C) stops api/worker/flower.
:: ---------------------------------------------------------------------------
echo [INFO] Starting Backend (api + worker + flower) on port %BACKEND_PORT%...
start "ACA Backend" /d "%ROOT%" cmd /k "docker compose up api worker flower"

:: Wait up to ~60s for the api to answer /health.
echo [INFO] Waiting for backend to be ready...
set /a TRIES=0
:WAIT_API
timeout /t 3 /nobreak >nul
curl -s %BACKEND_URL%/health 2>nul | findstr "ok" >nul
if not errorlevel 1 goto API_READY
set /a TRIES+=1
if !TRIES! lss 20 goto WAIT_API
echo [WARN] Backend not responding on %BACKEND_URL%/health yet.
echo        Check the "ACA Backend" window for errors. Continuing...
:API_READY

:: ---------------------------------------------------------------------------
:: Start Frontend window: Vite dev server inside the web container.
:: First boot does pnpm install -- can take 1-2 min.
:: ---------------------------------------------------------------------------
echo [INFO] Starting Frontend on port %FRONTEND_PORT%...
start "ACA Frontend" /d "%ROOT%" cmd /k "docker compose up web"

:: Give Vite a moment to compile, then open the browser.
echo [INFO] Waiting for frontend to compile...
timeout /t 6 /nobreak >nul
start "" "%FRONTEND_URL%"

:: ---------------------------------------------------------------------------
:: Summary
:: ---------------------------------------------------------------------------
echo.
echo ============================================
echo   AI CODING AGENT IS RUNNING
echo ============================================
echo   Frontend  : %FRONTEND_URL%
echo   API       : %BACKEND_URL%
echo   API docs  : %BACKEND_URL%/docs
echo   Health    : %BACKEND_URL%/health
echo   Qdrant    : http://localhost:6333/dashboard
echo   Flower    : http://localhost:5555
echo   Prometheus: http://localhost:9090
echo   Grafana   : http://localhost:3001  (dashboard: AI Coding Agent - Overview)
echo ============================================
echo.
echo Keep the "ACA Backend" and "ACA Frontend" windows open.
echo Close them (or Ctrl+C in each) to stop the app.
echo.
echo To fully stop EVERYTHING (containers + Ollama) when you are done,
echo run:  Ai_coding_agent_stop.bat
echo  (this frees the CPU/RAM so nothing runs while the project is closed).
echo.
echo Press any key to close this launcher window.
pause >nul
endlocal
