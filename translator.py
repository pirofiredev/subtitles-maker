from dotenv import load_dotenv
load_dotenv()

import os
import sys
_pyver = f"python{sys.version_info.major}.{sys.version_info.minor}"
_cublas = f"/home/{os.environ.get('USER', 'user')}/.local/lib/{_pyver}/site-packages/nvidia/cublas/lib"
os.environ["LD_LIBRARY_PATH"] = _cublas + ":" + os.environ.get("LD_LIBRARY_PATH", "")

from faster_whisper import WhisperModel
from tqdm import tqdm
from openai import OpenAI


LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:20128/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "cx/gpt-5.6-luna")
LLM_API_KEY = os.getenv("LLM_API_KEY", "local")

client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)


def format_timestamp(seconds):
    milliseconds = int((seconds % 1) * 1000)
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def write_srt(path, entries):
    with open(path, "w", encoding="utf-8") as f:
        for i, entry in enumerate(entries, 1):
            f.write(f"{i}\n{entry['timestamp']}\n{entry['text']}\n\n")


def translate_entries(entries, src, target):
    from concurrent.futures import ThreadPoolExecutor, as_completed
    chunk_size = 60
    chunks = [entries[i:i + chunk_size] for i in range(0, len(entries), chunk_size)]
    translated = [None] * len(chunks)

    def translate_chunk(idx, chunk):
        numbered = "\n".join(f"{j+1}. {e['text']}" for j, e in enumerate(chunk))
        prompt = (
            f"Translate the following subtitle lines from {src} to {target}. "
            f"Return only the translated lines, numbered the same way, no extra text.\n\n"
            f"{numbered}"
        )
        try:
            resp = client.chat.completions.create(
                model=LLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            raw = resp.choices[0].message.content.strip().splitlines()
            result = []
            for line in raw:
                line = line.strip()
                if line and line[0].isdigit() and ". " in line:
                    line = line.split(". ", 1)[1]
                result.append(line)
            while len(result) < len(chunk):
                result.append(chunk[len(result)]["text"])
        except Exception as e:
            print(f"\nTranslation error: {e}, keeping originals for this chunk.")
            result = [e["text"] for e in chunk]
        return idx, [{"timestamp": e["timestamp"], "text": t.strip()} for e, t in zip(chunk, result)]

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(translate_chunk, i, chunk): i for i, chunk in enumerate(chunks)}
        with tqdm(total=len(chunks), desc=f"Translating to {target}") as pbar:
            for fut in as_completed(futures):
                idx, result = fut.result()
                translated[idx] = result
                pbar.update(1)

    return [entry for chunk in translated for entry in chunk]


def main():
    print("=== Subtitle Generator & Translator ===")
    src_lang = input("Film language (pl / ru / auto / other) [default: auto]: ").strip().lower()
    if not src_lang:
        src_lang = "auto"
    whisper_lang = None if src_lang == "auto" else src_lang

    print("\nSubtitle mode:")
    print("  1) Original only")
    print("  2) Bilingual (translation + original in one track)")
    print("  3) Separate tracks (original + translated, selectable in media player)")
    mode = input("Choose [1/2/3, default: 1]: ").strip() or "1"
    if mode not in ("1", "2", "3"):
        print("Invalid choice, defaulting to 1.")
        mode = "1"

    target_lang = None
    if mode in ("2", "3"):
        target_lang = input("Translate to (e.g., ru, pl, en) [default: en]: ").strip().lower()
        if not target_lang:
            target_lang = "en"

    print("\nLoading Whisper large-v3 model (downloading ~3GB on first run, please wait)...")
    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    print("Model loaded.")

    print(f"\nStarting transcription from audio.wav (language: {src_lang.upper()})...")
    segments, info = model.transcribe(
        "audio.wav",
        language=whisper_lang,
        vad_filter=True,
        vad_parameters=dict(
            threshold=0.3,
            min_silence_duration_ms=500,
        ),
    )

    detected_lang = info.language if hasattr(info, "language") else src_lang
    print(f"Audio duration: {int(info.duration)}s (Detected language: {detected_lang})")

    entries = []
    raw_segments = list(segments)  # materialize so we can look ahead
    with tqdm(total=info.duration, unit="sec", desc=f"Transcribing ({detected_lang.upper()})") as progress:
        previous_end = 0
        valid = [(s.start, s.end, s.text.strip()) for s in raw_segments if s.text.strip()]
        for i, (start, end, text) in enumerate(valid):
            # Shift start forward slightly — Whisper tends to be early
            start = start + 0.15
            # Cap end to 10s max display
            end = min(end, start + 10)
            # Don't overlap into next subtitle's start
            if i + 1 < len(valid):
                next_start = valid[i + 1][0] + 0.15
                end = min(end, next_start - 0.05)
            entries.append({
                "index": i + 1,
                "timestamp": f"{format_timestamp(max(0, start))} --> {format_timestamp(end)}",
                "text": text,
            })
            progress.update(max(0, end - previous_end))
            previous_end = end

            previous_end = segment.end

    write_srt("subtitles.srt", entries)
    print("\nSaved base subtitles to 'subtitles.srt'.")

    if mode == "1" or not target_lang:
        return

    translator_src = detected_lang if src_lang == "auto" else src_lang
    print(f"\nTranslating from {translator_src.upper()} to {target_lang.upper()} using {LLM_MODEL}...")
    translated = translate_entries(entries, translator_src, target_lang)

    if mode == "2":
        bilingual = [
            {"timestamp": e["timestamp"], "text": f"{t['text']}\n{e['text']}"}
            for e, t in zip(entries, translated)
        ]
        out = f"subtitles_bilingual_{target_lang}.srt"
        write_srt(out, bilingual)
        print(f"Saved bilingual subtitles to '{out}'.")

    elif mode == "3":
        out_translated = f"subtitles_{target_lang}.srt"
        write_srt(out_translated, translated)
        print(f"Saved original subtitles to 'subtitles.srt'.")
        print(f"Saved translated subtitles to '{out_translated}'.")
        print(f"\nTo embed both as separate tracks, run:")
        print(f"  ./bake_subtitles.sh  → choose mode 3, add subtitles.srt [{translator_src}] and {out_translated} [{target_lang}]")


if __name__ == "__main__":
    main()
