from copy import deepcopy
from common.log_helper import LOGGER
import random
from game.game_state import GameInfo
from .joukyou import is_normal_dora, compute_rank_deltas, is_haipaiori, self_hand_value, has_renfuu
from .count_dora import count_dora

"""
{
  "type": "dahai",
  "actor": 3,
  "pai": "W",
  "tsumogiri": false,
  "meta": {
    "q_values": [
      -3.985, -7.184, -7.126, -4.173,
      -7.861, -7.805, -7.290, -7.002,
      -7.257, 0.219, -2.358, -2.354
    ],
    "mask_bits": 10204768922,
    "is_greedy": true,
    "batch_size": 1,
    "eval_time_ns": 120126000,
    "shanten": 4,
    "at_furiten": false
  },
  "meta_options": {
    "W": 0.845,
    "N": 0.064,
    "C": 0.064,
    "2m": 0.013,
    "8m": 0.010
  },
  "buttons": ["none"],
  "seq": 21
}
"""

NAKI = ['chi_low', 'chi_mid', 'chi_high', 'pon', 'kan_select', 'chi', 'kakan', 'ankan', 'daiminkan']

def sample_top_k(meta_options: dict, in_top_k: int) -> str:
    # 1. 按概率降序排序，取前 in_top_k 个
    sorted_items = sorted(meta_options.items(), key=lambda x: x[1], reverse=True)
    top_k_items = sorted_items[:in_top_k]

    # 2. 按原始概率归一化
    keys, values = zip(*top_k_items)
    total = sum(values)
    probs = [v / total for v in values]

    # 3. 按归一化后的概率随机选一个 key
    choice = random.choices(keys, weights=probs, k=1)[0]
    return choice

# def sample_top_k_softmax(meta_options: dict, in_top_k: int) -> str:
#     # 1. 按概率降序排序，取前 in_top_k 个
#     sorted_items = sorted(meta_options.items(), key=lambda x: x[1], reverse=True)
#     top_k_items = sorted_items[:in_top_k]

#     # 2. 对 top_k 的值做 softmax
#     keys, values = zip(*top_k_items)
#     max_val = max(values)  # for numerical stability
#     exp_vals = [math.exp(v - max_val) for v in values]
#     sum_exp = sum(exp_vals)
#     probs = [v / sum_exp for v in exp_vals]

#     # 3. 按 softmax 概率随机选一个 key
#     choice = random.choices(keys, weights=probs, k=1)[0]
#     return choice

def uniform_honors_discard(mjai_action: dict, gi: GameInfo, excl_dora=True, excl_renfuu=True):
    """
    将字牌的 meta_options 概率重新分配为平均（原概率之和/数量）。
    只在 type=='dahai' 且原始最高概率牌是字牌时执行。
    对手中数量 >=2 的字牌不调整。
    直接修改 mjai_action["meta_options"]。

    排除逻辑：
    - excl_dora: 排除宝牌
    - excl_renfuu: 排除连风牌（自风且等于场风的牌）
    """

    honors_keys = ["E", "S", "W", "N", "C", "F", "P"]

    # 1️⃣ type 检查
    if mjai_action.get("type") != "dahai":
        return

    options: dict = dict(mjai_action.get("meta_options", {}))
    if not options:
        return

    # 2️⃣ 原始最高概率牌是否是字牌
    orig_max_tile = max(options.items(), key=lambda x: x[1])[0]
    if orig_max_tile not in honors_keys:
        return  # 原本最高概率不是字牌，直接返回

    # 3️⃣ 统计手中每种字牌数量
    hand_tiles = gi.my_tehai + [gi.my_tsumohai] if gi.my_tsumohai else gi.my_tehai
    tile_count = {}
    for t in hand_tiles:
        t_str = t
        if t_str in honors_keys:
            tile_count[t_str] = tile_count.get(t_str, 0) + 1

    # 4️⃣ 只保留字牌且数量 < 2
    honors = {k: v for k, v in options.items() if k in honors_keys and tile_count.get(k, 0) < 2}

    # 5️⃣ 排除宝牌
    if excl_dora:
        honors = {k: v for k, v in honors.items()
                  if not is_normal_dora(k, gi.doras_ms)}

    # 6️⃣ 排除连风牌（自风且等于场风）
    if excl_renfuu and gi.jikaze == gi.bakaze:
        honors = {k: v for k, v in honors.items() if k != gi.bakaze}

    # 7️⃣ 重新分配概率
    if honors:
        total_prob = sum(honors.values())
        n = len(honors)
        avg_prob = total_prob / n
        for k in honors:
            options[k] = avg_prob

    # 8️⃣ 更新 mjai_action
    mjai_action["meta_options"] = sorted(options.items(), key=lambda x: x[1], reverse=True)

    # 9️⃣ 随机选择字牌作为 pai（只从数量 <2 的字牌里选）
    if honors:
        mjai_action["pai"] = random.choice(list(honors.keys()))


