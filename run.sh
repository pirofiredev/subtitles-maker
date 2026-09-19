#!/bin/bash
PYVER=$(python3 -c "import sys; print(f'python{sys.version_info.major}.{sys.version_info.minor}')")
export LD_LIBRARY_PATH=/home/$USER/.local/lib/$PYVER/site-packages/nvidia/cublas/lib:$LD_LIBRARY_PATH
python3 translator.py
