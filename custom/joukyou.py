from common.mj_helper import GameInfo
from common.log_helper import LOGGER
from custom.count_dora import count_dora, parse_tile, next_dora

FLAG_DEBUG: bool = False
MS_2_MJAI = {
    'E': '1z',
    'S': '2z',
    'W': '3z',
    'N': '4z',
    'P': '5z',
    'F': '6z',
    'C': '7z',
}
HONORS = {'E', 'S', 'W', 'N', 'P', 'F', 'C'}

def is_honor(tile: str) -> bool:
    """
    Return True if tile is an honor tile.
    Supports mjai (E,S,W,N,P,F,C) and mahjong soul (1z-7z)
    """
    if tile in HONORS:
        return True
    return len(tile) == 2 and tile[1] == 'z'

def is_normal_dora(tile: str, dora_indicators: list[str]) -> bool:
    if tile in HONORS:
        tile = MS_2_MJAI[tile]
    tile_split = tuple(tile[:2])
    return tile_split in ms_dora_to_actual(dora_indicators)


def ms_dora_to_actual(dora_indicators: list[str]) -> set[tuple[int, str]]:
    """
    Convert Mahjong Soul dora indicators to actual dora tiles.
    Return set of (rank, suit)
    """
    doras = set()
    for t in dora_indicators:
        rank, suit, _ = parse_tile(t)
        doras.add(next_dora(rank, suit))
    return doras


def endgame_buffer(gi:GameInfo) -> int:
    """立直棒 + 本场供托对点差安全线的修正"""
    return gi.n_riichibou * 1000 + gi.honba * 400


def adaptive_n(gi:GameInfo) -> int:
    if gi.n_other_reach() == 0:
        # 获取手牌向听数
        # n_shanten = shanten(gi.my_tehai, gi.my_tsumohai)
        n_shanten = gi.shanten
        # 获取等效向听数
        n_equiv = n_shanten
        # 根据巡目调整等效向听数上限
        max_n = 5
        junme = (70 - gi.yama) // 4 + 1
        if junme <= 3:
            max_n = 5
        elif junme <= 6:
            max_n = 4
        elif junme <= 9:
            max_n = 3
        elif junme <= 12:
            max_n = 2
        elif junme <= 15:
            max_n = 1
        else:
            max_n = 0
        # 如果是南一南二，等效向听数减1
        # 如果是南三局及以后，等效向听数减2
        if gi.bakaze == 'S' and gi.kyoku <= 2:
            n_equiv -= 1
        elif gi.bakaze == 'W' or (gi.bakaze == 'S' and gi.kyoku >= 3):
            n_equiv -= 2
        # 如果是庄家，等效向听数减1
        if gi.oya == gi.self_seat:
            n_equiv -= 1
        # 根据自身手牌和副露中宝牌、红宝牌、双东的数量减少等效向听数
        try:
            dora_count = 0
            if gi.my_tehai:
                dora_count = count_dora(gi.doras_ms, gi.my_tehai + ([gi.my_tsumohai] if gi.my_tsumohai else []), gi.fuuros_ms[gi.self_seat])
                # 双东视同宝牌，亦即相当于北也是宝牌表示牌
                if gi.bakaze == 'E' and gi.self_seat == gi.oya:
                    dora_count += count_dora(['N'], gi.my_tehai + ([gi.my_tsumohai] if gi.my_tsumohai else []), gi.fuuros_ms[gi.self_seat])
                n_equiv -= dora_count

                # 根据其他玩家副露中宝牌、红宝牌、双东的数量减少等效向听数
            if gi.doras_ms:
                others_dora_count = 0
                for i in range(4):
                    if gi.fuuros_ms[i]:
                        if i != gi.self_seat:
                            others_dora_count += count_dora(gi.doras_ms, gi.fuuros_ms[i])
                            if gi.bakaze == 'E' and i == gi.oya:
                                # 双东视同宝牌，亦即相当于北也是宝牌表示牌
                                others_dora_count += count_dora(['N'], gi.fuuros_ms[i])
                    n_equiv -= others_dora_count
        except Exception as e:
            LOGGER.error(e)

        if max_n < 0:
            max_n = 0

        n = max(n_equiv, 0)
        n = min(n, max_n)
        try:
            LOGGER.debug(
                "无人立直，计算手牌向听数为 %d 向听，第 %d 巡, n 设为 %d, n_equiv 为 %d, max_n 为 %d, 玩家为庄家？ %s, 手牌为 %s, 自摸牌为 %s, 宝牌数为 %d, 宝牌表示牌 %s, 其他玩家总计副露宝牌数（含双东）为 %d, 自身副露为 %s, 所有副露为 %s",
                n_shanten, junme, n, n_equiv, max_n, str(gi.oya == gi.self_seat), gi.my_tehai, gi.my_tsumohai, dora_count, gi.doras_ms, others_dora_count, gi.fuuros_ms[gi.self_seat], gi.fuuros_ms
            )
        except Exception as e:
            LOGGER.error(e)
    else:
        LOGGER.debug("有他人立直，n 设为 0")
        n = 0
    return n