def reverse_honors_discard(mjai_action: dict, gi: GameInfo, excl_dora=True, excl_renfuu=True):
    """
    将字牌的 meta_options 概率进行“逆序重排”：
    保留原概率集合，但按排序后反向分配。

    只在 type=='dahai' 且原始最高概率牌是字牌时执行。
    对手中数量 >=2 的字牌不调整。

    排除逻辑：
    - excl_dora: 排除宝牌
    - excl_renfuu: 排除连风牌（自风且等于场风的牌）
    """

    honors_keys = ["E", "S", "W", "N", "C", "F", "P"]

    # 1️⃣ type 检查
    if mjai_action.get("type") != "dahai":
        return

    options: dict = dict(mjai_action.get("meta_options", []))
    if not options:
        return

    # 2️⃣ 原始最高概率牌是否是字牌
    orig_max_tile = max(options.items(), key=lambda x: x[1])[0]
    if orig_max_tile not in honors_keys:
        return

    # 3️⃣ 统计手中每种字牌数量
    hand_tiles = gi.my_tehai + [gi.my_tsumohai] if gi.my_tsumohai else gi.my_tehai
    tile_count = {}
    for t in hand_tiles:
        t_str = t
        if t_str in honors_keys:
            tile_count[t_str] = tile_count.get(t_str, 0) + 1

    # 4️⃣ 只保留字牌且数量 < 2
    honors = {k: v for k, v in options.items()
              if k in honors_keys and tile_count.get(k, 0) < 2}

    # 5️⃣ 排除宝牌
    if excl_dora:
        honors = {k: v for k, v in honors.items()
                  if not is_normal_dora(k, gi.doras_ms)}

    # 6️⃣ 排除连风牌
    if excl_renfuu and gi.jikaze == gi.bakaze:
        honors = {k: v for k, v in honors.items() if k != gi.bakaze}

    # 7️⃣ 逆序分配概率
    if honors:
        # 按原概率排序（从大到小）
        sorted_items = sorted(honors.items(), key=lambda x: x[1], reverse=True)

        keys_sorted = [k for k, _ in sorted_items]
        values_sorted = [v for _, v in sorted_items]

        # 反转概率
        reversed_values = list(reversed(values_sorted))

        # 重新赋值
        for k, new_v in zip(keys_sorted, reversed_values):
            options[k] = new_v

    # 8️⃣ 更新
    mjai_action["meta_options"] = sorted(options.items(), key=lambda x: x[1], reverse=True)

    # 9️⃣ 随机选择（仍然只从筛选后的字牌）
    if options:
        mjai_action["pai"] = max(options.items(), key=lambda x: x[1])[0]


def haipaiori(mjai_action: dict, gi: GameInfo):
    """
    根据 mjai_action['type'] 调整动作：
    - 'dahai': 调整 meta_options 概率并选择最高概率牌作为 pai
        - 普通牌：增量加权
        - 宝牌 / 红宝牌：乘法加权
    - 吃碰杠相关动作：直接置为 'none'
    直接修改 mjai_action。
    """
    rt = mjai_action.get('type')

    if rt == 'dahai':
        options: dict = dict(mjai_action.get("meta_options", {}))

        for tile_str, prob in options.items():
            tile = tile_str

            # 基础增量加权
            add_prob = 0
            if tile.suit == 'z':  # 字牌
                add_prob = 1
            elif tile.num in (4,5,6):
                add_prob = 1e4
            elif tile.num in (3,7):
                add_prob = 1e3
            elif tile.num in (2,8):
                add_prob = 100
            elif tile.num in (1,9):
                add_prob = 10

            final_prob = prob + add_prob

            # 宝牌 / 红宝牌乘法
            if is_normal_dora(tile, gi.doras_ms):
                final_prob *= 1e4
            if tile[0] == '0' or tile[-1] == 'r':
                final_prob *= 1e4

            # 更新 options
            options[tile_str] = final_prob

        # 更新 mjai_action
        mjai_action["meta_options"] = sorted(options.items(), key=lambda x: x[1], reverse=True)

        # 直接选择最高概率牌作为 pai
        if options:
            mjai_action["pai"] = max(options.items(), key=lambda x: x[1])[0]

    elif rt in NAKI:
        # 吃碰杠动作直接置为 'none'
        mjai_action['type'] = 'none'

