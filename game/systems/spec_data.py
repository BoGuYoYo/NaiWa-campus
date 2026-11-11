"""全部数值的唯一来源（开发者 B）。

规则与数值均取自《任务分工手册 3.0 · 任务 B》B1～B9 各表。运行期以
`content/rules/*.json` 为准，`python -m game.systems.spec_export` 负责把本文件
导出成这些 JSON；两者的一致性由 tests/systems/test_spec_sync.py 守护。

约定：
    * 效果键只允许 academic / stamina / social / interest / mood / energy / rel.<npc_id>
    * 条件格式见 conditions.py：stat / mood / energy / counter / rel / flag / not_flag / semester / any
    * 任何数值改动都必须同步本文件、content/rules/*.json 与 docs/balance_report.md
"""

from __future__ import annotations

from typing import Any

from game.core.state import NPC_IDS as _CORE_NPC_IDS

# ---------------------------------------------------------------------------
# 流程规模与初始值（B1 / B2）
# ---------------------------------------------------------------------------
TOTAL_DAYS = 16  # 4 年 × 2 学期 × 2 可游玩日
SLOTS_PER_DAY = 3
START_LOCATION = "loc_gate"
START_POS = (40.0, 5.0)
START_FACING = "n"

INITIAL_STATS: dict[str, int] = {"academic": 10, "stamina": 20, "social": 10, "interest": 10}
INITIAL_MOOD = 60
STAT_RANGE = (0, 100)
ENERGY_BASE = 80
ENERGY_PER_STAMINA = 5
# 初始精力等于上限（80 + 体力 // 5），不写死 84，避免初始体力改动后两处分裂
INITIAL_ENERGY: int = ENERGY_BASE + INITIAL_STATS["stamina"] // ENERGY_PER_STAMINA

# 日结算参数
LOW_ENERGY_THRESHOLD = 20
LOW_ENERGY_MOOD_PENALTY = 5
DAILY_ENERGY_RECOVERY = 40
LATE_NIGHT_RECOVERY_PENALTY = 20
LATE_NIGHT_FLAG = "stayed_up_late"

# 心情低于该值时，上课与图书馆学习的学业收益减半（向下取整）
LOW_MOOD_THRESHOLD = 30

# ---------------------------------------------------------------------------
# 错误码（手册第 7 节）
# ---------------------------------------------------------------------------
E_NO_SLOT = "E_NO_SLOT"
E_LOW_ENERGY = "E_LOW_ENERGY"
E_DAILY_LIMIT = "E_DAILY_LIMIT"
E_ALREADY_TALKED = "E_ALREADY_TALKED"
E_WRONG_PHASE = "E_WRONG_PHASE"
E_UNKNOWN_ID = "E_UNKNOWN_ID"
E_CHOICE_LOCKED = "E_CHOICE_LOCKED"

ERROR_TEXT_IDS: dict[str, str] = {
    E_NO_SLOT: "err.no_slot",
    E_LOW_ENERGY: "err.low_energy",
    E_DAILY_LIMIT: "err.daily_limit",
    E_ALREADY_TALKED: "err.already_talked",
    E_WRONG_PHASE: "err.wrong_phase",
    E_UNKNOWN_ID: "err.unknown_id",
    E_CHOICE_LOCKED: "err.choice_locked",
}

