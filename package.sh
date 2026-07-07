#!/usr/bin/env sh
set -eu

usage() {
  cat <<'EOF'
Usage: sh package.sh [options]

Options:
  --backend NAME       auto, pthread, std, boost, win32, single (default: auto)
  --cxx COMMAND        C++ compiler command (default: $CXX or g++)
  --out DIR            Output directory (default: dist/<platform>)
  --name NAME          Executable or library base name (default: javakh_cpp)
  --shared             Build a shared library (.dll, .so, or .dylib)
  --static             Try to link statically where the platform supports it
  --native             Add -march=native when supported (default)
  --no-native          Do not add -march=native
  --portable           Same as --no-native
  --lto                Try -flto
  --no-lto             Do not try -flto (default)
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

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

backend="auto"
cxx="${CXX:-}"
out=""
name="javakh_cpp"
want_static=0
want_shared=0
want_native=1
want_lto=0
want_strip=1
extra_cxxflags="${CXXFLAGS:-}"
extra_ldflags="${LDFLAGS:-}"

while [ "$#" -gt 0 ]; do
  case "$1" in
    --backend) backend="$2"; shift 2 ;;
    --cxx) cxx="$2"; shift 2 ;;
    --out) out="$2"; shift 2 ;;
    --name) name="$2"; shift 2 ;;
    --shared) want_shared=1; shift ;;
    --static) want_static=1; shift ;;
    --native) want_native=1; shift ;;
    --no-native|--portable) want_native=0; shift ;;
    --lto) want_lto=1; shift ;;
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
  Darwin*) platform_id="macos"; exe_ext=""; shared_ext=".dylib" ;;
  Linux*) platform_id="linux"; exe_ext=""; shared_ext=".so" ;;
  MINGW*|MSYS*|CYGWIN*) platform_id="windows"; exe_ext=".exe"; shared_ext=".dll" ;;
  *) platform_id="$(echo "$platform" | tr '[:upper:]' '[:lower:]')"; exe_ext=""; shared_ext=".so" ;;
esac

if [ -z "$out" ]; then
  out="dist/${platform_id}"
fi

mkdir -p "$out"
if [ "$want_shared" -eq 1 ]; then
  if [ "$platform_id" = "windows" ] || [ "${name#lib}" != "$name" ]; then
    target="${out}/${name}${shared_ext}"
  else
    target="${out}/lib${name}${shared_ext}"
  fi
else
  target="${out}/${name}${exe_ext}"
fi

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

compiler_usable() {
  candidate="$1"
  [ -n "$candidate" ] || return 1
  $candidate --version >/dev/null 2>&1 || return 1
  cat > "$tmpdir/test.cpp" <<'EOF'
int main() { return 0; }
EOF
  # shellcheck disable=SC2086
  $candidate -std=c++14 "$tmpdir/test.cpp" -o "$tmpdir/test.bin" >/dev/null 2>&1
}

choose_compiler() {
  if [ -n "$cxx" ]; then
    compiler_usable "$cxx" || {
      echo "C++ compiler '$cxx' is not usable." >&2
      exit 1
    }
    return
  fi

  for candidate in "$script_dir"/../toolchains/winlibs-*/mingw64/bin/g++.exe; do
    if [ -f "$candidate" ] && compiler_usable "$candidate"; then
      cxx="$candidate"
      return
    fi
  done

  for candidate in g++ clang++ c++; do
    if command -v "$candidate" >/dev/null 2>&1 && compiler_usable "$candidate"; then
      cxx="$candidate"
      return
    fi
  done

  echo "No usable C++14 compiler found. Install g++ or pass --cxx <compiler>." >&2
  exit 1
}

backend_supported() {
  candidate="$1"
  case "$candidate" in
    pthread)
      cat > "$tmpdir/test.cpp" <<'EOF'
#include <pthread.h>
int main() { pthread_t t; (void)t; return 0; }
EOF
      # shellcheck disable=SC2086
      $cxx -std=c++14 -DKH_THREAD_BACKEND_PTHREAD "$tmpdir/test.cpp" -o "$tmpdir/test.bin" -pthread >/dev/null 2>&1
      ;;
    std)
      cat > "$tmpdir/test.cpp" <<'EOF'
#include <thread>
int main() { return 0; }
EOF
      # shellcheck disable=SC2086
      $cxx -std=c++14 -DKH_THREAD_BACKEND_STD "$tmpdir/test.cpp" -o "$tmpdir/test.bin" -pthread >/dev/null 2>&1
      ;;
    win32)
      cat > "$tmpdir/test.cpp" <<'EOF'
#include <windows.h>
int main() { CRITICAL_SECTION cs; InitializeCriticalSection(&cs); DeleteCriticalSection(&cs); return 0; }
EOF
      # shellcheck disable=SC2086
      $cxx -std=c++14 -DKH_THREAD_BACKEND_WIN32 "$tmpdir/test.cpp" -o "$tmpdir/test.bin" >/dev/null 2>&1
      ;;
    single)
      cat > "$tmpdir/test.cpp" <<'EOF'
