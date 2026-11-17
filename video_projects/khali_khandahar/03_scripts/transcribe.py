"""Transcribe the source audio (Hindi) with faster-whisper; writes JSON with word timings."""
import sys, json, wave
import numpy as np
from faster_whisper import WhisperModel
src, out, model = sys.argv[1], sys.argv[2], (sys.argv[3] if len(sys.argv) > 3 else "medium")
w = wave.open(src); audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0
m = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=4)
segs, info = m.transcribe(audio, language="hi", word_timestamps=True, vad_filter=True,
                          beam_size=1, condition_on_previous_text=False, temperature=0.0)
res = {"language": info.language, "model": model, "segments": []}
for s in segs:
    res["segments"].append({"start": s.start, "end": s.end, "text": s.text.strip(), "avg_logprob": s.avg_logprob,
        "no_speech_prob": s.no_speech_prob,
        "words": [{"start": x.start, "end": x.end, "word": x.word, "p": x.probability} for x in (s.words or [])]})
    print(f"[{s.start:7.2f}-{s.end:7.2f}] ({s.avg_logprob:.2f}) {s.text.strip()}", flush=True)
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
