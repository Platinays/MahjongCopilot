# ==================================================
# Dora / Aka Dora counter
# ==================================================

from collections import Counter
from typing import Iterable, Optional, Tuple
from common.log_helper import LOGGER

# ---------- parsing ----------

FLAG_DEBUG: bool = False

HONOR_MAP = {
    'E': 1, 'S': 2, 'W': 3, 'N': 4,
    'P': 5, 'F': 6, 'C': 7,
}

REV_HONOR_MAP = {v: k for k, v in HONOR_MAP.items()}


def parse_tile(tile: str) -> Tuple[int, str, bool]:
    """
    Normalize a tile string into (rank, suit, is_red)

    Supports:
    - mjai: 5sr, E
    - tenhou / mahjong soul: 0s, 1z
    """
    tile = tile.strip()

    # honors (mjai)
    if tile in HONOR_MAP:
        return HONOR_MAP[tile], 'z', False

    # red five (mjai)
    if tile.endswith('r'):
        rank = int(tile[0])
        suit = tile[1]
        return rank, suit, True

    # mahjong soul / tenhou red
    if tile[0] == '0':
        suit = tile[1]
        return 5, suit, True

    # mahjong soul honor
    if tile.endswith('z'):
        return int(tile[0]), 'z', False

    # normal tile
    rank = int(tile[0])
    suit = tile[1]
    return rank, suit, False


# ---------- dora logic ----------

def next_dora(rank: int, suit: str) -> Tuple[int, str]:
    """Convert dora indicator to actual dora"""
    if suit == 'z':
        # winds
        if rank <= 4:
            return (rank % 4) + 1, 'z'
        # dragons
        return ((rank - 5 + 1) % 3) + 5, 'z'

    # number tiles
    return (rank % 9) + 1, suit


# ---------- main API ----------

def count_dora(
    dora_indicators: Iterable[str],
    hand_tiles: Iterable[str],
    open_tiles: Optional[Iterable[str]] = None,
) -> int:
    """
    Count total dora + red dora.
    """
    tiles = list(hand_tiles)
    if open_tiles:
        tiles.extend(open_tiles)

    # 保留原始字符串，方便日志
    parsed_tiles = [(t, *parse_tile(t)) for t in tiles]
    parsed_indicators = [(t, *parse_tile(t)) for t in dora_indicators]

    # ---------- red dora ----------
    red_count = 0
    for raw, rank, suit, is_red in parsed_tiles:
        if is_red:
            red_count += 1
            if FLAG_DEBUG:
                LOGGER.debug("aka dora: %s (rank=%d suit=%s)", raw, rank, suit)

    # ---------- normal dora ----------
    dora_counter = Counter()
    for raw, rank, suit, _ in parsed_indicators:
        dora = next_dora(rank, suit)
        dora_counter[dora] += 1
        if FLAG_DEBUG:
            LOGGER.debug(
                "dora indicator: %s -> dora: %d%s",
                raw, dora[0], dora[1]
            )

    normal_dora = 0
    for raw, rank, suit, _ in parsed_tiles:
        cnt = dora_counter.get((rank, suit), 0)
        if cnt > 0:
            normal_dora += cnt
            if FLAG_DEBUG:
                LOGGER.debug(
                    "dora: %s (rank=%d suit=%s) x%d",
                    raw, rank, suit, cnt
                )

    total = red_count + normal_dora
    if FLAG_DEBUG:
        LOGGER.debug(
            "dora summary: normal=%d, aka=%d, total=%d",
            normal_dora, red_count, total
        )

    return total