# ---------------------------------------------------------------------------
# 9 个活动（B3）
# ---------------------------------------------------------------------------
ACTIVITIES: list[dict[str, Any]] = [
    {
        "id": "attend_class",
        "name": "上课",
        "location": "loc_classroom",
        "effects": {"energy": -15, "mood": -4, "academic": 4, "interest": 1},
        "counter": "class_count",
        "daily_limit": None,
        "halve_academic_on_low_mood": True,
        "late_flag_on_daily_count": None,
        "flag_when_counter": None,
        "random_daily_event": False,
    },
    {
        "id": "library_study",
        "name": "图书馆学习",
        "location": "loc_library",
        "effects": {"energy": -20, "mood": -3, "academic": 5, "rel.npc_sumo": 2},
        "counter": "library_count",
        "daily_limit": None,
        "halve_academic_on_low_mood": True,
        "late_flag_on_daily_count": None,
        "flag_when_counter": None,
        "random_daily_event": False,
    },
    {
        "id": "play_games",
        "name": "打游戏",
        "location": "loc_clubroom",
        "effects": {"energy": -8, "mood": 8, "interest": 3, "rel.npc_xiaoyou": 2},
        "counter": "games_count",
        "daily_limit": None,
        "halve_academic_on_low_mood": False,
        "late_flag_on_daily_count": {"count": 3, "flag": "stayed_up_late"},
        "flag_when_counter": None,
        "random_daily_event": False,
    },
    {
        "id": "create_work",
        "name": "创作",
        "location": "loc_clubroom",
        "effects": {"energy": -15, "mood": 1, "interest": 4, "rel.npc_xiaoyou": 2},
        "counter": "create_count",
        "daily_limit": None,
        "halve_academic_on_low_mood": False,
        "late_flag_on_daily_count": None,
        "flag_when_counter": None,
        "random_daily_event": False,
    },
    {
        "id": "join_club",
        "name": "参加社团",
        "location": "loc_clubroom",
        "effects": {"energy": -12, "mood": -2, "social": 4, "interest": 1, "rel.npc_chenlang": 3},
        "counter": "club_count",
        "daily_limit": None,
        "halve_academic_on_low_mood": False,
        "late_flag_on_daily_count": None,
        "flag_when_counter": {"counter": "club_count", "at_least": 3, "flag": "club_member"},
        "random_daily_event": False,
    },
    {
        "id": "exercise",
        "name": "操场锻炼",
        "location": "loc_playground",
        "effects": {"energy": -18, "mood": 4, "stamina": 4},
        "counter": "exercise_count",
        "daily_limit": None,
        "halve_academic_on_low_mood": False,
        "late_flag_on_daily_count": None,
        "flag_when_counter": None,
        "random_daily_event": False,
    },
    {
        "id": "eat_canteen",
        "name": "食堂用餐",
        "location": "loc_canteen",
        "effects": {"energy": 25, "mood": 4, "stamina": 1},
        "counter": "meal_count",
        "daily_limit": 2,
        "halve_academic_on_low_mood": False,
        "late_flag_on_daily_count": None,
        "flag_when_counter": None,
        "random_daily_event": False,
    },
    {
        "id": "rest_dorm",
        "name": "宿舍休息",
        "location": "loc_dorm",
        "effects": {"energy": 35, "mood": 3},
        "counter": "rest_count",
        "daily_limit": None,
        "halve_academic_on_low_mood": False,
        "late_flag_on_daily_count": None,
        "flag_when_counter": None,
        "random_daily_event": False,
    },
    {
        "id": "campus_walk",
        "name": "校园闲逛",
        "location": "loc_plaza",
        "effects": {"energy": -5, "mood": 5},
        "counter": "walk_count",
        "daily_limit": None,
        "halve_academic_on_low_mood": False,
        "late_flag_on_daily_count": None,
        "flag_when_counter": None,
        "random_daily_event": True,
    },
]

ACTIVITY_IDS: tuple[str, ...] = tuple(a["id"] for a in ACTIVITIES)

# ---------------------------------------------------------------------------
# 交谈与关系（B4）
# ---------------------------------------------------------------------------
TALK_EFFECTS: dict[str, int] = {"energy": -5, "mood": 2, "social": 2}
TALK_RELATION_GAIN = 6
TALK_REQUIRED_ENERGY = 5
REL_EVENT_BONUS = 5

REL_STAGES: list[dict[str, Any]] = [
    {"stage": 1, "threshold": 20, "min_semester": 2, "require_flag": None},
    {"stage": 2, "threshold": 45, "min_semester": 4, "require_flag": "{npc_id}_stage1"},
    {"stage": 3, "threshold": 70, "min_semester": 6, "require_flag": "{npc_id}_stage2"},
]

