# Rebuild pipeline
Needs: python3, numpy, scipy, pillow, ffmpeg; fonts Anton, Oswald, Yellowtail (Google Fonts) in `fonts/`.
1. `python3 gen.py img` downloads the keyframes (already in `keyframes/`; copy them to `img/`).
2. `python3 audio.py mix.wav` synthesises the original phonk score + SFX on the shared beat grid (`timeline.py`).
3. `python3 render.py video_noaudio.mp4` renders 1140 frames (camera moves, motion blur, grade, FX, titles).
4. Mux: `ffmpeg -i video_noaudio.mp4 -i mix.wav -c:v libx264 -b:v 14M -c:a aac -b:a 256k -movflags +faststart out.mp4`
5. `python3 thumb.py` builds the thumbnails.
