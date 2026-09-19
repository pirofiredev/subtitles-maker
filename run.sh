#!/bin/bash
export LD_LIBRARY_PATH=/home/pirodev/.local/lib/python3.14/site-packages/nvidia/cublas/lib:$LD_LIBRARY_PATH
python translator.py