NPCS: list[dict[str, Any]] = [
    {
        "id": "npc_sumo",
        "name": "符闹吃",
        "role": "同班同学，学习方向，嘴硬心软的抬杠担当",
        "location": "loc_library",
        "relation_sources": ["library_study", "talk", "semester_event"],
    },
    {
        "id": "npc_chenlang",
        "name": "李振兴",
        "role": "社团联合会干事，爱张罗活动的壮汉",
        "location": "loc_clubroom",
        "relation_sources": ["join_club", "talk", "semester_event"],
    },
    {
        "id": "npc_xiaoyou",
        "name": "小柚",
        "role": "隔壁专业同学，兴趣方向",
        "location": "loc_canteen",
        "relation_sources": ["play_games", "create_work", "talk", "semester_event"],
    },
]

NPC_IDS: tuple[str, ...] = _CORE_NPC_IDS
"""NPC ID 的唯一来源是 `game.core.state`（依赖方向 core ← systems）。"""

if tuple(n["id"] for n in NPCS) != NPC_IDS:  # pragma: no cover - 配置写错才会触发
    raise RuntimeError(
        "spec_data.NPCS 的 id 顺序与 game.core.state.NPC_IDS 不一致："
        f"{tuple(n['id'] for n in NPCS)} != {NPC_IDS}"
    )

