from game.game_state import GameInfo
from common.log_helper import LOGGER
from custom.count_dora import count_dora

def adaptive_n(gi:GameInfo):
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
            dora_count = count_dora(gi.doras_ms, gi.my_tehai + ([gi.my_tsumohai] if gi.my_tsumohai else []), gi.fuuros_ms[gi.self_seat])
            # 双东视同宝牌，亦即相当于北也是宝牌表示牌
            if gi.bakaze == 'E' and gi.self_seat == gi.oya:
                dora_count += count_dora(['N'], gi.my_tehai + ([gi.my_tsumohai] if gi.my_tsumohai else []), gi.fuuros_ms[gi.self_seat])
            n_equiv -= dora_count

            # 根据其他玩家副露中宝牌、红宝牌、双东的数量减少等效向听数
            others_dora_count = 0
            for i in range(4):
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
        LOGGER.debug(
            "无人立直，计算手牌向听数为 %d 向听，第 %d 巡, n 设为 %d, n_equiv 为 %d, max_n 为 %d, 玩家为庄家？ %s, 手牌为 %s, 自摸牌为 %s, 宝牌数为 %d, 宝牌表示牌 %s, 其他玩家总计副露宝牌数（含双东）为 %d, 自身副露为 %s, 所有副露为 %s",
            n_shanten, junme, n, n_equiv, max_n, str(gi.oya == gi.self_seat), gi.my_tehai, gi.my_tsumohai, dora_count, gi.doras_ms, others_dora_count, gi.fuuros_ms[gi.self_seat], gi.fuuros_ms
        )
    else:
        LOGGER.debug("有他人立直，n 设为 0")
        n = 0
    return n