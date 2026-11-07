# 奶娃：大学四年（naiwa_campus）

30 分钟一周目的校园生活养成游戏。工程规格见《任务分工手册 3.0》，本仓库是它的落地实现。

- 引擎：Python 3.12.x 64 位 + Panda3D 1.10.16（游戏逻辑 100% Python）
- 表现：3D 低多边形校园 + 预渲染像素角色卡片（2.5D），内部画布 480×270，最近邻放大
- 流程：4 学年 × 2 学期 × 2 可游玩日 = 16 天，每天 3 个行动时段，共 48 次行动
- 平台：Windows 10 22H2 / Windows 11，64 位

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt

# 主菜单（有窗口）
python -m game

# 直接进校园，跳过开场事件
python -m game --dev --scene CampusScene --skip-intro --seed 42

# 离屏渲染 6 帧并截图（无需显示器，CI 可用）
python -m game --dev --scene CampusScene --skip-intro --offscreen --seed 42 --frames 6
```

`python -m game` 必须能在仓库根目录和 PyInstaller onedir 目录中都能启动；存档与配置写在
`%APPDATA%\NaiwaCampus`，绝不写安装目录。

## 验收命令（A）

```powershell
python -m pytest tests/core tests/standalone_a -m "not gui" -q     # 单元测试
python -m tests.standalone_a --check-save --check-assets --check-flow
python -m tests.standalone_a --check-render                        # 需要图形设备
python -m game --dev --autoplay --offscreen --seed 42              # 脚本化通关冒烟
```

验收产物统一写 `reports/standalone/<岗位>/`（例如 `reports/standalone/A/autoplay.json`）。

## 目录结构

目录名、文件名不得自行增减；括号内是负责人，改动他人文件必须走合并请求。

```text
game/            (A) __main__.py app.py config.py core/（state results flow scene_manager
                     save_manager asset_registry render_pipeline audio event_bus）
game/systems/    (B) 纯 Python 业务规则，禁止 import panda3d / game.ui / game.world
game/world/      (C) 场景、移动、相机、碰撞、交互
game/ui/         (D) 主题、控件、面板、文本
game/sim/        (B) 无图形模拟器
content/         (B/C/D/E) JSON 规则、文本、地图、schema
assets/          (A) manifest.json、LICENSES.csv、characters/ campus/ portraits/ ui/ fonts/ audio/
tools/           (A) make_placeholders.py slice_reference_sheets.py pack_sprites.py gltf_to_bam.py
tests/           (E 框架；B/C/D 各自子目录；A 的 standalone_a)
docs/            接口变更记录、整合记录、美术说明
```

## 已知限制（第 1 周）

- `game/systems`、`game/world`、`game/ui` 尚未合入，A 的 `game/core/flow.py` 会回退到替身服务，
  `game/app.py` 会回退到替身场景（测试地面 + 8 方向角色卡片），日志会打印
  `[FLOW] services: {'activity': 'fallback', ...}`。合入后自动切换为正式实现。
- `assets/fonts/FusionPixel12.ttf` 尚未放入（SIL OFL 1.1，见 `assets/LICENSES.csv` 的 `LIC-0301`）。
  缺失时字体加载返回 `None`，D 的 TextDB 回退引擎默认字体并写 `asset.missing`。
- 角色的行走表与待机表已经是**正式资源**：由 `tools/slice_reference_sheets.py` 从用户提供的
  单方向序列帧（每个方向 8 帧）自动切片、去背、像素化到 48×48（身高 38 像素、脚点 24,46），
  行走表为 384×384 / 8 帧、待机表 144×384 / 3 帧。其余美术与全部音频仍是同尺寸占位资源
  （`LIC-0005`、`LIC-0002~0004`、`LIC-0101` 等）。逐张按 A9 流程重绘后同名替换即可，
  注意 `tools/make_placeholders.py art` 不会覆盖这两张正式精灵表（`FINAL_ASSETS`）。

## 协作约定

- 分支：`main`（仅发布）→ `develop`（每周五 17:00 由 A 合并）→ `feature/<岗位字母>-<主题>`
- 提交信息：`<岗位>(<模块>): <动词开头的描述>`，例如 `B(activity): 增加食堂每日次数上限`
- 公共接口（`game/core` 的数据结构与签名）只能由 A 修改，变更登记在 `docs/CHANGELOG_API.md`
- 合并前必须通过：`python -m pytest -m "not gui"`、两个校验器零错误、附自测输出

## 文档索引

| 文件 | 内容 |
| --- | --- |
| `docs/CHANGELOG_API.md` | 公共接口与引擎陷阱记录（全员必读） |
| `docs/handover_a.md` | A 的交付说明：启动命令、资源清单、已知缺陷、测试入口 |
| `docs/integration/week-1.md` | 第 1 周整合记录 |
| `docs/art/README.md` | 美术规格、占位资源清单、正式素材替换流程 |
| `assets/LICENSES.csv` | 每个资源的许可登记（发布前 `commercial_ok` 必须为 yes） |
