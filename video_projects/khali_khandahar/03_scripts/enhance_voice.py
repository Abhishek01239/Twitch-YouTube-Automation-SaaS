"""Speech enhancement of the whole source soundtrack (non-stationary spectral gating, noisereduce).

Usage: python3 enhance_voice.py <input.wav> <output.wav> [prop_decrease]
prop_decrease < 1 keeps a little of the natural ambience (horror atmosphere) and avoids the
watery artefacts of full suppression. Processing is chunked (60 s, with overlap context).
Further voice EQ / de-essing / levelling happens per clip in render.py.
"""
import sys, wave
import numpy as np
import noisereduce as nr

src, dst = sys.argv[1], sys.argv[2]
prop = float(sys.argv[3]) if len(sys.argv) > 3 else 0.8
w = wave.open(src); sr = w.getframerate(); ch = w.getnchannels()
x = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
x = x.reshape(-1, ch).mean(axis=1)  # phone audio is effectively mono
CH, PAD = sr * 60, sr * 2
out = np.zeros_like(x)
for s in range(0, len(x), CH):
    a, b = max(0, s - PAD), min(len(x), s + CH + PAD)
    y = nr.reduce_noise(y=x[a:b], sr=sr, stationary=False, prop_decrease=prop,
                        time_constant_s=2.0, freq_mask_smooth_hz=500, time_mask_smooth_ms=50, n_jobs=4)
    n = min(CH, len(x) - s)
    out[s:s + n] = y[s - a: s - a + n]
    print(f"  {(s + n) / sr:7.1f}s / {len(x) / sr:.1f}s", flush=True)
y = np.clip(np.stack([out, out], axis=1), -1, 1)
o = wave.open(dst, "wb"); o.setnchannels(2); o.setsampwidth(2); o.setframerate(sr)
o.writeframes((y * 32767).astype(np.int16).tobytes()); o.close()
print("wrote", dst)
