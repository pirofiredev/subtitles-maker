#!/usr/bin/env python3
from dotenv import load_dotenv
load_dotenv()
import re
import sys
import random
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from tqdm import tqdm
from deep_translator import GoogleTranslator

PROXIFLY_URL = "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt"


def fetch_proxifly_list(limit=50):
    print("Fetching proxy list from Proxifly...")
    try:
        req = urllib.request.Request(
            PROXIFLY_URL,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            lines = resp.read().decode("utf-8").splitlines()
        proxies = [p.strip() for p in lines if p.strip()]
        random.shuffle(proxies)
        selected = proxies[:limit]
        print(f"Loaded {len(selected)} proxies from Proxifly.")
        return selected
    except Exception as e:
        print(f"Warning: Failed to fetch Proxifly proxy list ({e}). Falling back to direct connection.")
        return []


def parse_srt(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    blocks = re.split(r"\n\s*\n", content.strip())
    subtitles = []

    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) >= 3:
            index = lines[0].strip()
            timestamp = lines[1].strip()
            text = "\n".join(lines[2:]).strip()
            subtitles.append({
                "index": index,
                "timestamp": timestamp,
                "text": text,
            })
    return subtitles


def write_srt(file_path, subtitles):
    with open(file_path, "w", encoding="utf-8") as f:
        for i, sub in enumerate(subtitles, 1):
            f.write(f"{i}\n")
            f.write(f"{sub['timestamp']}\n")
            f.write(f"{sub['text']}\n\n")


def translate_chunk(chunk_data, source_lang, target_lang, proxy=None):
    chunk_idx, chunk = chunk_data
    texts = [s["text"] for s in chunk]
    valid_indices = [idx for idx, t in enumerate(texts) if t.strip()]
    valid_texts = [texts[idx] for idx in valid_indices]

    proxies_dict = {"http": proxy, "https": proxy} if proxy else None
    translator = GoogleTranslator(source=source_lang, target=target_lang, proxies=proxies_dict)

    translations = []
    if valid_texts:
        try:
            translations = translator.translate_batch(valid_texts)
        except Exception:
            # Fallback without proxy or per item
            direct_translator = GoogleTranslator(source=source_lang, target=target_lang)
            for t in valid_texts:
                try:
                    translations.append(direct_translator.translate(t) or t)
                except Exception:
                    translations.append(t)

    trans_map = {}
    for orig_idx, trans in zip(valid_indices, translations):
        trans_map[orig_idx] = trans

    chunk_result = []
    for idx, sub in enumerate(chunk):
        trans_text = trans_map.get(idx, "").strip()
        orig_text = sub["text"].strip()
        if trans_text:
            combined_text = f"{trans_text}\n{orig_text}"
        else:
            combined_text = orig_text

        chunk_result.append({
            "index": sub["index"],
            "timestamp": sub["timestamp"],
            "text": combined_text,
        })

    return chunk_idx, chunk_result


def make_bilingual_subtitles(
    input_file="subtitles.srt",
    target_lang="ru",
    source_lang="auto",
    output_file=None,
    use_subtitle_tk=False,
    use_proxifly=False,
    max_workers=8,
):
    input_path = Path(input_file)
    if not input_path.exists():
        print(f"Error: {input_file} not found.")
        sys.exit(1)

    if output_file is None:
        output_file = input_path.stem + f"_bilingual_{target_lang}.srt"

    print(f"Parsing subtitles from: {input_file}")
    subtitles = parse_srt(input_file)
    if not subtitles:
        print("No subtitle units found.")
        return

    print(f"Translating {len(subtitles)} subtitle units to '{target_lang}' (Source: '{source_lang}')...")

    chunk_size = 20
    chunks = [
        (i // chunk_size, subtitles[i : i + chunk_size])
        for i in range(0, len(subtitles), chunk_size)
    ]

    proxies = fetch_proxifly_list() if use_proxifly else []
    translated_chunks = [None] * len(chunks)

    workers = max_workers if use_proxifly or len(chunks) > 1 else 1

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for chunk_idx, chunk in chunks:
            proxy = proxies[chunk_idx % len(proxies)] if proxies else None
            fut = executor.submit(
                translate_chunk,
                (chunk_idx, chunk),
                source_lang,
                target_lang,
                proxy,
            )
            futures[fut] = chunk_idx

        with tqdm(total=len(chunks), desc=f"Translating ({target_lang})") as pbar:
            for fut in as_completed(futures):
                chunk_idx, res = fut.result()
                translated_chunks[chunk_idx] = res
                pbar.update(1)

    translated_subtitles = []
    for c in translated_chunks:
        if c:
            translated_subtitles.extend(c)

    # Option to merge / process using subtitle-tk if available
    temp_trans_path = input_path.stem + f"_{target_lang}_only.srt"
    if use_subtitle_tk:
        # Write translated only, then merge using subtitle-tk
        trans_only_subs = []
        for idx, sub in enumerate(subtitles):
            orig_combined = translated_subtitles[idx]["text"].split("\n")
            trans_line = orig_combined[0] if len(orig_combined) > 1 else ""
            trans_only_subs.append({
                "index": sub["index"],
                "timestamp": sub["timestamp"],
                "text": trans_line,
            })
        write_srt(temp_trans_path, trans_only_subs)
        print("Merging tracks using subtitle-tk...")
        subprocess.run([
            "subtitle-tk", "subtitle-tracks", "merge",
            temp_trans_path, str(input_path),
            "--priority", "combine",
            "-o", str(output_file)
        ], check=True)
        Path(temp_trans_path).unlink(missing_ok=True)
    else:
        write_srt(output_file, translated_subtitles)

    print(f"\nBilingual subtitles created: {output_file}")


def main():
    print("=== Bilingual Subtitle Creator ===")
    input_file = input("Input SRT file [default: subtitles.srt]: ").strip()
    if not input_file:
        input_file = "subtitles.srt"

    target_lang = input("Target language to add on top (e.g., ru, en, de, es, fr) [default: ru]: ").strip()
    if not target_lang:
        target_lang = "ru"

    source_lang = input("Source subtitle language (e.g., pl, en, auto) [default: auto]: ").strip()
    if not source_lang:
        source_lang = "auto"

    out_file = input(f"Output SRT filename [default: subtitles_bilingual_{target_lang}.srt]: ").strip()
    if not out_file:
        out_file = f"subtitles_bilingual_{target_lang}.srt"

    use_proxifly_input = input("Use Proxifly proxies + multi-threading? (y/N): ").strip().lower()
    use_proxifly = (use_proxifly_input == "y" or use_proxifly_input == "yes")

    use_tk_input = input("Use subtitle-tk merge backend? (y/N): ").strip().lower()
    use_subtitle_tk = (use_tk_input == "y" or use_tk_input == "yes")

    make_bilingual_subtitles(
        input_file=input_file,
        target_lang=target_lang,
        source_lang=source_lang,
        output_file=out_file,
        use_subtitle_tk=use_subtitle_tk,
        use_proxifly=use_proxifly,
    )


if __name__ == "__main__":
    main()
