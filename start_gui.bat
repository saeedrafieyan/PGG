@echo off
setlocal EnableExtensions
REM Launch PGG, Porous Geometry Generation GUI (Windows).
REM Prefer a project-local virtual environment, allow PGG_PYTHON override,
REM and keep the console open on errors when double-clicked.

cd /d "%~dp0"

if not defined PGG_PYTHON (
    if exist "%CD%\.venv\Scripts\python.exe" set "PGG_PYTHON=%CD%\.venv\Scripts\python.exe"
)
if not defined PGG_PYTHON (
    if exist "%CD%\venv\Scripts\python.exe" set "PGG_PYTHON=%CD%\venv\Scripts\python.exe"
)
if not defined PGG_PYTHON (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        set "PGG_PYTHON=%%P"
        goto :python_found
    )
)

:python_found
if not defined PGG_PYTHON (
    echo [PGG] Python was not found.
    echo [PGG] Install Python 3.11+ or create a project environment, then run:
    echo       python -m pip install -e ".[gui]"
    goto :fail
)

if exist "%CD%\src" (
    set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
)

echo [PGG] Using Python: %PGG_PYTHON%
"%PGG_PYTHON%" -c "import sys; assert sys.version_info >= (3, 11), sys.version; import porous_designer; import PySide6" >nul 2>nul
if errorlevel 1 (
    echo [PGG] The selected Python cannot import PGG and its GUI dependencies.
    echo [PGG] From this folder, install the project GUI dependencies:
    echo       "%PGG_PYTHON%" -m pip install -e ".[gui]"
    echo.
    echo [PGG] If you use a virtual environment, create/activate it first or set:
    echo       set PGG_PYTHON=E:\path\to\venv\Scripts\python.exe
    goto :fail
)

"%PGG_PYTHON%" -m porous_designer.gui.app %*
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo [PGG] GUI launch failed.
if /i not "%PGG_NO_PAUSE%"=="1" pause
exit /b 1
