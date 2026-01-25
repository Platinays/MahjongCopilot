# custom/notifier.py

import os
import threading
import time
# import winsound  # plyer 版本不依赖 Windows 音效
from plyer import notification

# ======================
# 通知初始化
# ======================

SOUND_FILE = os.path.join(os.path.dirname(__file__), "notify.wav")


class GameNotifier:
    """
    Mahjong game event notifier (cross-platform).
    - Uses plyer.notification for popups
    - Optional sound alert (Windows only)
    - Can intentionally pause bot for critical events
    """

    def __init__(self, enable_popup=True, enable_sound=True, pause_seconds=5):
        self.enable_popup = enable_popup
        self.enable_sound = enable_sound
        self.pause_seconds = pause_seconds

        # 防止重复触发
        self._last_round_key = None
        self._last_reach_keys = set()

    # ==================================================
    # 新一局开始提醒（东三/东四/南三/南四/西场）
    # ==================================================

    def on_new_round(self, game_state):
        try:
            ks = game_state.kyoku_state
            bakaze = ks.bakaze
            kyoku = ks.kyoku
            honba = ks.honba

            # 把 honba 也纳入，解决连庄不提醒的问题
            round_key = (bakaze, kyoku, honba)
            if round_key == self._last_round_key:
                return
            self._last_round_key = round_key

            # ===== 判断是否需要提醒 =====
            notify_prefix = None
            if bakaze == 'S' and kyoku in (3, 4):
                notify_prefix = '南'
            elif bakaze == 'W':
                notify_prefix = '西'
            # elif bakaze == 'E' and kyoku in (1, 2, 3, 4):
            #     notify_prefix = '东'

            if notify_prefix is None:
                return

            # ===== 自己的排名和点数 =====
            my_rank, my_score = self._my_rank_and_score(game_state)

            title = f"{notify_prefix}{kyoku}局 {honba}本场｜你第{my_rank}名 {my_score}点"
            msg = self._round_message(game_state)  # 内部自动算排名

            self._notify(title, msg)

        except Exception as e:
            # notifier 永远不影响主逻辑
            print(e)
            pass

    # ==================================================
    # 立直提醒（庄家 / 唯一第四）
    # 并在提醒后阻塞 bot
    # ==================================================

    def on_reach(self, actor, game_state):
        try:
            ks = game_state.kyoku_state
            scores = game_state.player_scores
            my_seat = game_state.seat

            # ===== 自己立直，简单提醒 =====
            if actor == my_seat:
                # my_rank, my_score = self._my_rank_and_score(game_state)
                # notify_prefix = {'E': '东', 'S': '南', 'W': '西'}.get(ks.bakaze, '')
                # title = f"你立直了！｜{notify_prefix}{ks.kyoku}局 {ks.honba}本场｜你第{my_rank}名 {my_score}点"
                # msg = self._round_message(game_state, skip_myself=True)  # 只显示其他三家
                # self._notify(title, msg)
                return

            key = (actor, ks.bakaze, ks.kyoku, ks.honba)
            if key in self._last_reach_keys:
                return
            self._last_reach_keys.add(key)

            oya = ks.oya
            ranked = self._rank_by_score(scores, oya)
            last_seat = ranked[-1][0]  # 唯一第四名已经按座次排序

            is_oya = (actor == oya)
            is_last = (actor == last_seat)

            # ===== 东风场差距太小，不提醒第四 =====
            if ks.bakaze == 'E' and is_last:
                max_score = ranked[0][1]
                min_score = ranked[-1][1]
                if max_score - min_score <= 2000:
                    is_last = False  # 不再认为是需要提醒的第四名

            # ===== 标题前缀 =====
            if is_oya and is_last:
                warning_prefix = "第四名庄家立直"
            elif is_oya:
                warning_prefix = "庄家立直警告"
            elif is_last:
                warning_prefix = "第四名立直警告"
            else:
                if not ((ks.bakaze == 'S' and ks.kyoku >= 3) or ks.bakaze == 'W'):
                    return  # 早期局不提醒其他玩家立直
                warning_prefix = "立直警告"

            # ===== 自己的排名和点数 =====
            my_rank, my_score = self._my_rank_and_score(game_state)

            notify_prefix = {'E': '东', 'S': '南', 'W': '西'}.get(ks.bakaze, '')
            title = f"{warning_prefix}｜{notify_prefix}{ks.kyoku}局 {ks.honba}本场｜你第{my_rank}名 {my_score}点"

            # ===== 正文：只显示其他三家 =====
            msg = self._round_message(game_state, skip_myself=True)

            # ===== 发送提醒并阻塞 =====
            self._notify(title, msg)
            time.sleep(self.pause_seconds)

        except Exception:
            # notifier 永远不影响主逻辑
            pass

    # ==================================================
    # 内部辅助函数
    # ==================================================

    def _round_message(self, game_state, skip_myself: bool = True):
        ks = game_state.kyoku_state
        scores = game_state.player_scores
        my_seat = game_state.seat

        ranked = self._rank_by_score(scores, ks.oya)

        parts = []
        for seat, score in ranked:
            if skip_myself and seat == my_seat:
                continue

            name = self._relative_name(my_seat, seat)

            # 标记庄家
            if seat == ks.oya:
                name = f"{name}(庄)"

            parts.append(f"{name}: {score}")

        return " | ".join(parts)

    @staticmethod
    def _rank_by_score(scores, oya):
        """
        根据雀魂规则对4家点数排序：
        - 点数高优先
        - 点数相同则靠近起家优先（顺时针距离越小越靠前）

        返回 [(seat, score), ...] 排序列表
        """
        def distance_to_oya(seat):
            return (seat - oya) % 4

        return sorted(
            enumerate(scores),
            key=lambda x: (-x[1], distance_to_oya(x[0]))
        )

    def _my_rank_and_score(self, game_state):
        """
        返回自己在本局的排名（1~4）和点数。
        同分时按照座位靠近起家顺序排名，越靠近起家位次越高。
        """
        scores = game_state.player_scores
        my_seat = game_state.seat
        oya = game_state.kyoku_state.oya

        ranked = self._rank_by_score(scores, oya)

        my_score = scores[my_seat]
        my_rank = next(i + 1 for i, (s, _) in enumerate(ranked) if s == my_seat)

        return my_rank, my_score

    @staticmethod
    def _relative_name(my_seat, seat):
        """将绝对座次转换为相对称呼"""
        diff = (seat - my_seat) % 4
        return ["自己", "下家", "对面", "上家"][diff]

    # ==================================================
    # 通知与声音
    # ==================================================

    def _play_sound(self):
        # 如果你想在 Windows 上播放声音，可以取消注释
        # if os.path.exists(SOUND_FILE):
        #     winsound.PlaySound(
        #         SOUND_FILE,
        #         winsound.SND_FILENAME | winsound.SND_ASYNC
        #     )
        # else:
        #     winsound.MessageBeep(winsound.MB_ICONASTERISK)
        pass

    def _show_toast(self, title, msg, duration=5):
        # 使用 plyer 跨平台通知
        def show():
            try:
                notification.notify(
                    title=title,
                    message=msg,
                    app_name="MahjongCopilot",
                    timeout=duration
                )
            except Exception:
                pass

        threading.Thread(target=show, daemon=True).start()

    def _notify(self, title, message):
        if not self.enable_popup:
            return

        # 播放声音（可选）
        if self.enable_sound:
            threading.Thread(target=self._play_sound, daemon=True).start()

        try:
            self._show_toast(title, message)
        except Exception:
            pass