int main() { return 0; }
EOF
      # shellcheck disable=SC2086
      $cxx -std=c++14 -DKH_THREAD_BACKEND_SINGLE "$tmpdir/test.cpp" -o "$tmpdir/test.bin" >/dev/null 2>&1
      ;;
    boost)
      cat > "$tmpdir/test.cpp" <<'EOF'
#include <boost/thread.hpp>
int main() { return 0; }
EOF
      # shellcheck disable=SC2086
      $cxx -std=c++14 -DKH_THREAD_BACKEND_BOOST "$tmpdir/test.cpp" -o "$tmpdir/test.bin" -lboost_thread -lboost_system -pthread >/dev/null 2>&1
      ;;
    *) return 1 ;;
  esac
}

choose_compiler

if [ "$backend" = "auto" ]; then
  case "$platform_id" in
    windows)
      if [ "$want_shared" -eq 1 ]; then
        backend_order="win32 pthread std single"
      else
        backend_order="pthread win32 std single"
      fi
      ;;
    *) backend_order="pthread std single" ;;
  esac
  for candidate in $backend_order; do
    if backend_supported "$candidate"; then
      backend="$candidate"
      break
    fi
  done
  if [ "$backend" = "auto" ]; then
    echo "No supported thread backend found for compiler '$cxx'." >&2
    exit 1
  fi
else
  backend_supported "$backend" || {
    echo "Requested backend '$backend' is not supported by compiler '$cxx'." >&2
    exit 1
  }
fi

cxxflags="-std=c++14 -O3 -DNDEBUG -Isrc"
libs=""
ldflags=""

if [ "$want_shared" -eq 1 ]; then
  cxxflags="$cxxflags -DCPPKH_SHARED_LIBRARY"
  if [ "$platform_id" != "windows" ] && flag_supported "-fPIC"; then
    cxxflags="$cxxflags -fPIC"
  fi
  case "$platform_id" in
    macos) ldflags="$ldflags -dynamiclib" ;;
    *) ldflags="$ldflags -shared" ;;
  esac
fi

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

if [ "$want_static" -eq 1 ]; then
  if [ "$want_shared" -eq 1 ]; then
    echo "warning: --static is ignored when --shared is used" >&2
  else
    case "$platform_id" in
      macos)
        echo "warning: --static is not supported by normal macOS toolchains; ignoring" >&2
      ;;
    *)
      if flag_supported "-static-libstdc++"; then
        ldflags="$ldflags -static-libstdc++"
      fi
      if flag_supported "-static-libgcc"; then
        ldflags="$ldflags -static-libgcc"
      fi
      ldflags="$ldflags -static"
      ;;
    esac
  fi
fi

cxxflags="$cxxflags $extra_cxxflags"
ldflags="$ldflags $extra_ldflags"

dep_basename() {
  basename "$1" | tr '[:upper:]' '[:lower:]'
}

is_system_dependency() {
  dep_spec="$1"
  dep_base="$(dep_basename "$dep_spec")"
  case "$platform_id" in
    windows)
      case "$dep_base" in
        api-ms-*|ext-ms-*|kernel32.dll|user32.dll|gdi32.dll|advapi32.dll|shell32.dll|ole32.dll|oleaut32.dll|ntdll.dll|msvcrt.dll|ucrtbase.dll|vcruntime*.dll|ws2_32.dll|secur32.dll|bcrypt.dll|crypt32.dll|rpcrt4.dll|comdlg32.dll|comctl32.dll|shlwapi.dll|imm32.dll|winmm.dll|version.dll|normaliz.dll)
          return 0
          ;;
      esac
      ;;
    macos)
      case "$dep_spec" in
        /System/Library/*|/usr/lib/*) return 0 ;;
      esac
      [ "$dep_base" = "libsystem.b.dylib" ] && return 0
      ;;
    *)
      case "$dep_base" in
        linux-vdso*|ld-linux*|ld-musl*|libc.so*|libm.so*|libpthread.so*|librt.so*|libdl.so*)
          return 0
          ;;
      esac
      ;;
  esac
  return 1
}

list_runtime_dependencies() {
  dep_file="$1"
  case "$platform_id" in
    windows)
      cxx_path="$(command -v "$cxx" 2>/dev/null || printf '%s' "$cxx")"
      cxx_dir="$(dirname "$cxx_path")"
      objdump_tool=""
      if [ -x "$cxx_dir/objdump.exe" ]; then objdump_tool="$cxx_dir/objdump.exe"
      elif [ -x "$cxx_dir/objdump" ]; then objdump_tool="$cxx_dir/objdump"
      elif command -v objdump.exe >/dev/null 2>&1; then objdump_tool="$(command -v objdump.exe)"
      elif command -v objdump >/dev/null 2>&1; then objdump_tool="$(command -v objdump)"
      fi
      if [ -z "$objdump_tool" ]; then
        echo "warning: objdump was not found; runtime dependencies were not scanned for $dep_file" >&2
        return 0
      fi
      "$objdump_tool" -p "$dep_file" 2>/dev/null | sed -n 's/.*DLL Name:[[:space:]]*//p'
      ;;
    macos)
      if ! command -v otool >/dev/null 2>&1; then
        echo "warning: otool was not found; runtime dependencies were not scanned for $dep_file" >&2
        return 0
      fi
      otool -L "$dep_file" 2>/dev/null | sed '1d' | awk '{print $1}'
      ;;
    *)
      if ! command -v ldd >/dev/null 2>&1; then
        echo "warning: ldd was not found; runtime dependencies were not scanned for $dep_file" >&2
        return 0
      fi
      ldd "$dep_file" 2>/dev/null | sed -n -e 's/.*=>[[:space:]]*\(\/[^ ]*\).*/\1/p' -e 's/^[[:space:]]*\(\/[^ ]*\).*/\1/p'
      ;;
  esac
}

