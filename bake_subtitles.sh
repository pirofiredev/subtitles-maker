#!/bin/bash
read -rp "Input MP4 file: " input
if [[ -z "$input" ]]; then echo "Error: input file required."; exit 1; fi
if [[ ! -f "$input" ]]; then echo "Error: '$input' not found."; exit 1; fi
if [[ "$input" != *.mp4 ]]; then echo "Error: input must be an .mp4 file."; exit 1; fi

echo ""
echo "Subtitle mode:"
echo "  1) Bake in (hardcoded, always visible)"
echo "  2) Soft (single embedded track, toggleable)"
echo "  3) Multi-track (multiple separate subtitle tracks)"
read -rp "Choose [1/2/3]: " mode
if [[ "$mode" != "1" && "$mode" != "2" && "$mode" != "3" ]]; then echo "Error: choose 1, 2 or 3."; exit 1; fi

if [[ "$mode" == "3" ]]; then
    tracks=()
    langs=()
    echo "Enter subtitle tracks (leave filename empty to finish):"
    while true; do
        read -rp "  SRT file: " srt
        [[ -z "$srt" ]] && break
        if [[ ! -f "$srt" ]]; then echo "  Warning: '$srt' not found, skipping."; continue; fi
        if [[ "$srt" != *.srt ]]; then echo "  Warning: must be .srt, skipping."; continue; fi
        read -rp "  Language tag for '$srt' (e.g. pol, rus, eng): " lang
        lang="${lang:-und}"
        tracks+=("$srt")
        langs+=("$lang")
        echo "  Added: $srt [$lang]"
    done
    if [[ ${#tracks[@]} -eq 0 ]]; then echo "Error: no valid subtitle tracks provided."; exit 1; fi
else
    read -rp "Subtitle file: " subs
    if [[ -z "$subs" ]]; then echo "Error: subtitle file required."; exit 1; fi
    if [[ ! -f "$subs" ]]; then echo "Error: '$subs' not found."; exit 1; fi
    if [[ "$subs" != *.srt ]]; then echo "Error: subtitle must be an .srt file."; exit 1; fi

    if [[ "$mode" == "2" ]]; then
        read -rp "Subtitle language tag (e.g. rus, eng, pol) [leave empty to autodetect]: " sub_lang
        if [[ -z "$sub_lang" ]]; then
            sub_lang=$(ffprobe -v error -select_streams a:0 -show_entries stream_tags=language -of csv=p=0 "$input" 2>/dev/null)
            sub_lang="${sub_lang:-und}"
            echo "Autodetected language: $sub_lang"
        fi
    fi
fi

output="${input%.*}_subtitled.mp4"

# Auto-detect source bitrate
bitrate=$(ffprobe -v error -select_streams v:0 -show_entries stream=bit_rate -of csv=p=0 "$input" 2>/dev/null)
if [[ -z "$bitrate" || "$bitrate" == "N/A" ]]; then
    bitrate=$(ffprobe -v error -show_entries format=bit_rate -of csv=p=0 "$input" 2>/dev/null)
fi
bitrate_k=$(( bitrate / 1000 ))
echo "Detected bitrate: ${bitrate_k}k"

# Get total duration in seconds
duration=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$input" 2>/dev/null)
duration=${duration%.*}

progress_filter() {
    while IFS= read -r line; do
        if [[ "$line" == out_time_ms=* ]]; then
            ms="${line#out_time_ms=}"
            current=$(( ms / 1000000 ))
            if [[ $duration -gt 0 ]]; then
                pct=$(( current * 100 / duration ))
                filled=$(( pct * 40 / 100 ))
                bar=$(printf '%0.s#' $(seq 1 $filled))
                empty=$(printf '%0.s-' $(seq 1 $((40 - filled))))
                printf "\r[%s%s] %d%% (%ds / %ds)" "$bar" "$empty" "$pct" "$current" "$duration"
            fi
        fi
    done
}

if [[ "$mode" == "1" ]]; then
    echo "Baking subtitles (hardcoded)..."
    ffmpeg -i "$input" -vf "subtitles=$subs" \
        -c:v h264_nvenc -preset fast -b:v "${bitrate_k}k" -c:a copy \
        "$output" -progress pipe:1 -nostats -loglevel error 2>&1 | progress_filter

elif [[ "$mode" == "2" ]]; then
    echo "Embedding subtitles (soft track)..."
    ffmpeg -i "$input" -i "$subs" \
        -c:v copy -c:a copy -c:s mov_text \
        -metadata:s:s:0 language="$sub_lang" \
        "$output" -progress pipe:1 -nostats -loglevel error 2>&1 | progress_filter

else
    echo "Embedding ${#tracks[@]} subtitle track(s)..."
    cmd=(ffmpeg -i "$input")
    for srt in "${tracks[@]}"; do
        cmd+=(-i "$srt")
    done
    cmd+=(-c:v copy -c:a copy -c:s mov_text)
    for i in "${!langs[@]}"; do
        cmd+=(-metadata:s:s:$i "language=${langs[$i]}")
    done
    cmd+=("$output" -progress pipe:1 -nostats -loglevel error)
    "${cmd[@]}" 2>&1 | progress_filter
fi

echo -e "\nDone: $output"
