#!/usr/bin/env python
"""DEPRECATED: use ``porous-designer generate`` instead.

This wrapper preserves CLI compatibility while delegating STL generation to the
porous_designer package. STEP generation remains experimental and is NOT used
by the Phase 2A pipeline.
"""
from __future__ import annotations

import sys
import warnings

warnings.warn(
    "porousgen.py is deprecated. Use: porous-designer generate <spec.txt>",
    DeprecationWarning,
    stacklevel=1,
)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    from porous_designer.cli import main as cli_main

    return cli_main(["generate", sys.argv[1], *sys.argv[2:]])


if __name__ == "__main__":
    sys.exit(main())
