@echo off
setlocal EnableExtensions

set "BACKEND=auto"
set "CXX=%CXX%"
set "OUT="
set "NAME=javakh_cpp"
set "WANT_SHARED=0"
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
if /I "%~1"=="--shared" set "WANT_SHARED=1" & shift & goto parse
if /I "%~1"=="--static" set "WANT_STATIC=1" & shift & goto parse
if /I "%~1"=="--native" set "WANT_NATIVE=1" & shift & goto parse
if /I "%~1"=="--no-native" set "WANT_NATIVE=0" & shift & goto parse
if /I "%~1"=="--portable" set "WANT_NATIVE=0" & shift & goto parse
if /I "%~1"=="--lto" set "WANT_LTO=1" & shift & goto parse
if /I "%~1"=="--no-lto" set "WANT_LTO=0" & shift & goto parse
if /I "%~1"=="--no-strip" set "WANT_STRIP=0" & shift & goto parse
if /I "%~1"=="--extra-cxxflags" set "EXTRA_CXXFLAGS=%EXTRA_CXXFLAGS% %~2" & shift & shift & goto parse
if /I "%~1"=="--extra-ldflags" set "EXTRA_LDFLAGS=%EXTRA_LDFLAGS% %~2" & shift & shift & goto parse
if /I "%~1"=="--help" goto help
if /I "%~1"=="-h" goto help
echo Unknown option: %~1
goto help_error

:parsed
if "%CXX%"=="" (
  call :choose_cxx
  if errorlevel 1 exit /b %errorlevel%
) else (
  call :test_compiler
  if errorlevel 1 (
    echo C++ compiler "%CXX%" is not usable.
    exit /b 1
  )
)

if /I "%BACKEND%"=="auto" (
  call :choose_backend
  if errorlevel 1 exit /b %errorlevel%
) else (
  call :test_backend "%BACKEND%"
  if errorlevel 1 (
    echo Requested backend "%BACKEND%" is not supported by compiler "%CXX%".
    exit /b 1
  )
)

if "%OUT%"=="" set "OUT=dist\windows"
if not exist "%OUT%" mkdir "%OUT%"
if "%WANT_SHARED%"=="1" (
  set "TARGET=%OUT%\%NAME%.dll"
) else (
  set "TARGET=%OUT%\%NAME%.exe"
)

set "CXXFLAGS_ALL=-std=c++14 -O3 -DNDEBUG -Isrc"
set "LIBS="
set "LDFLAGS_ALL="

if "%WANT_SHARED%"=="1" (
  set "CXXFLAGS_ALL=%CXXFLAGS_ALL% -DCPPKH_SHARED_LIBRARY"
  set "LDFLAGS_ALL=%LDFLAGS_ALL% -shared"
)

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

if "%WANT_STATIC%"=="1" (
  if "%WANT_SHARED%"=="1" (
    echo Warning: --static is ignored when --shared is used.
  ) else (
    call :test_flag -static-libstdc++
    if not errorlevel 1 set "LDFLAGS_ALL=%LDFLAGS_ALL% -static-libstdc++"
    call :test_flag -static-libgcc
    if not errorlevel 1 set "LDFLAGS_ALL=%LDFLAGS_ALL% -static-libgcc"
    set "LDFLAGS_ALL=%LDFLAGS_ALL% -static"
  )
)

set "CXXFLAGS_ALL=%CXXFLAGS_ALL% %EXTRA_CXXFLAGS%"
set "LDFLAGS_ALL=%LDFLAGS_ALL% %EXTRA_LDFLAGS%"

echo Compiler : %CXX%
echo Platform : windows
echo Backend  : %BACKEND%
if "%WANT_SHARED%"=="1" (echo Kind     : shared library) else (echo Kind     : executable)
echo Output   : %TARGET%

%CXX% %CXXFLAGS_ALL% src\main.cpp -o "%TARGET%" %LDFLAGS_ALL% %LIBS%
if errorlevel 1 exit /b %errorlevel%

if "%WANT_STRIP%"=="1" (
  where strip >nul 2>nul
  if not errorlevel 1 strip "%TARGET%" >nul 2>nul
)

if "%WANT_SHARED%"=="1" (
  call :copy_runtime_deps
)
if "%WANT_SHARED%"=="0" if "%WANT_STATIC%"=="0" (
  call :copy_runtime_deps
)

if "%WANT_SHARED%"=="1" (
  echo Packaged shared library: %TARGET%
) else (
  echo Packaged executable: %TARGET%
)
exit /b 0

