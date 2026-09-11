#!/usr/bin/env python3
"""Run this skill with the marketplace's shared evidence engine."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from auditlib.runner import main
if __name__ == '__main__':
    main(component='crawl')
