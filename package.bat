@echo off
setlocal EnableExtensions

set "BACKEND=auto"
set "CXX=%CXX%"
if "%CXX%"=="" set "CXX=g++"
set "OUT="
set "NAME=javakh_cpp"
set "WANT_STATIC=0"
set "WANT_NATIVE=1"
set "WANT_LTO=1"
set "WANT_STRIP=1"
set "EXTRA_CXXFLAGS=%CXXFLAGS%"
set "EXTRA_LDFLAGS=%LDFLAGS%"

:parse
if "%~1"=="" goto parsed
if /I "%~1"=="--backend" set "BACKEND=%~2" & shift & shift & goto parse
if /I "%~1"=="--cxx" set "CXX=%~2" & shift & shift & goto parse
if /I "%~1"=="--out" set "OUT=%~2" & shift & shift & goto parse
if /I "%~1"=="--name" set "NAME=%~2" & shift & shift & goto parse
if /I "%~1"=="--static" set "WANT_STATIC=1" & shift & goto parse
if /I "%~1"=="--native" set "WANT_NATIVE=1" & shift & goto parse
if /I "%~1"=="--no-native" set "WANT_NATIVE=0" & shift & goto parse
if /I "%~1"=="--portable" set "WANT_NATIVE=0" & shift & goto parse
if /I "%~1"=="--no-lto" set "WANT_LTO=0" & shift & goto parse
if /I "%~1"=="--no-strip" set "WANT_STRIP=0" & shift & goto parse
if /I "%~1"=="--extra-cxxflags" set "EXTRA_CXXFLAGS=%EXTRA_CXXFLAGS% %~2" & shift & shift & goto parse
if /I "%~1"=="--extra-ldflags" set "EXTRA_LDFLAGS=%EXTRA_LDFLAGS% %~2" & shift & shift & goto parse
if /I "%~1"=="--help" goto help
if /I "%~1"=="-h" goto help
echo Unknown option: %~1
goto help_error

:parsed
if /I "%BACKEND%"=="auto" set "BACKEND=win32"
if "%OUT%"=="" set "OUT=dist\windows"
if not exist "%OUT%" mkdir "%OUT%"
set "TARGET=%OUT%\%NAME%.exe"

set "CXXFLAGS_ALL=-std=c++14 -O3 -DNDEBUG -Isrc"
set "LIBS="
set "LDFLAGS_ALL="

if /I "%BACKEND%"=="win32" (
  set "CXXFLAGS_ALL=%CXXFLAGS_ALL% -DKH_THREAD_BACKEND_WIN32"
) else if /I "%BACKEND%"=="pthread" (
  set "CXXFLAGS_ALL=%CXXFLAGS_ALL% -DKH_THREAD_BACKEND_PTHREAD"
  set "LIBS=%LIBS% -pthread"
) else if /I "%BACKEND%"=="std" (
  set "CXXFLAGS_ALL=%CXXFLAGS_ALL% -DKH_THREAD_BACKEND_STD"
) else if /I "%BACKEND%"=="boost" (
  set "CXXFLAGS_ALL=%CXXFLAGS_ALL% -DKH_THREAD_BACKEND_BOOST"
  set "LIBS=%LIBS% -lboost_thread -lboost_system"
) else if /I "%BACKEND%"=="single" (
  set "CXXFLAGS_ALL=%CXXFLAGS_ALL% -DKH_THREAD_BACKEND_SINGLE"
) else (
  echo Unknown backend "%BACKEND%".
  echo Choose: auto, win32, pthread, std, boost, single
  exit /b 2
)

if "%WANT_LTO%"=="1" (
  call :test_flag -flto
  if not errorlevel 1 (
    set "CXXFLAGS_ALL=%CXXFLAGS_ALL% -flto"
    set "LDFLAGS_ALL=%LDFLAGS_ALL% -flto"
  )
)

if "%WANT_NATIVE%"=="1" (
  call :test_flag -march=native
  if not errorlevel 1 set "CXXFLAGS_ALL=%CXXFLAGS_ALL% -march=native"
)

call :test_flag -static-libstdc++
if not errorlevel 1 set "LDFLAGS_ALL=%LDFLAGS_ALL% -static-libstdc++"

call :test_flag -static-libgcc
if not errorlevel 1 set "LDFLAGS_ALL=%LDFLAGS_ALL% -static-libgcc"

if "%WANT_STATIC%"=="1" set "LDFLAGS_ALL=%LDFLAGS_ALL% -static"

set "CXXFLAGS_ALL=%CXXFLAGS_ALL% %EXTRA_CXXFLAGS%"
set "LDFLAGS_ALL=%LDFLAGS_ALL% %EXTRA_LDFLAGS%"

echo Compiler : %CXX%
echo Platform : windows
echo Backend  : %BACKEND%
echo Output   : %TARGET%

%CXX% %CXXFLAGS_ALL% src\main.cpp -o "%TARGET%" %LDFLAGS_ALL% %LIBS%
if errorlevel 1 exit /b %errorlevel%

if "%WANT_STRIP%"=="1" (
  where strip >nul 2>nul
  if not errorlevel 1 strip "%TARGET%" >nul 2>nul
)

echo Packaged single executable: %TARGET%
exit /b 0

:test_flag
set "PKG_TMP=%TEMP%\javakh_cpp_flag_%RANDOM%.cpp"
set "PKG_EXE=%TEMP%\javakh_cpp_flag_%RANDOM%.exe"
echo int main(){return 0;}>"%PKG_TMP%"
%CXX% -std=c++14 %~1 "%PKG_TMP%" -o "%PKG_EXE%" >nul 2>nul
set "PKG_RC=%ERRORLEVEL%"
del "%PKG_TMP%" >nul 2>nul
del "%PKG_EXE%" >nul 2>nul
exit /b %PKG_RC%

:help
echo Usage: package.bat [options]
echo.
echo Options:
echo   --backend NAME       auto, win32, pthread, std, boost, single ^(default: auto^)
echo   --cxx COMMAND        C++ compiler command ^(default: %%CXX%% or g++^)
echo   --out DIR            Output directory ^(default: dist\windows^)
echo   --name NAME          Executable base name ^(default: javakh_cpp^)
echo   --static             Try static linking
echo   --native             Add -march=native if supported ^(default^)
echo   --no-native          Do not add -march=native
echo   --portable           Same as --no-native
echo   --no-lto             Do not try -flto
echo   --no-strip           Do not strip symbols
echo   --extra-cxxflags X   Append extra compiler flags
echo   --extra-ldflags X    Append extra linker flags
echo   -h, --help           Show this help
exit /b 0

:help_error
call :help
exit /b 2