def compute_rank_deltas(gi:GameInfo) -> tuple[int, int, int]:
    """
    计算自己在分数排名中的名次，以及与上一位、下一位的分数差
    同分时按 index 越小名次越高

    Returns:
        rank (int): 自己的名次，1~4
        delta_prev (int): 与上一位的分数差（正数表示差多少分）
        delta_next (int): 与下一位的分数差（正数表示差多少分）
    """

    scores = gi.scores
    self_seat = gi.self_seat

    if len(scores) != 4:
        raise ValueError("scores 必须是长度为 4 的列表")
    
    my_score = scores[self_seat]

    # 创建 (index, score) 元组列表
    indexed_scores = [(i, s) for i, s in enumerate(scores)]

    # 按分数降序排序，同分则 index 越小越靠前
    indexed_scores.sort(key=lambda x: (-x[1], x[0]))

    # 找到自己在排序后的名次
    for rank, (idx, s) in enumerate(indexed_scores, start=1):
        if idx == self_seat:
            my_rank = rank
            break

    # 计算上一位差值
    if my_rank == 1:
        delta_prev = 0
    else:
        prev_score = indexed_scores[my_rank - 2][1]
        delta_prev = prev_score - my_score

    # 计算下一位差值
    if my_rank == 4:
        delta_next = 0
    else:
        next_score = indexed_scores[my_rank][1]
        delta_next = my_score - next_score

    return my_rank, delta_prev, delta_next


def oya_rank_and_diff(gi:GameInfo) -> tuple[int, int]:
    """
    返回：
    - 庄家的顺位（1~4）
    - 自己与庄家的点差绝对值
    """

    scores = gi.scores
    oya = gi.oya
    me = gi.self_seat

    # [(seat, score), ...]
    ranked = sorted(
        enumerate(scores),
        key=lambda x: (-x[1], x[0])  # 分数高优先，同分 index 小优先
    )

    # 找庄家的顺位
    for i, (seat, _) in enumerate(ranked):
        if seat == oya:
            oya_rank = i + 1
            break

    # 点差（绝对值）
    score_diff = abs(scores[me] - scores[oya])

    return oya_rank, score_diff


def is_defensive(gi:GameInfo) -> bool:
    if gi.bakaze != 'E' and (gi.self_seat != gi.oya):
        junme = (70 - gi.yama) // 4 + 1
        if junme <= 9:
            LOGGER.debug('南场非庄家，第9巡及之前打字牌概率减半')
            return True
    return False


def is_haipaiori(gi:GameInfo) -> bool:
    """配牌弃和逻辑
    南四局
    手牌3向听或以上，6巡目或以前
    自己是庄家
    （1）是第一名且领先第二满贯自摸条件以上，或
    （2）是第二名且落后第一亲满自摸以上，并且领先第三名大于4000点（流局不会被逆）
    自己不是庄家
    （1）是第一名且领先庄家和第二（如不同）满贯自摸以上，或
    （2）是第二名且第一是庄家，自己落后第一满贯自摸以上，并且领先第三名大于4000点（流局不会被逆）
    """

    # 计算供托立直棒和本场点数
    buf = endgame_buffer(gi)

    if gi.bakaze == 'S' and gi.kyoku == 4:
        junme = (70 - gi.yama) // 4 + 1
        if gi.shanten >= 3 and junme <= 6:
            my_rank, delta_prev, delta_next = compute_rank_deltas(gi)
            # 自己是庄家
            if gi.self_seat == gi.oya:
                if my_rank == 1 and delta_next > 12000 + buf:
                    LOGGER.debug('南四自亲一位配牌弃和， (我的顺位，下位点差): %s', (my_rank, delta_next))
                    return True
                elif my_rank == 2 and delta_prev >= 16000 + buf and delta_next > 4000:
                    LOGGER.debug('南四自亲二位配牌弃和， (我的顺位，上位点差，下位点差): %s', (my_rank, delta_prev, delta_next))
                    return True
            # 自己不是庄家
            else:
                oya_rank, delta_oya = oya_rank_and_diff(gi)
                if my_rank == 1 and delta_oya >= 16000 + buf and delta_next > 10000 + buf:
                    LOGGER.debug('南四非自亲一位配牌弃和， (我的顺位，下位点差，亲点差): %s', (my_rank, delta_next, delta_oya))
                    return True
                elif my_rank == 2 and oya_rank == 1 and delta_prev > 12000 + buf and delta_next > 4000:
                    LOGGER.debug('南四非自亲二位配牌弃和， (我的顺位，上位=亲点差，下位点差): %s', (my_rank, delta_prev, delta_next))
                    return True

    return False


