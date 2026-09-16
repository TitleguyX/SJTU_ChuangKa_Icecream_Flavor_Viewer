@echo off
chcp 65001 >nul
title 创咖今日冰淇淋口味
cd /d "%~dp0"

set "SCRIPT=%~dp0icecream_flavor.py"

where py >nul 2>nul
if %errorlevel%==0 goto usepy

where python >nul 2>nul
if %errorlevel%==0 goto usepython

echo.
echo 没有找到 Python，请先安装 Python 3.7 或更高版本：
echo     https://www.python.org/downloads/
echo 安装时请勾选 Add python.exe to PATH。
goto end

:usepy
py "%SCRIPT%" %*
goto end

:usepython
python "%SCRIPT%" %*
goto end

:end
echo.
pause