# ---------------------------------------------------------------------------
# 8 个学期事件（B5）
# ---------------------------------------------------------------------------
SEMESTER_EVENTS: list[dict[str, Any]] = [
    {
        "id": "sem_1_club_fair",
        "kind": "semester",
        "semester_no": 1,
        "speaker": "npc_chenlang",
        "pages": ["evt.sem_1_club_fair.body.1"],
        "choices": [
            {
                "id": "fair_club",
                "conditions": [],
                "effects": {"social": 4, "rel.npc_chenlang": 10},
                "add_flags": ["club_member"],
                "remove_flags": [],
            },
            {
                "id": "fair_lab",
                "conditions": [],
                "effects": {"academic": 4, "rel.npc_sumo": 10},
                "add_flags": ["lab_visited"],
                "remove_flags": [],
            },
            {
                "id": "fair_game",
                "conditions": [],
                "effects": {"interest": 4, "rel.npc_xiaoyou": 10},
                "add_flags": ["game_circle"],
                "remove_flags": [],
            },
        ],
    },
    {
        "id": "sem_2_first_exam",
        "kind": "semester",
        "semester_no": 2,
        "speaker": None,
        "pages": ["evt.sem_2_first_exam.body.1"],
        "choices": [
            {"id": "cram", "conditions": [], "effects": {"academic": 6, "mood": -6},
             "add_flags": [], "remove_flags": []},
            {"id": "steady", "conditions": [], "effects": {"academic": 3, "mood": 3},
             "add_flags": [], "remove_flags": []},
            {"id": "relax", "conditions": [], "effects": {"mood": 8, "interest": 2},
             "add_flags": [], "remove_flags": []},
        ],
    },
    {
        "id": "sem_3_art_contest",
        "kind": "semester",
        "semester_no": 3,
        "speaker": "npc_xiaoyou",
        "pages": ["evt.sem_3_art_contest.body.1"],
        "choices": [
            {
                "id": "submit_art",
                "conditions": [{"type": "counter", "key": "create_count", "op": ">=", "value": 2}],
                "effects": {"interest": 5},
                "add_flags": ["art_submitted"],
                "remove_flags": [],
            },
            {"id": "help_friend", "conditions": [], "effects": {"social": 4, "rel.npc_xiaoyou": 8},
             "add_flags": [], "remove_flags": []},
            {"id": "skip", "conditions": [], "effects": {"mood": 3},
             "add_flags": [], "remove_flags": []},
        ],
    },
    {
        "id": "sem_4_sports_meet",
        "kind": "semester",
        "semester_no": 4,
        "speaker": None,
        "pages": ["evt.sem_4_sports_meet.body.1"],
        "choices": [
            {
                "id": "run_race",
                "conditions": [{"type": "stat", "key": "stamina", "op": ">=", "value": 30}],
                "effects": {"stamina": 6, "mood": 4},
                "add_flags": ["sports_star"],
                "remove_flags": [],
            },
            {"id": "cheer", "conditions": [], "effects": {"social": 4, "mood": 3},
             "add_flags": [], "remove_flags": []},
            {"id": "study_hall", "conditions": [], "effects": {"academic": 4},
             "add_flags": [], "remove_flags": []},
        ],
    },
    {
        "id": "sem_5_club_election",
        "kind": "semester",
        "semester_no": 5,
        "speaker": "npc_chenlang",
        "pages": ["evt.sem_5_club_election.body.1", "evt.sem_5_club_election.body.2"],
        "choices": [
            {
                "id": "run_election",
                "conditions": [
                    {"type": "flag", "key": "club_member"},
                    {"type": "stat", "key": "social", "op": ">=", "value": 35},
                ],
                "effects": {"social": 5, "rel.npc_chenlang": 10},
                "add_flags": ["ran_for_president"],
                "remove_flags": [],
            },
            {"id": "support", "conditions": [], "effects": {"social": 3, "rel.npc_chenlang": 5},
             "add_flags": [], "remove_flags": []},
            {"id": "decline", "conditions": [], "effects": {"mood": 3},
             "add_flags": [], "remove_flags": []},
        ],
    },
    {
        "id": "sem_6_lab_invite",
        "kind": "semester",
        "semester_no": 6,
        "speaker": "npc_sumo",
        "pages": ["evt.sem_6_lab_invite.body.1"],
        "choices": [
            {
                "id": "accept_lab",
                "conditions": [{"type": "stat", "key": "academic", "op": ">=", "value": 45}],
                "effects": {"academic": 6, "mood": -3, "rel.npc_sumo": 8},
                "add_flags": ["accepted_lab"],
                "remove_flags": [],
            },
            {"id": "team_project", "conditions": [], "effects": {"social": 3, "academic": 2},
             "add_flags": [], "remove_flags": []},
            {"id": "decline", "conditions": [], "effects": {"mood": 4},
             "add_flags": [], "remove_flags": []},
        ],
    },
    {
        "id": "sem_7_final_project",
        "kind": "semester",
        "semester_no": 7,
        "speaker": None,
        "pages": ["evt.sem_7_final_project.body.1"],
        "choices": [
            {
                "id": "game_jam",
                "conditions": [{"type": "counter", "key": "games_count", "op": ">=", "value": 4}],
                "effects": {"interest": 6, "rel.npc_xiaoyou": 6},
                "add_flags": ["joined_game_jam"],
                "remove_flags": [],
            },
            {
                "id": "exhibition",
                "conditions": [{"type": "counter", "key": "create_count", "op": ">=", "value": 4}],
                "effects": {"interest": 6},
                "add_flags": ["held_exhibition"],
                "remove_flags": [],
            },
            {"id": "internship", "conditions": [], "effects": {"social": 4, "academic": 2},
             "add_flags": ["internship"], "remove_flags": []},
        ],
    },
    {
        "id": "sem_8_graduation_eve",
        "kind": "semester",
        "semester_no": 8,
        "speaker": None,
        "pages": ["evt.sem_8_graduation_eve.body.1"],
        "choices": [
            {"id": "thesis", "conditions": [], "effects": {"academic": 5},
             "add_flags": [], "remove_flags": []},
            {"id": "party", "conditions": [], "effects": {"social": 4, "mood": 6},
             "add_flags": [], "remove_flags": []},
            {"id": "project", "conditions": [], "effects": {"interest": 5},
             "add_flags": [], "remove_flags": []},
        ],
    },
]

SEMESTER_EVENT_BY_NO: dict[int, str] = {e["semester_no"]: e["id"] for e in SEMESTER_EVENTS}

