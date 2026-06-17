"""Shared matplotlib config for Japanese labels.

Import this module before any matplotlib pyplot use:

    from _jp_font import setup_japanese_font
    setup_japanese_font()

It registers IPAGothic with matplotlib's font manager and sets it
as the default sans-serif family.
"""

from pathlib import Path

import matplotlib
import matplotlib.font_manager as fm

IPA_PATH = "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"


def setup_japanese_font() -> None:
    if Path(IPA_PATH).exists():
        fm.fontManager.addfont(IPA_PATH)
    matplotlib.rcParams["font.family"] = "IPAGothic"
    matplotlib.rcParams["axes.unicode_minus"] = False