def defensive_ops(ops: list[tuple[str, float]], r: float = 0.5) -> list[tuple[str, float]]:
    """
    Multiply probability of honor tiles by r.
    """
    new_ops = []
    for tile, prob in ops:
        if is_honor(tile):
            if FLAG_DEBUG:
                LOGGER.debug(
                    "defensive: tile=%s base=%.4f mult=%.1f final=%.4f",
                    tile, prob, r, prob * r
                )
            new_ops.append((tile, prob * r))
        else:
            new_ops.append((tile, prob))
    return new_ops


def haipaiori_ops(ops: list[tuple[str, float]], gi) -> list[tuple[str, float]]:
    """
    配牌弃和概率调整：
    - 普通牌：增量加权
    - 宝牌 / 红宝牌：乘法加权
    """
    out = []
    doras = set(gi.doras_ms or [])

    for tile, prob in ops:
        rank, suit, is_red = parse_tile(tile)

        # 基础增量加权
        add_prob = 0
        if suit == 'z':
            add_prob = 1
        elif rank in (4,5,6):
            add_prob = 1e4
        elif rank in (3,7):
            add_prob = 1000
        elif rank in (2,8):
            add_prob = 100
        elif rank in (1,9):
            add_prob = 10

        final_prob = prob + add_prob

        # 宝牌/红宝牌乘法
        if tile in doras:
            final_prob *= 1e4
        if is_red:
            final_prob *= 1e4

        out.append((tile, final_prob))

    return out

def count_self_z1928(gi: GameInfo) -> float:
    """
    统计 self 手牌中的：
    - 1 / 9 数牌 +1
    - 字牌 (z) +1
    - 2 / 8 数牌 +0.5
    """
    total = 0.0

    for tile in gi.my_tehai + [gi.my_tsumohai] if gi.my_tsumohai else gi.my_tehai:
        if tile in HONORS:
            tile = MS_2_MJAI[tile]
        num = tile[0]
        suit = tile[1]

        # 字牌
        if suit == "z":
            total += 1
            continue

        # 数牌
        if num == 1 or num == 9:
            total += 1
        elif num == 2 or num == 8:
            total += 0.5

    return total

def self_hand_value(gi: GameInfo) -> int:
    v = count_dora(gi.doras_ms, gi.my_tehai + [gi.my_tsumohai] if gi.my_tsumohai else gi.my_tehai, gi.fuuros_ms[gi.self_seat])
    if gi.oya == gi.self_seat:
        v += 1
    if has_renfuu(gi, 'self'):
        v += 2
    if count_self_z1928(gi) <= 6:
        v += 1
    return v

def has_renfuu(gi: GameInfo, mode: str):
    if mode == 'self':
        if gi.jikaze != gi.bakaze:
            return False
        
        tiles: list[str] = (gi.my_tehai + [gi.my_tsumohai] if gi.my_tsumohai else gi.my_tehai) + gi.fuuros_ms[gi.self_seat]
        return tiles.count(gi.bakaze) >= 2
    else:
        if gi.bakaze == 'E':
            tiles: list[str] = gi.fuuros_ms[0]
        elif gi.bakaze == 'S':
            tiles: list[str] = gi.fuuros_ms[1]
        elif gi.bakaze == 'W':
            tiles: list[str] = gi.fuuros_ms[2]
        elif gi.bakaze == 'N':
            tiles: list[str] = gi.fuuros_ms[3]
        else:
            return False
        return tiles.count(gi.bakaze) >= 2