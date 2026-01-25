# custom/shanten.py

MJAI_TILES_34 = [
    '1m','2m','3m','4m','5m','6m','7m','8m','9m',
    '1p','2p','3p','4p','5p','6p','7p','8p','9p',
    '1s','2s','3s','4s','5s','6s','7s','8s','9s',
    'E','S','W','N','P','F','C'
]

TERMINALS_AND_HONORS = [
    '1m','9m','1p','9p','1s','9s',
    'E','S','W','N','P','F','C'
]

# ==================================================
# 基础工具
# ==================================================

def tiles_to_index(tile: str) -> int:
    return MJAI_TILES_34.index(tile.replace('r', ''))

def tiles_to_counts(tiles: list[str]) -> list[int]:
    c = [0] * 34
    for t in tiles:
        if t:
            c[tiles_to_index(t)] += 1
    return c

# ==================================================
# 标准形向听（完整：面子 + 搭子 + 雀头 + 副露）
# ==================================================

def shanten_standard(counts: list[int], fixed_melds: int = 0) -> int:
    min_shanten = 8

    def dfs(c, idx, melds, taatsu, pair_used):
        nonlocal min_shanten

        # 跳到下一个非空牌
        while idx < 34 and c[idx] == 0:
            idx += 1

        if idx == 34:
            total_melds = melds + fixed_melds
            need_melds = max(0, 4 - total_melds)
            effective_taatsu = min(taatsu, need_melds)

            sh = 8 - 2 * total_melds
            sh -= 1 if pair_used else 0
            sh -= effective_taatsu

            min_shanten = min(min_shanten, sh)
            return

        # ===== 刻子 =====
        if c[idx] >= 3:
            c[idx] -= 3
            dfs(c, idx, melds + 1, taatsu, pair_used)
            c[idx] += 3

        # ===== 顺子 =====
        if idx < 27 and idx % 9 <= 6:
            if c[idx+1] > 0 and c[idx+2] > 0:
                c[idx] -= 1
                c[idx+1] -= 1
                c[idx+2] -= 1
                dfs(c, idx, melds + 1, taatsu, pair_used)
                c[idx] += 1
                c[idx+1] += 1
                c[idx+2] += 1

        # ===== 雀头 =====
        if not pair_used and c[idx] >= 2:
            c[idx] -= 2
            dfs(c, idx, melds, taatsu, True)
            c[idx] += 2

        # ===== 搭子 =====
        # 两面 / 边张
        if idx < 27 and idx % 9 <= 7 and c[idx+1] > 0:
            c[idx] -= 1
            c[idx+1] -= 1
            dfs(c, idx, melds, taatsu + 1, pair_used)
            c[idx] += 1
            c[idx+1] += 1

        # 嵌张
        if idx < 27 and idx % 9 <= 6 and c[idx+2] > 0:
            c[idx] -= 1
            c[idx+2] -= 1
            dfs(c, idx, melds, taatsu + 1, pair_used)
            c[idx] += 1
            c[idx+2] += 1

        # ===== 当孤张跳过 =====
        dfs(c, idx + 1, melds, taatsu, pair_used)

    dfs(counts[:], 0, 0, 0, False)
    return min_shanten

# ==================================================
# 七对 / 国士（仅门清）
# ==================================================

def shanten_chiitoitsu(counts: list[int]) -> int:
    pairs = sum(1 for c in counts if c >= 2)
    return max(6 - pairs, 0)

def shanten_kokushi(counts: list[int]) -> int:
    unique = sum(1 for t in TERMINALS_AND_HONORS
                 if counts[tiles_to_index(t)] > 0)
    pair = any(counts[tiles_to_index(t)] >= 2
               for t in TERMINALS_AND_HONORS)
    sh = 13 - unique
    if pair:
        sh -= 1
    return max(sh, 0)

# ==================================================
# 副露数推断
# ==================================================

def infer_open_melds(tile_count: int) -> int:
    if tile_count < 1 or tile_count > 14:
        raise ValueError(f"非法手牌张数: {tile_count}")
    return max(0, (14 - tile_count) // 3)

# ==================================================
# 对外统一接口
# ==================================================

def shanten(hand: list[str], tsumohai: str = None,
            n_open_melds: int | None = None) -> int:

    tiles = hand[:]
    if tsumohai:
        tiles.append(tsumohai)

    if n_open_melds is None:
        n_open_melds = infer_open_melds(len(tiles))

    # ===== 14 张：枚举弃牌 =====
    if len(tiles) % 3 == 2:
        best = 99
        for i in range(len(tiles)):
            rest = tiles[:i] + tiles[i+1:]
            counts = tiles_to_counts(rest)

            sh = shanten_standard(counts, n_open_melds)

            if n_open_melds == 0:
                sh = min(
                    sh,
                    shanten_chiitoitsu(counts),
                    shanten_kokushi(counts)
                )

            best = min(best, sh)

        return -1 if best == 0 else best

    # ===== 非 14 张 =====
    counts = tiles_to_counts(tiles)
    sh = shanten_standard(counts, n_open_melds)

    if n_open_melds == 0:
        sh = min(
            sh,
            shanten_chiitoitsu(counts),
            shanten_kokushi(counts)
        )

    return sh
