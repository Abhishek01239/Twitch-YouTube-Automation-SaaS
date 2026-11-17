#!/usr/bin/env bash
# Full rebuild: video pass -> audio pass -> loudness-normalised mux.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p work export
python3 scripts/render_video.py work/video_only.mp4
python3 scripts/make_audio.py work/premix.wav
ffmpeg -v error -y -i work/video_only.mp4 -i work/premix.wav \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000" \
  -c:v copy -c:a aac -b:a 256k -shortest -movflags +faststart \
  export/Final_Edited_Cricket_Rivalry.mp4