def chiitoi_honitsu(mjai_action: dict, gi: GameInfo):
    """
    七对 + 混一色策略（完整最终版）

    规则：

    0️⃣ 若 最大花色 + 字牌 >= 11 张 → 直接返回，不做任何调整

    dahai:
    - 对子及以上的牌：概率不调整
    - 花色策略：
        三种花色：
            1) 若最多花色 ≥ 第二花色 + 2：只调整另外两种
            2) 若最多花色与第二花色差 ≤ 1：
                若最少花色 ≤ 第二花色 - 2：只调整最少花色
                否则：调整所有三种

        只剩两种花色：
            若一样多 → 都调整
            若不一样多 → 只调整少的

    吃碰杠：
        若 shanten >= 2 → type = 'none'
    """

    # ======================
    # 手牌统计（最优先规则用）
    # ======================
    hand_tiles = gi.my_tehai + [gi.my_tsumohai] if gi.my_tsumohai else gi.my_tehai

    suit_count = {'m': 0, 'p': 0, 's': 0}
    honor_count = 0

    tile_count = {}

    for t in hand_tiles:
        tile_str = t
        tile_count[tile_str] = tile_count.get(tile_str, 0) + 1

        if t[1] in suit_count:
            suit_count[t[1]] += 1
        elif t[1] == 'z':
            honor_count += 1

    # ======================
    # 0️⃣ 最大花色 + 字牌 ≥ 11 → 直接返回
    # ======================
    max_suit_cnt = max(suit_count.values())
    if max_suit_cnt + honor_count >= 11:
        return

    rt = mjai_action.get("type")

    # ======================
    # 吃碰杠处理
    # ======================
    if rt in NAKI:
        shanten = int(mjai_action.get("meta", {}).get("shanten", 99))
        if shanten >= 2:
            mjai_action['type'] = 'none'
        return

    if rt != 'dahai':
        return

    options: dict = dict(mjai_action.get("meta_options", {}))
    if not options:
        return

    # ======================
    # 花色排序
    # ======================
    sorted_suits = sorted(
        suit_count.items(),
        key=lambda x: x[1],
        reverse=True
    )

    non_zero_suits = [(s, c) for s, c in sorted_suits if c > 0]

    adjust_suits = set()

    # ======================
    # 两种花色情况
    # ======================
    if len(non_zero_suits) == 2:
        (s1, c1), (s2, c2) = non_zero_suits

        if c1 == c2:
            adjust_suits = {s1, s2}
        else:
            adjust_suits = {s2}  # 少的那个

    # ======================
    # 三种花色情况
    # ======================
    elif len(non_zero_suits) == 3:
        (max_suit, max_cnt), (second_suit, second_cnt), (min_suit, min_cnt) = sorted_suits

        if max_cnt >= second_cnt + 2:
            adjust_suits = {second_suit, min_suit}

        elif max_cnt <= second_cnt + 1:
            if min_cnt <= second_cnt - 2:
                adjust_suits = {min_suit}
            else:
                adjust_suits = {'m', 'p', 's'}

    # 只有一种花色 → 不需要调整
    else:
        return

    # ======================
    # 调整概率（七对保护）
    # ======================
    for tile_str, prob in options.items():
        tile = tile_str

        # 对子或以上不调整
        if tile_count.get(tile_str, 0) >= 2:
            continue

        if tile[0] == '0' or tile[-1] == 'r' or is_normal_dora(tile, gi.doras_ms):
            continue

        if tile[1] in adjust_suits:
            add_prob = 0

            if tile[0] in (4, 5, 6):
                add_prob = 1
            elif tile[0] in (3, 7):
                add_prob = 10
            elif tile[0] in (2, 8):
                add_prob = 100
            elif tile[0] in (1, 9):
                add_prob = 1000

            options[tile_str] = prob + add_prob

    mjai_action["meta_options"] = sorted(options.items(), key=lambda x: x[1], reverse=True)

    # ======================
    # 最终选择最高概率
    # ======================
    mjai_action["pai"] = max(options.items(), key=lambda x: x[1])[0]

def half_honors_discard(mjai_action: dict):
    """
    将所有字牌弃牌概率减半。
    仅在 type == 'dahai' 时生效。
    """

    if mjai_action.get("type") != "dahai":
        return

    options: dict = dict(mjai_action.get("meta_options"))
    if not options:
        return

    # 字牌集合
    honors = {"E", "S", "W", "N", "P", "F", "C"}

    # 调整字牌概率
    for tile_str in options:
        if tile_str in honors:
            options[tile_str] *= 0.5

    candidates = {
        k: v for k, v in options.items()
        if k and (len(k) == 1 or k[0].isdigit())
    }

    # 如果没有候选，则回退到全部
    if not candidates:
        candidates = options

    mjai_action["pai"] = max(candidates.items(), key=lambda x: x[1])[0]
    mjai_action["meta_options"] = sorted(candidates.items(), key=lambda x: x[1], reverse=True)

