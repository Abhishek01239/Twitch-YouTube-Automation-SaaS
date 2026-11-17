"""Per-second loudness profile + peak detection (screams, impacts) from the source audio."""
import sys, wave, numpy as np
w = wave.open(sys.argv[1]); sr = w.getframerate()
a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768
hop = sr // 2
rms = np.array([np.sqrt(np.mean(a[i:i+hop]**2)) + 1e-9 for i in range(0, len(a) - hop, hop)])
db = 20 * np.log10(rms)
with open(sys.argv[2], "w") as f:
    for i, d in enumerate(db): f.write(f"{i*0.5:.1f}\t{d:.1f}\n")
print("median dB", np.median(db).round(1))
# per-minute mean
for m in range(0, len(db)//120 + 1):
    seg = db[m*120:(m+1)*120]
    print(f"min {m:2d}: mean {seg.mean():6.1f}  max {seg.max():6.1f}  silent% {(seg < -40).mean()*100:4.0f}")
top = np.argsort(db)[::-1]
picked = []
for i in top:
    if all(abs(i - j) > 6 for j in picked): picked.append(i)
    if len(picked) == 25: break
print("loudest moments:", sorted(f"{p*0.5:.1f}" for p in picked))