:copy_runtime_deps
where powershell >nul 2>nul
if errorlevel 1 (
  echo Warning: powershell was not found; runtime dependencies were not copied.
  exit /b 0
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\copy_runtime_deps.ps1" -Target "%TARGET%" -Out "%OUT%" -Compiler "%CXX%"
exit /b 0

:choose_cxx
for /d %%D in ("%~dp0..\toolchains\winlibs-*") do (
  if exist "%%~fD\mingw64\bin\g++.exe" (
    set "CXX=%%~fD\mingw64\bin\g++.exe"
    call :test_compiler
    if not errorlevel 1 exit /b 0
  )
)
for %%G in (g++.exe clang++.exe c++.exe) do (
  where %%G >nul 2>nul
  if not errorlevel 1 (
    set "CXX=%%G"
    call :test_compiler
    if not errorlevel 1 exit /b 0
  )
)
echo No usable C++14 compiler found. Install g++ or pass --cxx.
exit /b 1

:choose_backend
if "%WANT_SHARED%"=="1" (
  call :test_backend win32
  if not errorlevel 1 set "BACKEND=win32" & exit /b 0
)
call :test_backend pthread
if not errorlevel 1 set "BACKEND=pthread" & exit /b 0
call :test_backend win32
if not errorlevel 1 set "BACKEND=win32" & exit /b 0
call :test_backend std
if not errorlevel 1 set "BACKEND=std" & exit /b 0
call :test_backend single
if not errorlevel 1 set "BACKEND=single" & exit /b 0
echo No supported thread backend found for compiler "%CXX%".
exit /b 1

:test_compiler
%CXX% --version >nul 2>nul
if errorlevel 1 exit /b 1
call :test_flag
exit /b %ERRORLEVEL%

:test_backend
set "PKG_BACKEND=%~1"
set "PKG_TMP=%TEMP%\javakh_cpp_backend_%RANDOM%.cpp"
set "PKG_EXE=%TEMP%\javakh_cpp_backend_%RANDOM%.exe"
if /I "%PKG_BACKEND%"=="pthread" (
  echo #include ^<pthread.h^>>"%PKG_TMP%"
  echo int main^(^){return 0;}>>"%PKG_TMP%"
  %CXX% -std=c++14 -DKH_THREAD_BACKEND_PTHREAD "%PKG_TMP%" -o "%PKG_EXE%" -pthread >nul 2>nul
) else if /I "%PKG_BACKEND%"=="win32" (
  echo #include ^<windows.h^>>"%PKG_TMP%"
  echo int main^(^){return 0;}>>"%PKG_TMP%"
  %CXX% -std=c++14 -DKH_THREAD_BACKEND_WIN32 "%PKG_TMP%" -o "%PKG_EXE%" >nul 2>nul
) else if /I "%PKG_BACKEND%"=="std" (
  echo #include ^<thread^>>"%PKG_TMP%"
  echo int main^(^){return 0;}>>"%PKG_TMP%"
  %CXX% -std=c++14 -DKH_THREAD_BACKEND_STD "%PKG_TMP%" -o "%PKG_EXE%" >nul 2>nul
) else if /I "%PKG_BACKEND%"=="boost" (
  echo #include ^<boost/thread.hpp^>>"%PKG_TMP%"
  echo int main^(^){return 0;}>>"%PKG_TMP%"
  %CXX% -std=c++14 -DKH_THREAD_BACKEND_BOOST "%PKG_TMP%" -o "%PKG_EXE%" -lboost_thread -lboost_system >nul 2>nul
) else if /I "%PKG_BACKEND%"=="single" (
  echo int main^(^){return 0;}>"%PKG_TMP%"
  %CXX% -std=c++14 -DKH_THREAD_BACKEND_SINGLE "%PKG_TMP%" -o "%PKG_EXE%" >nul 2>nul
) else (
  del "%PKG_TMP%" >nul 2>nul
  exit /b 1
)
set "PKG_RC=%ERRORLEVEL%"
del "%PKG_TMP%" >nul 2>nul
del "%PKG_EXE%" >nul 2>nul
exit /b %PKG_RC%

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
echo   --name NAME          Executable or library base name ^(default: javakh_cpp^)
echo   --shared             Build a .dll shared library instead of an executable
echo   --static             Try static linking
echo   --native             Add -march=native if supported ^(default^)
echo   --no-native          Do not add -march=native
echo   --portable           Same as --no-native
echo   --lto                Try -flto ^(default^)
echo   --no-lto             Do not try -flto
echo   --no-strip           Do not strip symbols
echo   --extra-cxxflags X   Append extra compiler flags
echo   --extra-ldflags X    Append extra linker flags
echo   -h, --help           Show this help
exit /b 0

:help_error
call :help
exit /b 2
