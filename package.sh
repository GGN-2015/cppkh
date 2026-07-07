#!/usr/bin/env sh
set -eu

usage() {
  cat <<'EOF'
Usage: sh package.sh [options]

Options:
  --backend NAME       auto, pthread, std, boost, win32, single (default: auto)
  --cxx COMMAND        C++ compiler command (default: $CXX or g++)
  --out DIR            Output directory (default: dist/<platform>)
  --name NAME          Executable base name (default: javakh_cpp)
  --static             Try to link statically where the platform supports it
  --native             Add -march=native when supported (default)
  --no-native          Do not add -march=native
  --portable           Same as --no-native
  --no-lto             Do not try -flto
  --no-strip           Do not strip symbols from the final executable
  --extra-cxxflags X   Append extra compiler flags
  --extra-ldflags X    Append extra linker flags
  -h, --help           Show this help

Environment:
  CXX                  C++ compiler command, overridden by --cxx
  CXXFLAGS             Additional compiler flags
  LDFLAGS              Additional linker flags
EOF
}

backend="auto"
cxx="${CXX:-g++}"
out=""
name="javakh_cpp"
want_static=0
want_native=1
want_lto=1
want_strip=1
extra_cxxflags="${CXXFLAGS:-}"
extra_ldflags="${LDFLAGS:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backend) backend="$2"; shift 2 ;;
    --cxx) cxx="$2"; shift 2 ;;
    --out) out="$2"; shift 2 ;;
    --name) name="$2"; shift 2 ;;
    --static) want_static=1; shift ;;
    --native) want_native=1; shift ;;
    --no-native|--portable) want_native=0; shift ;;
    --no-lto) want_lto=0; shift ;;
    --no-strip) want_strip=0; shift ;;
    --extra-cxxflags) extra_cxxflags="${extra_cxxflags} $2"; shift 2 ;;
    --extra-ldflags) extra_ldflags="${extra_ldflags} $2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

platform="$(uname -s 2>/dev/null || echo unknown)"
case "$platform" in
  Darwin*) platform_id="macos"; exe_ext="" ;;
  Linux*) platform_id="linux"; exe_ext="" ;;
  MINGW*|MSYS*|CYGWIN*) platform_id="windows"; exe_ext=".exe" ;;
  *) platform_id="$(echo "$platform" | tr '[:upper:]' '[:lower:]')"; exe_ext="" ;;
esac

if [ "$backend" = "auto" ]; then
  case "$platform_id" in
    windows) backend="win32" ;;
    *) backend="pthread" ;;
  esac
fi

if [ -z "$out" ]; then
  out="dist/${platform_id}"
fi

mkdir -p "$out"
target="${out}/${name}${exe_ext}"

tmpdir="${TMPDIR:-/tmp}/javakh_cpp_pkg_$$"
mkdir -p "$tmpdir"
trap 'rm -rf "$tmpdir"' EXIT INT TERM

flag_supported() {
  flag="$1"
  cat > "$tmpdir/test.cpp" <<'EOF'
int main() { return 0; }
EOF
  # shellcheck disable=SC2086
  $cxx -std=c++14 $flag "$tmpdir/test.cpp" -o "$tmpdir/test.bin" >/dev/null 2>&1
}

cxxflags="-std=c++14 -O3 -DNDEBUG -Isrc"
libs=""
ldflags=""

case "$backend" in
  pthread)
    cxxflags="$cxxflags -DKH_THREAD_BACKEND_PTHREAD"
    libs="$libs -pthread"
    ;;
  std)
    cxxflags="$cxxflags -DKH_THREAD_BACKEND_STD"
    libs="$libs -pthread"
    ;;
  boost)
    cxxflags="$cxxflags -DKH_THREAD_BACKEND_BOOST"
    libs="$libs -lboost_thread -lboost_system -pthread"
    ;;
  win32)
    cxxflags="$cxxflags -DKH_THREAD_BACKEND_WIN32"
    ;;
  single)
    cxxflags="$cxxflags -DKH_THREAD_BACKEND_SINGLE"
    ;;
  *)
    echo "Unknown backend '$backend'. Choose: auto, pthread, std, boost, win32, single" >&2
    exit 2
    ;;
esac

if [ "$want_lto" -eq 1 ] && flag_supported "-flto"; then
  cxxflags="$cxxflags -flto"
  ldflags="$ldflags -flto"
fi

if [ "$want_native" -eq 1 ] && flag_supported "-march=native"; then
  cxxflags="$cxxflags -march=native"
fi

if flag_supported "-static-libstdc++"; then
  ldflags="$ldflags -static-libstdc++"
fi

if flag_supported "-static-libgcc"; then
  ldflags="$ldflags -static-libgcc"
fi

if [ "$want_static" -eq 1 ]; then
  case "$platform_id" in
    macos)
      echo "warning: --static is not supported by normal macOS toolchains; ignoring" >&2
      ;;
    *)
      ldflags="$ldflags -static"
      ;;
  esac
fi

cxxflags="$cxxflags $extra_cxxflags"
ldflags="$ldflags $extra_ldflags"

echo "Compiler : $cxx"
echo "Platform : $platform_id"
echo "Backend  : $backend"
echo "Output   : $target"

# shellcheck disable=SC2086
$cxx $cxxflags src/main.cpp -o "$target" $ldflags $libs

if [ "$want_strip" -eq 1 ] && command -v strip >/dev/null 2>&1; then
  strip "$target" >/dev/null 2>&1 || true
fi

echo "Packaged single executable: $target"