# ---------------------------------------------------------------------------
# 12 个日常事件（B6，数组顺序即 rng.choice 的抽样顺序，禁止重排）
# ---------------------------------------------------------------------------
DAILY_EVENTS: list[dict[str, Any]] = [
    {"id": "daily_lost_cat", "title": "迷路的小猫", "effects": {"mood": 3}},
    {"id": "daily_free_snack", "title": "学长塞来的零食", "effects": {"energy": 10}},
    {"id": "daily_sudden_rain", "title": "突然下雨", "effects": {"mood": -2, "stamina": 1}},
    {"id": "daily_street_music", "title": "广场上的吉他声", "effects": {"interest": 2}},
    {"id": "daily_found_notes", "title": "捡到一本笔记", "effects": {"academic": 2}},
    {"id": "daily_club_flyer", "title": "发传单的社团", "effects": {"social": 2}},
    {"id": "daily_sunset", "title": "操场上的夕阳", "effects": {"mood": 4}},
    {"id": "daily_bike_ride", "title": "绕校园骑一圈车", "effects": {"stamina": 2}},
    {"id": "daily_wrong_room", "title": "走错教室", "effects": {"academic": 1, "mood": 1}},
    {"id": "daily_photo_help", "title": "帮游客拍合照", "effects": {"social": 1, "mood": 2}},
    {"id": "daily_vending_luck", "title": "售货机多掉一瓶", "effects": {"mood": 3, "energy": 5}},
    {"id": "daily_old_friend", "title": "遇到高中同学", "effects": {"social": 2, "mood": 2}},
]

DAILY_EVENT_CHANCE = 0.5

# ---------------------------------------------------------------------------
# 关系事件（B4）：手册只冻结了 9 个 ID 与触发条件，正文与选项由 B 补写。
# 触发时已经 +5 关系，因此事件本身不再重复加关系。
# ---------------------------------------------------------------------------
def _build_relation_events() -> list[dict[str, Any]]:
    """每名 NPC 三段关系事件；关系 +5 在触发时已结算，事件本身只做展示。"""
    events: list[dict[str, Any]] = []
    for npc_id in NPC_IDS:
        for stage in (1, 2, 3):
            events.append(
                {
                    "id": f"rel_{npc_id}_{stage}",
                    "kind": "relationship",
                    "npc_id": npc_id,
                    "stage": stage,
                    "speaker": npc_id,
                    "pages": [f"evt.rel_{npc_id}_{stage}.body.1"],
                    "choices": [
                        {
                            "id": "continue",
                            "conditions": [],
                            "effects": {},
                            "add_flags": [],
                            "remove_flags": [],
                        }
                    ],
                }
            )
    return events


RELATION_EVENTS: list[dict[str, Any]] = _build_relation_events()

STORY_EVENTS: list[dict[str, Any]] = [
    {
        "id": "story_opening",
        "kind": "story",
        "semester_no": 0,
        "speaker": None,
        "pages": ["evt.story_opening.body.1"],
        "choices": [
            {"id": "begin", "conditions": [], "effects": {}, "add_flags": [], "remove_flags": []}
        ],
    }
]