def self_honitsu(gi: GameInfo) -> bool:
    hand_tiles = (gi.my_tehai + [gi.my_tsumohai] if gi.my_tsumohai else gi.my_tehai) + gi.fuuros_ms[gi.self_seat]

    suit_count = {'m': 0, 'p': 0, 's': 0}
    honor_count = 0

    for t in hand_tiles:
        if len(t) == 1 or t[1] == 'z':
            honor_count += 1
        elif t[1] in suit_count:
            suit_count[t[1]] += 1

    # ======================
    # 0️⃣ 最大花色 + 字牌 ≥ 11 → 返回 True
    # ======================
    max_suit_cnt = max(suit_count.values())
    if max_suit_cnt + honor_count >= 11:
        return True
    else:
        return False


def decide(reaction: dict, gi: GameInfo) -> dict:
    r = deepcopy(reaction)
    junme = (70 - gi.yama) // 4 + 1
    # 直接返回模式
    if gi.n_other_reach() > 0:
        print("others_reached")
        return r
    
    if count_dora(gi.doras_ms, 
                gi.my_tehai + [gi.my_tsumohai] if gi.my_tsumohai else gi.my_tehai, 
                gi.fuuros_ms[gi.self_seat]) >= 2:
        print("self_doras")
        return r
    
    if any(
        count_dora(gi.doras_ms, gi.fuuros_ms[i]) >= 2
        for i in range(4)
        if i != gi.self_seat
    ):
        print("others_doras")
        return r
    
    if (
        any(len(gi.fuuros_ms[i]) >= 9 for i in range(4)) or
        (junme >= 7 and any(len(gi.fuuros_ms[i]) >= 6 for i in range(4)))
    ):
        print("others_fuuro")
        return r
    if (has_renfuu(gi, 'others') or has_renfuu(gi, 'self')):
        print("renfuu")
        return r
    # if "last_direct" in self.mode and ts.compute_rank_deltas[0] == 4:
    #     return r, "last_direct"
    # if "oya_direct" in self.mode and ts.mjai_oya_id == ts.mjai_self_id:
    #     return r, "oya_direct"

    if self_honitsu(gi):
        print("self_honitsu")
        return r
    
    shanten = int(r['meta'].get('shanten', 0))
    if shanten <= 2:
        print("shanten <= 2")
        return r
    
    if shanten >= 4 and is_haipaiori(gi):
        print("is_haipaiori")
        haipaiori(r, gi)
        return r
        
    if ((gi.bakaze == 'S' and gi.kyoku == 4) or gi.bakaze == 'W') and compute_rank_deltas[0] != 1:
        print("S4/W")
        return r
    
    # if gi.bakaze == 'S' and gi.kyoku in (3, 4) and compute_rank_deltas[0] == 3:
    #     print("S3, third place")
    #     return r
        
    if junme <= 6 and len(gi.fuuros_ms[gi.self_seat]) == 0:
        print("反转字牌打出顺序，reverse_honors_discard")
        reverse_honors_discard(r, gi, excl_dora=True, excl_renfuu=True)

    if shanten >= 3 and gi.bakaze != 'E':
        print("half_honors_discard")
        half_honors_discard(r)

    v = self_hand_value(gi)
    # if v >= 2:
    #     print(f"v >= 2: v = {v}")
    #     return r
        
    if junme <= 6:
        if shanten - v >= 5:
            chiitoi_honitsu(r, gi)
            print("chiitoi_honitsu")
            return r

    # 默认策略，3向听或以上时，
    try:
        if shanten - v <= 2 or r.get('type') == 'none':
            print("shanten - v <= 2 or r.get('type') == 'none'")
            return r
        else:
            print("默认策略，3向听或以上时")
            meta_options = r.get('meta_options', [])
            if not meta_options:
                return r

            new_op = sample_top_k(meta_options, in_top_k=5)
            
            if not new_op:
                return r
            
            if new_op in NAKI:
                return r
            elif new_op == 'none':
                r['type'] = 'none'
                return r
            elif len(new_op) == 1 or new_op[0].isdigit():
                r['pai'] = new_op
                return r
            else:
                return r

    except Exception as e:
        LOGGER.error(f"Error in 3shanten+ decision, reaction: {r}, error: {e}")
        return r

