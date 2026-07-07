@echo off
setlocal EnableExtensions

set "ARGS=--out build --no-strip"

if "%~1"=="" goto run
if /I "%~1"=="auto" set "ARGS=%ARGS% --backend auto" & shift & goto append
if /I "%~1"=="win32" set "ARGS=%ARGS% --backend win32" & shift & goto append
if /I "%~1"=="pthread" set "ARGS=%ARGS% --backend pthread" & shift & goto append
if /I "%~1"=="std" set "ARGS=%ARGS% --backend std" & shift & goto append
if /I "%~1"=="boost" set "ARGS=%ARGS% --backend boost" & shift & goto append
if /I "%~1"=="single" set "ARGS=%ARGS% --backend single" & shift & goto append

:append
if "%~1"=="" goto run
set "ARGS=%ARGS% %1"
shift
goto append

:run
call "%~dp0package.bat" %ARGS%
exit /b %ERRORLEVEL%
