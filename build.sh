#!/usr/bin/env sh
set -eu

script_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

args="--out build --no-strip"
if [ "$#" -gt 0 ]; then
  case "$1" in
    auto|pthread|std|boost|win32|single)
      args="$args --backend $1"
      shift
      ;;
  esac
fi

# shellcheck disable=SC2086
sh "$script_dir/package.sh" $args "$@"
