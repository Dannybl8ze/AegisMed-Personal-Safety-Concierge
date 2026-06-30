import os
import sys

# Ensure aegismed-agent directory is in sys.path so tests/eval/custom_metrics can be imported
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from .agent import app

__all__ = ["app"]

