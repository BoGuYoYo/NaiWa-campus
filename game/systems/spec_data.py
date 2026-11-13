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
        "effects": {"energy": -20, "mood": -3, "academic": 5, "rel.npc_chenlang": 2},
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
        "effects": {"energy": -12, "mood": -2, "social": 4, "interest": 1, "rel.npc_sumo": 3},
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
        "role": "社团联合会干事，爱张罗活动，嗓门比谁都大",
        "location": "loc_clubroom",
        "relation_sources": ["join_club", "talk", "semester_event"],
    },
    {
        "id": "npc_chenlang",
        "name": "李振兴",
        "role": "同班同学，学习方向，嘴硬心软的抬杠担当",
        "location": "loc_library",
        "relation_sources": ["library_study", "talk", "semester_event"],
    },
    {
        "id": "npc_xiaoyou",
        "name": "奈珑",
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
        "speaker": "npc_sumo",
        "pages": ["evt.sem_1_club_fair.body.1"],
        "choices": [
            {
                "id": "fair_club",
                "conditions": [],
                "effects": {"rel.npc_sumo": 10},
                "add_flags": ["club_member"],
                "remove_flags": [],
            },
            {
                "id": "fair_lab",
                "conditions": [],
                "effects": {"academic": 4, "rel.npc_chenlang": 10},
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
            {"id": "cram", "conditions": [], "effects": {"academic": 6, "mood": -5},
             "add_flags": [], "remove_flags": []},
            {"id": "steady", "conditions": [], "effects": {"academic": 3},
             "add_flags": [], "remove_flags": []},
            {"id": "relax", "conditions": [], "effects": {"mood": 5},
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
                "id": "library_docs",
                "conditions": [],
                "effects": {"academic": 4, "rel.npc_chenlang": 5},
                "add_flags": [],
                "remove_flags": [],
            },
            {
                "id": "tech_server",
                "conditions": [{"type": "counter", "key": "club_count", "op": ">=", "value": 2}],
                "effects": {"social": 3, "rel.npc_sumo": 10},
                "add_flags": [],
                "remove_flags": [],
            },
            {
                "id": "help_nailong",
                "conditions": [{"type": "rel", "key": "npc_xiaoyou", "op": ">=", "value": 25}],
                "effects": {"interest": 3, "rel.npc_xiaoyou": 10},
                "add_flags": ["helped_nailong"],
                "remove_flags": [],
            },
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
                "id": "library_mock",
                "conditions": [],
                "effects": {"academic": 4, "rel.npc_chenlang": 5},
                "add_flags": [],
                "remove_flags": [],
            },
            {
                "id": "tech_network",
                "conditions": [{"type": "flag", "key": "club_member"}],
                "effects": {"social": 4, "rel.npc_sumo": 8},
                "add_flags": [],
                "remove_flags": [],
            },
            {
                "id": "nailong_chat",
                "conditions": [],
                "effects": {"mood": 6, "rel.npc_xiaoyou": 8},
                "add_flags": [],
                "remove_flags": [],
            },
        ],
    },
    {
        "id": "sem_5_club_election",
        "kind": "semester",
        "semester_no": 5,
        "speaker": "npc_sumo",
        "pages": ["evt.sem_5_club_election.body.1", "evt.sem_5_club_election.body.2"],
        "choices": [
            {
                "id": "tech_project",
                "conditions": [
                    {"type": "flag", "key": "club_member"},
                    {"type": "rel", "key": "npc_sumo", "op": ">=", "value": 45},
                ],
                "effects": {"rel.npc_sumo": 12},
                "add_flags": ["tech_project"],
                "remove_flags": [],
            },
            {
                "id": "kaoyan_books",
                "conditions": [],
                "effects": {"academic": 5, "rel.npc_chenlang": 6},
                "add_flags": [],
                "remove_flags": [],
            },
            {
                "id": "focus_own",
                "conditions": [],
                "effects": {},
                "add_flags": [],
                "remove_flags": [],
            },
        ],
    },
    {
        "id": "sem_6_lab_invite",
        "kind": "semester",
        "semester_no": 6,
        "speaker": "npc_chenlang",
        "pages": ["evt.sem_6_lab_invite.body.1"],
        "choices": [
            {
                "id": "kaoyan_partner",
                "conditions": [
                    {"type": "stat", "key": "academic", "op": ">=", "value": 50},
                    {"type": "rel", "key": "npc_chenlang", "op": ">=", "value": 40},
                ],
                "effects": {"academic": 5, "rel.npc_chenlang": 12},
                "add_flags": ["kaoyan_partner"],
                "remove_flags": [],
            },
            {
                "id": "tech_continue",
                "conditions": [],
                "effects": {"social": 4, "rel.npc_sumo": 8},
                "add_flags": [],
                "remove_flags": [],
            },
            {
                "id": "nailong_time",
                "conditions": [],
                "effects": {"mood": 5, "rel.npc_xiaoyou": 8},
                "add_flags": [],
                "remove_flags": [],
            },
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
                "id": "confess_nailong",
                "conditions": [
                    {"type": "flag", "key": "helped_nailong"},
                    {"type": "rel", "key": "npc_xiaoyou", "op": ">=", "value": 65},
                ],
                "effects": {"mood": 10, "rel.npc_xiaoyou": 15},
                "add_flags": ["confessed_nailong"],
                "remove_flags": [],
            },
            {
                "id": "kaoyan_sprint",
                "conditions": [],
                "effects": {"academic": 6, "rel.npc_chenlang": 8},
                "add_flags": [],
                "remove_flags": [],
            },
            {
                "id": "tech_handover",
                "conditions": [],
                "effects": {"social": 5, "rel.npc_sumo": 8},
                "add_flags": [],
                "remove_flags": [],
            },
            {
                "id": "internship",
                "conditions": [],
                "effects": {"social": 2, "academic": 2},
                "add_flags": [],
                "remove_flags": [],
            },
        ],
    },
    {
        "id": "sem_8_graduation_eve",
        "kind": "semester",
        "semester_no": 8,
        "speaker": None,
        "pages": ["evt.sem_8_graduation_eve.body.1"],
        "choices": [
            {"id": "thesis", "conditions": [], "effects": {"academic": 4},
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
# 5 个结局（B8，按优先级从上到下）
# ---------------------------------------------------------------------------
ENDINGS: list[dict[str, Any]] = [
    {
        "id": "ending_delayed",
        "name": "延毕结局",
        "priority": 1,
        "conditions": [{"type": "stat", "key": "academic", "op": "<", "value": 40}],
        "matched": ["学业低于 40", "毕业资格不足"],
    },
    {
        "id": "ending_kaoyan",
        "name": "考研结局",
        "priority": 2,
        "conditions": [
            {"type": "stat", "key": "academic", "op": ">=", "value": 75},
            {"type": "counter", "key": "library_count", "op": ">=", "value": 10},
            {"type": "rel", "key": "npc_chenlang", "op": ">=", "value": 60},
            {"type": "flag", "key": "kaoyan_partner"},
        ],
        "matched": ["学业 75+", "图书馆学习 10 次以上", "李振兴关系 60+", "考研搭子"],
    },
    {
        "id": "ending_tech_master",
        "name": "技术大牛",
        "priority": 3,
        "conditions": [
            {"type": "stat", "key": "social", "op": ">=", "value": 55},
            {"type": "counter", "key": "club_count", "op": ">=", "value": 10},
            {"type": "rel", "key": "npc_sumo", "op": ">=", "value": 65},
            {"type": "stat", "key": "academic", "op": ">=", "value": 40},
            {"type": "flag", "key": "tech_project"},
        ],
        "matched": ["社交 55+", "参加社团 10 次以上", "符闹吃关系 65+", "学业 40+", "技术项目"],
    },
    {
        "id": "ending_romance_nailong",
        "name": "坠入爱河",
        "priority": 4,
        "conditions": [
            {"type": "rel", "key": "npc_xiaoyou", "op": ">=", "value": 80},
            {"type": "stat", "key": "interest", "op": ">=", "value": 55},
            {"type": "counter_sum", "keys": ["create_count", "games_count"], "op": ">=", "value": 10},
            {"type": "stat", "key": "academic", "op": ">=", "value": 40},
            {"type": "flag", "key": "confessed_nailong"},
        ],
        "matched": ["奈珑关系 80+", "兴趣 55+", "创作与打游戏合计 10 次以上", "学业 40+", "表白成功"],
    },
    {
        "id": "ending_mediocre",
        "name": "平平无奇",
        "priority": 5,
        "conditions": [],
        "matched": ["学业达到毕业线，但没有完成任何专精路线"],
    },
]

# ---------------------------------------------------------------------------
# 5 套固定策略（课堂演示路线）
# ---------------------------------------------------------------------------
STRATEGIES: dict[str, dict[str, Any]] = {
    "kaoyan": {
        "script": ['library_study', 'library_study', 'eat_canteen', 'library_study', 'library_study', 'talk:npc_chenlang', 'library_study', 'attend_class', 'eat_canteen', 'library_study', 'attend_class', 'talk:npc_chenlang', 'library_study', 'library_study', 'eat_canteen', 'library_study', 'attend_class', 'talk:npc_chenlang', 'library_study', 'attend_class', 'eat_canteen', 'library_study', 'talk:npc_chenlang', 'eat_canteen', 'eat_canteen', 'rest_dorm', 'talk:npc_chenlang', 'library_study', 'eat_canteen', 'rest_dorm', 'eat_canteen', 'rest_dorm', 'campus_walk', 'eat_canteen', 'rest_dorm', 'campus_walk', 'eat_canteen', 'rest_dorm', 'campus_walk', 'eat_canteen', 'rest_dorm', 'campus_walk', 'eat_canteen', 'rest_dorm', 'campus_walk', 'rest_dorm', 'rest_dorm', 'rest_dorm'],
        "cycle": ["library_study", "eat_canteen", "rest_dorm"],
        "talk_npc": "npc_chenlang",
        "talk_every": 0,
        "prefs": {1: "fair_lab", 2: "steady", 3: "library_docs", 4: "library_mock",
                  5: "kaoyan_books", 6: "kaoyan_partner", 7: "kaoyan_sprint", 8: "thesis"},
        "expected_ending": "ending_kaoyan",
    },
    "tech_master": {
        "script": ['join_club', 'join_club', 'eat_canteen', 'join_club', 'join_club', 'talk:npc_sumo', 'join_club', 'join_club', 'eat_canteen', 'join_club', 'join_club', 'talk:npc_sumo', 'join_club', 'join_club', 'eat_canteen', 'join_club', 'talk:npc_sumo', 'eat_canteen', 'join_club', 'attend_class', 'eat_canteen', 'attend_class', 'talk:npc_sumo', 'eat_canteen', 'attend_class', 'eat_canteen', 'talk:npc_sumo', 'attend_class', 'eat_canteen', 'rest_dorm', 'attend_class', 'eat_canteen', 'rest_dorm', 'attend_class', 'eat_canteen', 'campus_walk', 'attend_class', 'eat_canteen', 'campus_walk', 'rest_dorm', 'campus_walk', 'rest_dorm', 'rest_dorm', 'campus_walk', 'rest_dorm', 'eat_canteen', 'campus_walk', 'rest_dorm'],
        "cycle": ["join_club", "eat_canteen", "rest_dorm"],
        "talk_npc": "npc_sumo",
        "talk_every": 0,
        "prefs": {1: "fair_club", 2: "steady", 3: "tech_server", 4: "tech_network",
                  5: "tech_project", 6: "tech_continue", 7: "tech_handover", 8: "thesis"},
        "expected_ending": "ending_tech_master",
    },
    "romance_nailong": {
        "script": ['create_work', 'play_games', 'talk:npc_xiaoyou', 'create_work', 'play_games', 'talk:npc_xiaoyou', 'create_work', 'play_games', 'talk:npc_xiaoyou', 'create_work', 'play_games', 'talk:npc_xiaoyou', 'create_work', 'attend_class', 'eat_canteen', 'create_work', 'attend_class', 'eat_canteen', 'play_games', 'attend_class', 'eat_canteen', 'play_games', 'attend_class', 'eat_canteen', 'attend_class', 'eat_canteen', 'rest_dorm', 'attend_class', 'eat_canteen', 'rest_dorm', 'attend_class', 'eat_canteen', 'rest_dorm', 'talk:npc_xiaoyou', 'eat_canteen', 'rest_dorm', 'talk:npc_xiaoyou', 'eat_canteen', 'campus_walk', 'eat_canteen', 'rest_dorm', 'campus_walk', 'rest_dorm', 'campus_walk', 'campus_walk', 'rest_dorm', 'campus_walk', 'campus_walk'],
        "cycle": ["create_work", "play_games", "eat_canteen"],
        "talk_npc": "npc_xiaoyou",
        "talk_every": 0,
        "prefs": {1: "fair_game", 2: "steady", 3: "help_nailong", 4: "nailong_chat",
                  5: "focus_own", 6: "nailong_time", 7: "confess_nailong", 8: "thesis"},
        "expected_ending": "ending_romance_nailong",
    },
    "delayed": {
        "script": ['play_games', 'eat_canteen', 'campus_walk', 'play_games', 'rest_dorm', 'rest_dorm', 'play_games', 'eat_canteen', 'campus_walk', 'play_games', 'rest_dorm', 'rest_dorm', 'play_games', 'eat_canteen', 'campus_walk', 'play_games', 'rest_dorm', 'rest_dorm', 'play_games', 'eat_canteen', 'campus_walk', 'play_games', 'rest_dorm', 'rest_dorm', 'play_games', 'eat_canteen', 'campus_walk', 'play_games', 'rest_dorm', 'rest_dorm', 'play_games', 'eat_canteen', 'campus_walk', 'play_games', 'rest_dorm', 'rest_dorm', 'play_games', 'eat_canteen', 'campus_walk', 'play_games', 'rest_dorm', 'rest_dorm', 'play_games', 'eat_canteen', 'campus_walk', 'play_games', 'rest_dorm', 'rest_dorm'],
        "cycle": ["play_games", "rest_dorm", "campus_walk"],
        "talk_npc": None,
        "talk_every": 0,
        "prefs": {1: "fair_game", 2: "relax", 3: "library_docs", 4: "nailong_chat",
                  5: "focus_own", 6: "nailong_time", 7: "internship", 8: "thesis"},
        "expected_ending": "ending_delayed",
    },
    "mediocre": {
        "script": ['attend_class', 'eat_canteen', 'join_club', 'exercise', 'play_games', 'rest_dorm', 'attend_class', 'eat_canteen', 'join_club', 'exercise', 'play_games', 'rest_dorm', 'attend_class', 'eat_canteen', 'join_club', 'exercise', 'play_games', 'rest_dorm', 'attend_class', 'eat_canteen', 'join_club', 'exercise', 'play_games', 'rest_dorm', 'attend_class', 'eat_canteen', 'join_club', 'exercise', 'play_games', 'rest_dorm', 'attend_class', 'eat_canteen', 'join_club', 'exercise', 'play_games', 'rest_dorm', 'attend_class', 'eat_canteen', 'join_club', 'exercise', 'play_games', 'rest_dorm', 'attend_class', 'eat_canteen', 'join_club', 'exercise', 'play_games', 'rest_dorm'],
        "cycle": ["attend_class", "eat_canteen", "join_club", "exercise", "play_games", "rest_dorm"],
        "talk_npc": None,
        "talk_every": 0,
        "prefs": {1: "fair_club", 2: "steady", 3: "library_docs", 4: "nailong_chat",
                  5: "focus_own", 6: "nailong_time", 7: "internship", 8: "thesis"},
        "expected_ending": "ending_mediocre",
    },
}

STRATEGY_NAMES: tuple[str, ...] = ("kaoyan", "tech_master", "romance_nailong",
                                   "delayed", "mediocre")
