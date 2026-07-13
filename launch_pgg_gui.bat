@echo off
setlocal
cd /d "%~dp0"
python -m porous_designer.gui.app %*
