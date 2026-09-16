@echo off
chcp 65001 >nul
python "%~dp0ice_cream_flavor.py" %*
echo.
pause

