#!/usr/bin/env sh
set -eu

backend="${1:-pthread}"
cxx="${CXX:-g++}"
cxxflags="-std=c++14 -O3 -DNDEBUG -Isrc"
libs=""

case "$backend" in
  pthread)
    cxxflags="$cxxflags -DKH_THREAD_BACKEND_PTHREAD"
    libs="-pthread"
    ;;
  std)
    cxxflags="$cxxflags -DKH_THREAD_BACKEND_STD"
    libs="-pthread"
    ;;
  boost)
    cxxflags="$cxxflags -DKH_THREAD_BACKEND_BOOST"
    libs="-lboost_thread -lboost_system -pthread"
    ;;
  win32)
    cxxflags="$cxxflags -DKH_THREAD_BACKEND_WIN32"
    ;;
  single)
    cxxflags="$cxxflags -DKH_THREAD_BACKEND_SINGLE"
    ;;
  *)
    echo "Unknown backend '$backend'. Choose: pthread, std, boost, win32, single" >&2
    exit 2
    ;;
esac

mkdir -p build
$cxx $cxxflags src/main.cpp -o build/javakh_cpp $libs
echo "Built build/javakh_cpp with $backend threading"