# ---------------------------------------------------------------------------
# 6 个结局（B8，按优先级从上到下）
# ---------------------------------------------------------------------------
ENDINGS: list[dict[str, Any]] = [
    {
        "id": "ending_academic",
        "name": "学术研究",
        "priority": 1,
        "conditions": [
            {"type": "stat", "key": "academic", "op": ">=", "value": 70},
            {"type": "counter", "key": "library_count", "op": ">=", "value": 10},
            {"type": "flag", "key": "accepted_lab"},
        ],
        "matched": ["学业 70+", "图书馆学习 10 次以上", "加入课题组"],
    },
    {
        "id": "ending_club_leader",
        "name": "社团领袖",
        "priority": 2,
        "conditions": [
            {"type": "stat", "key": "social", "op": ">=", "value": 60},
            {"type": "counter", "key": "club_count", "op": ">=", "value": 10},
            {"type": "rel", "key": "npc_chenlang", "op": ">=", "value": 60},
            {"type": "flag", "key": "ran_for_president"},
        ],
        "matched": ["社交 60+", "参加社团 10 次以上", "李振兴关系 60+", "参加社长竞选"],
    },
    {
        "id": "ending_creator",
        "name": "独立创作者",
        "priority": 3,
        "conditions": [
            {"type": "stat", "key": "interest", "op": ">=", "value": 60},
            {"type": "counter", "key": "create_count", "op": ">=", "value": 8},
            {"type": "flag", "key": "held_exhibition"},
        ],
        "matched": ["兴趣 60+", "创作 8 次以上", "举办个人作品展"],
    },
    {
        "id": "ending_digital",
        "name": "数字内容方向",
        "priority": 4,
        "conditions": [
            {"type": "stat", "key": "interest", "op": ">=", "value": 60},
            {"type": "counter", "key": "games_count", "op": ">=", "value": 10},
            {"type": "flag", "key": "joined_game_jam"},
        ],
        "matched": ["兴趣 60+", "打游戏 10 次以上", "参加游戏创作马拉松"],
    },
    {
        "id": "ending_vibrant",
        "name": "活力生活家",
        "priority": 5,
        "conditions": [
            {"type": "stat", "key": "stamina", "op": ">=", "value": 55},
            {"type": "stat", "key": "social", "op": ">=", "value": 40},
            {"type": "mood", "op": ">=", "value": 70},
            {"type": "counter", "key": "exercise_count", "op": ">=", "value": 10},
        ],
        "matched": ["体力 55+", "社交 40+", "心情 70+", "操场锻炼 10 次以上"],
    },
    {
        "id": "ending_balanced",
        "name": "平衡毕业生",
        "priority": 6,
        "conditions": [],
        "matched": ["没有走上任何专精路线，但四年顺利毕业"],
    },
]

# ---------------------------------------------------------------------------
# 6 套固定策略（B9）
# ---------------------------------------------------------------------------
STRATEGIES: dict[str, dict[str, Any]] = {
    "academic": {
        "cycle": ["library_study", "attend_class", "library_study", "eat_canteen",
                  "library_study", "rest_dorm"],
        "talk_npc": "npc_sumo",
        "talk_every": 7,
        "prefs": {1: "fair_lab", 2: "cram", 4: "study_hall", 6: "accept_lab",
                  7: "internship", 8: "thesis"},
        "expected_ending": "ending_academic",
    },
    "club_leader": {
        "cycle": ["join_club", "join_club", "eat_canteen", "attend_class",
                  "join_club", "rest_dorm"],
        "talk_npc": "npc_chenlang",
        "talk_every": 5,
        "prefs": {1: "fair_club", 4: "cheer", 5: "run_election", 6: "team_project",
                  7: "internship", 8: "party"},
        "expected_ending": "ending_club_leader",
    },
    "creator": {
        "cycle": ["create_work", "create_work", "eat_canteen", "attend_class",
                  "create_work", "rest_dorm"],
        "talk_npc": "npc_xiaoyou",
        "talk_every": 9,
        "prefs": {1: "fair_game", 2: "relax", 3: "submit_art", 7: "exhibition", 8: "project"},
        "expected_ending": "ending_creator",
    },
    "digital": {
        "cycle": ["play_games", "attend_class", "play_games", "create_work",
                  "play_games", "eat_canteen"],
        "talk_npc": "npc_xiaoyou",
        "talk_every": 9,
        "prefs": {1: "fair_game", 2: "relax", 7: "game_jam", 8: "project"},
        "expected_ending": "ending_digital",
    },
    "vibrant": {
        "cycle": ["exercise", "join_club", "eat_canteen", "exercise", "campus_walk", "exercise"],
        "talk_npc": "npc_chenlang",
        "talk_every": 6,
        "prefs": {1: "fair_club", 2: "relax", 4: "run_race", 5: "support", 8: "party"},
        "expected_ending": "ending_vibrant",
    },
    "balanced": {
        "cycle": ["attend_class", "eat_canteen", "join_club", "exercise",
                  "play_games", "rest_dorm"],
        "talk_npc": None,
        "talk_every": 0,
        "prefs": {},
        "expected_ending": "ending_balanced",
    },
}

STRATEGY_NAMES: tuple[str, ...] = ("academic", "club_leader", "creator", "digital",
                                   "vibrant", "balanced")
