# Sunny Sir vs KD Sir — cricket rivalry edit

- `source/source_original.mp4` — untouched copy of the upload (read-only, not in git)
- `scripts/timeline.py` — edit decision list (cuts, speeds, zooms; 120 BPM beat grid)
- `scripts/render_video.py` — grade, speed ramps, zooms, flashes, broadcast graphics
- `scripts/make_audio.py` — conformed original audio + synthesized music and SFX
- `scripts/build.sh` — full rebuild into `export/Final_Edited_Cricket_Rivalry.mp4`
- `assets/` — Anton and Bebas Neue fonts (SIL Open Font License)

Requires ffmpeg, Python 3 with numpy, scipy and Pillow. Run `./scripts/build.sh`.
