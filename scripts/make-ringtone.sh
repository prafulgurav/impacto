#!/usr/bin/env bash
#
# Convert an MP3 (or anything ffmpeg reads) into the two files the apps need:
#
#   android/app/src/main/res/raw/ringtone.mp3   <- Android plays MP3 directly
#   ios/Resources/ringtone.caf                  <- iOS will NOT accept MP3
#
# Usage:
#   scripts/make-ringtone.sh ~/Downloads/my-ring.mp3
#   scripts/make-ringtone.sh ~/Downloads/my-ring.mp3 --android-only
#   scripts/make-ringtone.sh ~/Downloads/my-ring.mp3 --ios-only
#
# Why the iOS conversion is mandatory:
#   UNNotificationSound accepts only .caf / .aiff / .wav, 30 seconds or shorter. Hand it an MP3
#   and iOS silently substitutes the default sound — no error, no warning. That is the single
#   most common cause of "my custom sound doesn't work on iOS".
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

ANDROID_OUT="$ROOT_DIR/android/app/src/main/res/raw/ringtone.mp3"
IOS_OUT="$ROOT_DIR/ios/Resources/ringtone.caf"

# iOS hard limit is 30 s; 29 leaves room for rounding in the encoder.
MAX_SECONDS=29

do_android=1
do_ios=1

usage() {
  sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

[[ $# -ge 1 ]] || usage 1

SOURCE="$1"
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --android-only) do_ios=0 ;;
    --ios-only)     do_android=0 ;;
    -h|--help)      usage 0 ;;
    *) echo "Unknown option: $1" >&2; usage 1 ;;
  esac
  shift
done

if [[ ! -f "$SOURCE" ]]; then
  echo "error: no such file: $SOURCE" >&2
  exit 1
fi

have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------- Android
if [[ $do_android -eq 1 ]]; then
  mkdir -p "$(dirname "$ANDROID_OUT")"
  if have ffmpeg; then
    # Re-encode rather than copy: normalises sample rate and strips album art, which
    # MediaPlayer sometimes chokes on. Mono 128k keeps the file small enough to loop
    # without a gap.
    ffmpeg -hide_banner -loglevel error -y -i "$SOURCE" \
      -vn -ac 1 -ar 44100 -b:a 128k "$ANDROID_OUT"
  else
    echo "note: ffmpeg not found; copying the source file unchanged."
    cp "$SOURCE" "$ANDROID_OUT"
  fi
  echo "android: wrote $ANDROID_OUT"
  echo "         (looped by MediaPlayer, so length does not matter)"
fi

# ---------------------------------------------------------------- iOS
if [[ $do_ios -eq 1 ]]; then
  mkdir -p "$(dirname "$IOS_OUT")"

  if have afconvert; then
    # macOS: afconvert is the tool Apple documents. It cannot read MP3 directly in all
    # versions, so go via an intermediate WAV when ffmpeg is available.
    tmp_wav="$(mktemp -t ringtone).wav"
    trap 'rm -f "$tmp_wav"' EXIT

    if have ffmpeg; then
      ffmpeg -hide_banner -loglevel error -y -i "$SOURCE" \
        -vn -ac 1 -ar 44100 -t "$MAX_SECONDS" -c:a pcm_s16le "$tmp_wav"
    else
      afconvert -f WAVE -d LEI16@44100 -c 1 "$SOURCE" "$tmp_wav"
    fi

    # IMA4 in a CAF container is Apple's recommended notification-sound format.
    afconvert -f caff -d ima4 -c 1 "$tmp_wav" "$IOS_OUT"

  elif have ffmpeg; then
    # Linux / CI: ffmpeg can write CAF directly. Use pcm_s16be, which iOS plays reliably.
    ffmpeg -hide_banner -loglevel error -y -i "$SOURCE" \
      -vn -ac 1 -ar 44100 -t "$MAX_SECONDS" -c:a pcm_s16be -f caf "$IOS_OUT"
  else
    echo "error: need afconvert (macOS) or ffmpeg to produce $IOS_OUT" >&2
    echo "       install ffmpeg:  brew install ffmpeg   |   apt install ffmpeg" >&2
    exit 1
  fi

  echo "ios:     wrote $IOS_OUT"
  echo "         (trimmed to ${MAX_SECONDS}s — iOS rejects notification sounds over 30s)"
  echo "         Make sure it is in the target's Copy Bundle Resources phase."
fi

echo
echo "Done. Rebuild both apps to pick up the new ringtone."
