# Film Subtitle & Translation Tools

Automatic transcription, subtitle generation, and translation pipeline using whisper model and a local LLM endpoint. **Tested on fedora (could possibly not work on other distros / OS)**

## Requirements

- Python 3.10+
- FFmpeg
- NVIDIA GPU with CUDA (16GB VRAM recommended for large-v3)
- A running **local LLM endpoint** (OpenAI-compatible) for translation.
  - Such as: [9router](https://github.com/decolua/9router), [omniroute](https://github.com/diegosouzapw/OmniRoute), or from any other provider.

### Python Dependencies

```bash
pip install -r requirements.txt
```

## Setup

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

```env
HF_TOKEN=hf_your_token_here       # Hugging Face token for faster model downloads

LLM_BASE_URL=http://localhost:20128/v1  # Your local LLM endpoint (required for translation)
LLM_MODEL=cx/gpt-5.6-luna              # Model name
LLM_API_KEY=local                       # API key (can be anything for local endpoints)
```

> **Translation requires a running local LLM endpoint.** The script uses an OpenAI-compatible API at `LLM_BASE_URL`. Without it, transcription still works but translation will fail.

---

## Scripts

### `translator.py` — Full Pipeline

Transcribes `audio.wav` and optionally translates subtitles.

```bash
./run.sh
# or
python translator.py
```

Prompts:
- Film language (`pl`, `ru`, `auto`, etc.) — default: auto-detect
- Subtitle mode:
  - `1` Original only
  - `2` Bilingual (translation + original in one track)
  - `3` Separate tracks (selectable in media player)
- Target language — default: `en`

Outputs:
- `subtitles.srt` — original transcription
- `subtitles_bilingual_<lang>.srt` — mode 2
- `subtitles_<lang>.srt` — mode 3 translated track

---

### `make_bilingual.py` — Standalone Subtitle Translator

Translates an existing `.srt` without re-transcribing.

```bash
python make_bilingual.py
```

---

### `extract_audio.sh` — Extract Audio from MP4

```bash
./extract_audio.sh
```

Outputs `audio.wav` at 16kHz mono (format expected by Whisper).

---

### `bake_subtitles.sh` — Embed Subtitles into Video

```bash
./bake_subtitles.sh
```

Modes:
- `1` Bake in (hardcoded, always visible) — uses GPU encoding via `h264_nvenc`
- `2` Soft track (single, toggleable in media player)
- `3` Multi-track (multiple languages, each selectable separately)

---

### `run.sh` — Run translator with correct library paths

```bash
./run.sh
```

Use this instead of `python translator.py` directly if you get `libcublas.so.12 not found` errors.
