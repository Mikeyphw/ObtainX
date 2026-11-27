#!/usr/bin/env bats

setup() {
  root="$BATS_TEST_DIRNAME/../.."
}

@test "legacy signing remains disabled" {
  run bash "$root/sign.sh"
  [ "$status" -eq 2 ]
  [[ "$output" == *"direct legacy signing is disabled"* ]]
}

@test "implicit source sync is refused" {
  run bash "$root/build.sh" sync
  [ "$status" -eq 2 ]
  [[ "$output" == *"unsigned developer builds only"* ]]
}

@test "unsigned developer build refuses release configuration before invoking tooling" {
  sandbox="$BATS_TEST_TMPDIR/project"
  mkdir -p "$sandbox/android/app"
  cp "$root/build.sh" "$sandbox/build.sh"
  touch "$sandbox/android/app/key.properties"
  run bash "$sandbox/build.sh"
  [ "$status" -eq 2 ]
  [[ "$output" == *"release signing configuration present"* ]]
}

@test "unsigned developer build invokes only pinned lock and two unsigned flavors" {
  sandbox="$BATS_TEST_TMPDIR/project"
  mkdir -p "$sandbox/android" "$sandbox/bin"
  cp "$root/build.sh" "$sandbox/build.sh"
  printf '%s\n' '#!/bin/sh' 'printf "flutter %s\n" "$*" >> "$TRACE"' > "$sandbox/bin/flutter"
  printf '%s\n' '#!/bin/sh' 'printf "git %s\n" "$*" >> "$TRACE"' > "$sandbox/bin/git"
  chmod +x "$sandbox/bin/flutter" "$sandbox/bin/git"
  export TRACE="$sandbox/trace" PATH="$sandbox/bin:$PATH"
  run bash "$sandbox/build.sh"
  [ "$status" -eq 0 ]
  [ "$(cat "$TRACE")" = "$(printf '%s\n' 'flutter pub get --enforce-lockfile' 'git diff --exit-code -- pubspec.lock' 'flutter build apk --release --split-per-abi --flavor normal --no-pub' 'flutter build apk --release --split-per-abi --flavor fdroid -t lib/main_fdroid.dart --no-pub')" ]
}
