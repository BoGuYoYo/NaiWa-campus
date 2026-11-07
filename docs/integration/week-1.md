# 第 1 周整合记录（week-1）

整合人：开发者 A　　整合时间：2026-01-05 17:00　　标签：`week-1`

## 已合入内容

| 归属 | 内容 | 状态 |
| --- | --- | --- |
| A | 仓库骨架、`.gitignore` / `.gitattributes`（LFS：png/ogg/bam/blend/gltf/字体） | ✅ |
| A | `game/__main__.py`、`app.py`、`config.py`（含 `--dev/--seed/--scene/--spawn/--day/--load/--skip-intro/--windowed/--offscreen/--autoplay/--frames/--screenshot/--inspect/--echo`） | ✅ |
| A | `core/state.py`、`results.py`、`event_bus.py`、`asset_registry.py`、`render_pipeline.py`、`scene_manager.py`、`save_manager.py`、`audio.py`、`flow.py` | ✅ |
| A | 480×270 离屏渲染管线（nearest、正交 film 20×11.25、主相机停用、1/24 米网格对齐、整数倍优先 / 85% 规则回退） | ✅ 实测 1280×720=2.6667 拉伸、1920×1080=4 倍 |
| A | 存档系统（tmp+fsync+replace、`.bak` 回退、`save_version` 迁移、摘要 peek） | ✅ |
| A | 109 条 manifest + `LICENSES.csv`（9 张许可记录） | ✅ |
| A | 占位美术 69 张、音频 16 个（4 BGM + 12 SFX，OGG 44.1k）、低模 23 个 `.bam` | ✅ |
| A | `tools/make_placeholders.py`、`tools/pack_sprites.py`、`tools/gltf_to_bam.py` | ✅ |
| A | `tests/core`（75 用例）、`tests/standalone_a`（独立验收 13 项） | ✅ |
| B/C/D/E | 正式实现、内容 JSON、schema、校验器、打包脚本 | ⬜ 未合入（本周未收到合并请求） |

## 验证结果（本机 Windows 11 + Python 3.12.14 + Panda3D 1.10.16）

```text
python -m pytest tests/core -m "not gui" -q         -> 75 passed
python -m tests.standalone_a --all                  -> 13/13 passed
python -m game --dev --autoplay --offscreen --seed 42
    -> ok, 48 次行动 / 8 个学期事件 / ending_academic / day_index=15
    -> 自动存档 autosave 已生成
python -m game --dev --scene CampusScene --skip-intro --offscreen --frames 12
    -> 480×270 截图，网格 + 建筑占地框 + 角色卡片均正常
```

截图证据：`reports/standalone/A/offscreen.png`、`inspect_8dir.png`（8 方向检视）、
`missing_asset_fallback.png`（删掉 walk.png 后显示品红黑格）、`autoplay.json`。

## 已知问题

1. `game/systems`、`game/world`、`game/ui` 为空，`GameFlow` 使用 A 的替身服务，
   `SceneManager` 使用 A 的替身场景（测试地面）。日志会显示 `fallback`。
2. `assets/fonts/FusionPixel12.ttf` 未放入，`font_ui` 标记 `pending`；缺字体时中文文本无法显示
   （A 的替身场景已改用 ASCII 标签规避）。D 接入 TextDB 后需要真实字体。
3. 除角色的行走/待机两张精灵表外，其余美术仍是占位资源；`LICENSES.csv` 中 `author` 字段已注明来源，
   替换后需更新（角色两张已升级为 `LIC-0001` 正式资源，来源为用户提供的 AI 序列帧）。
4. `tools/gltf_to_bam.py` 尚未用真实 glTF 验证（仓库里还没有 Blender 导出的资源）。
5. 替身场景的 `campus_walk` 互动只演示流程，正式交互由 C 的 `InteractionService` 提供。

## 下周风险

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| B 的服务类构造参数与 A 的 `resolve_services()` 假设不同（需要一个 `state` 参数） | 合入后 `[FLOW] services` 仍显示 fallback | A 在 `resolve_services()` 里已用 `inspect.signature` 判断，无参可实例化；否则请 B 提供无参构造或登记接口变更 |
| C 的 `CampusScene` 名称或构造签名与 `make_scene()` 不一致 | 直接进 `--scene CampusScene` 会抛异常 | 约定场景类 `__init__(self, app, **kwargs)` 且实现 `on_enter/on_exit/on_update`；不一致时 A 在合并评审中拦下 |
| D 依赖 `EventView` 以外的立绘字段 | 事件界面无法显示立绘 | 见 CHANGELOG_API 的 REQ-002 |
| 中文字体缺失导致所有界面出现方块 | 无法演示与录屏 | E 在 `requirements` 安装步骤里加字体下载，或在第 2 周内由 A 提供裁剪后的像素字体 |

## 下周计划（A）

1. 第 2 周：`SceneManager` / `SaveManager` / `GameFlow` 与 C/D 的真实场景联调；补 `settings.json` 菜单项；
   日志轮转（保留 5 份）与 `reports/` 自动归档。
2. 奶娃占位精灵表 → 正式行走/待机（A9 流程，先过比例评审）。
3. 校园白模（5 栋建筑 + 地面）替换 `tools/make_placeholders.py` 生成的白模。