resolve_runtime_dependency() {
  dep_spec="$1"
  if [ -f "$dep_spec" ]; then
    resolve_dir="$(CDPATH= cd -- "$(dirname -- "$dep_spec")" && pwd)"
    printf '%s/%s\n' "$resolve_dir" "$(basename "$dep_spec")"
    return 0
  fi
  dep_name="$(basename "$dep_spec")"
  cxx_path="$(command -v "$cxx" 2>/dev/null || printf '%s' "$cxx")"
  cxx_dir="$(dirname "$cxx_path")"
  for dep_dir in "$out" "$(dirname "$target")" "$cxx_dir"; do
    if [ -n "$dep_dir" ] && [ -f "$dep_dir/$dep_name" ]; then
      resolve_dir="$(CDPATH= cd -- "$dep_dir" && pwd)"
      printf '%s/%s\n' "$resolve_dir" "$dep_name"
      return 0
    fi
  done
  old_ifs="$IFS"
  IFS=:
  for dep_dir in ${PATH:-} ${LD_LIBRARY_PATH:-} ${DYLD_LIBRARY_PATH:-}; do
    if [ -n "$dep_dir" ] && [ -f "$dep_dir/$dep_name" ]; then
      IFS="$old_ifs"
      resolve_dir="$(CDPATH= cd -- "$dep_dir" && pwd)"
      printf '%s/%s\n' "$resolve_dir" "$dep_name"
      return 0
    fi
  done
  IFS="$old_ifs"
  return 1
}

copy_runtime_dependencies() {
  if [ "$want_static" -eq 1 ] && [ "$want_shared" -eq 0 ]; then
    return 0
  fi
  dep_queue="$tmpdir/deps.queue"
  dep_seen="$tmpdir/deps.seen"
  dep_specs="$tmpdir/deps.specs"
  : > "$dep_seen"
  printf '%s\n' "$target" > "$dep_queue"
  dep_copied=0
  while [ -s "$dep_queue" ]; do
    dep_file="$(sed -n '1p' "$dep_queue")"
    sed '1d' "$dep_queue" > "$dep_queue.next"
    mv "$dep_queue.next" "$dep_queue"
    [ -n "$dep_file" ] || continue
    if grep -Fqx "$dep_file" "$dep_seen"; then continue; fi
    printf '%s\n' "$dep_file" >> "$dep_seen"
    list_runtime_dependencies "$dep_file" > "$dep_specs" || true
    while IFS= read -r dep_spec; do
      [ -n "$dep_spec" ] || continue
      if is_system_dependency "$dep_spec"; then continue; fi
      dep_path="$(resolve_runtime_dependency "$dep_spec" 2>/dev/null || true)"
      if [ -z "$dep_path" ]; then
        echo "warning: dependency not found: $dep_spec" >&2
        continue
      fi
      if is_system_dependency "$dep_path"; then continue; fi
      dep_dest="$out/$(basename "$dep_path")"
      dep_src_dir="$(CDPATH= cd -- "$(dirname -- "$dep_path")" && pwd)"
      dep_out_dir="$(CDPATH= cd -- "$out" && pwd)"
      if [ "$dep_src_dir/$(basename "$dep_path")" != "$dep_out_dir/$(basename "$dep_path")" ]; then
        cp -f "$dep_path" "$dep_dest"
        dep_copied=$((dep_copied + 1))
        echo "Copied runtime dependency: $dep_dest"
      fi
      printf '%s\n' "$dep_dest" >> "$dep_queue"
    done < "$dep_specs"
  done
  echo "Runtime dependency scan complete: copied $dep_copied file(s)."
}

echo "Compiler : $cxx"
echo "Platform : $platform_id"
echo "Backend  : $backend"
if [ "$want_shared" -eq 1 ]; then
  echo "Kind     : shared library"
else
  echo "Kind     : executable"
fi
echo "Output   : $target"

# shellcheck disable=SC2086
$cxx $cxxflags src/main.cpp -o "$target" $ldflags $libs

if [ "$want_strip" -eq 1 ] && command -v strip >/dev/null 2>&1; then
  strip "$target" >/dev/null 2>&1 || true
fi

copy_runtime_dependencies

if [ "$want_shared" -eq 1 ]; then
  echo "Packaged shared library: $target"
else
  echo "Packaged executable: $target"
fi
