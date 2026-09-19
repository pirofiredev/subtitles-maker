#!/bin/bash
read -rp "Input MP4 file [default: lalka1.mp4]: " input
input="${input:-lalka1.mp4}"
ffmpeg -i "$input" -vn -acodec pcm_s16le -ar 16000 -ac 1 audio.wav
