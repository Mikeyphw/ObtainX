#!/usr/bin/env bash
# Local unsigned developer build; never changes the repository or signs/publishes.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ $# -gt 1 || ${1:-build} != build ]]; then
  printf '%s\n' 'Usage: ./build.sh [build] (unsigned developer builds only)' >&2
  exit 2
fi
if [[ -e android/key.properties || -L android/key.properties || -e android/app/key.properties || -L android/app/key.properties ]]; then
  printf '%s\n' 'Refusing local build with release signing configuration present.' >&2
  exit 2
fi
flutter pub get --enforce-lockfile
git diff --exit-code -- pubspec.lock
flutter build apk --release --split-per-abi --flavor normal --no-pub
flutter build apk --release --split-per-abi --flavor fdroid -t lib/main_fdroid.dart --no-pub
printf '%s\n' 'Unsigned developer builds only; no release qualification or publication.'
