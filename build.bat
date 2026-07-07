@echo off
setlocal

set BACKEND=%1
if "%BACKEND%"=="" set BACKEND=win32

set CXX=g++
set CXXFLAGS=-std=c++14 -O3 -DNDEBUG -Isrc
set LIBS=

if /I "%BACKEND%"=="win32" (
  set CXXFLAGS=%CXXFLAGS% -DKH_THREAD_BACKEND_WIN32
) else if /I "%BACKEND%"=="pthread" (
  set CXXFLAGS=%CXXFLAGS% -DKH_THREAD_BACKEND_PTHREAD
  set LIBS=-pthread
) else if /I "%BACKEND%"=="std" (
  set CXXFLAGS=%CXXFLAGS% -DKH_THREAD_BACKEND_STD
) else if /I "%BACKEND%"=="boost" (
  set CXXFLAGS=%CXXFLAGS% -DKH_THREAD_BACKEND_BOOST
  set LIBS=-lboost_thread -lboost_system
) else if /I "%BACKEND%"=="single" (
  set CXXFLAGS=%CXXFLAGS% -DKH_THREAD_BACKEND_SINGLE
) else (
  echo Unknown backend "%BACKEND%".
  echo Choose one of: win32, pthread, std, boost, single
  exit /b 2
)

if not exist build mkdir build
%CXX% %CXXFLAGS% src\main.cpp -o build\javakh_cpp.exe %LIBS%
if errorlevel 1 exit /b %errorlevel%
echo Built build\javakh_cpp.exe with %BACKEND% threading
