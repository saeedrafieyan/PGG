@echo off
REM Launch Porous Structure Designer GUI (Windows)
cd /d "%~dp0"
python -m porous_designer.gui.app %*
