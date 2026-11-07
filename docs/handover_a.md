# A 交付说明（交接给 E）

交付人：开发者 A（技术负责人／项目整合／全部美术音频）
交付时间：2026-01-05　对应标签：`week-1`
代码状态：`game/core`、`game/app.py`、`game/config.py` 完成并可独立运行；B/C/D 目录为空。

## 1. 启动命令

| 场景 | 命令 |
| --- | --- |
| 主菜单（窗口 1280×720） | `python -m game` |
| 直接进校园（跳过开场） | `python -m game --dev --scene CampusScene --skip-intro --seed 42` |
| 指定天数/地点 | `python -m game --dev --scene CampusScene --skip-intro --day 7 --spawn loc_library` |
| 读档启动 | `python -m game --load slot_1` |
| 无窗口渲染 + 截图 | `python -m game --dev --scene CampusScene --skip-intro --offscreen --frames 6 --screenshot reports/standalone/A/offscreen.png` |
| 8 方向角色检视（A-09） | `python -m game --dev --scene CampusScene --skip-intro --inspect` （运行时 F4 开关） |
| 脚本化通关冒烟 | `python -m game --dev --autoplay --offscreen --seed 42` |
| 独立验收 | `python -m tests.standalone_a --all` |

打包目录（PyInstaller onedir）中同样执行 `python -m game` 或直接运行 exe；资源通过
`config.resource_root()` 解析到 `sys._MEIPASS`，存档/设置写到 `%APPDATA%\NaiwaCampus`。

## 2. 资源清单

- `assets/manifest.json`：109 条（sprite_sheet 5 / image 64 / model 23 / font 1 / music 4 / sound 12）
- `assets/LICENSES.csv`：9 条许可记录，全部 `commercial_ok=yes`；`LIC-0301` 的字体文件尚未放入（标记 `pending`）
- 自检命令：`python tools/make_placeholders.py check` → `assets=109 missing=0 unlicensed=0`
- 关键资源：`char_naiwan_walk`（192×384）、`char_naiwan_idle`（144×384）、`char_shadow`（24×8）、
  `ui_panel_9slice`（48×48，边距 16）、`palette`（32 色）、4 首 BGM + 12 个音效（OGG）
- 全部为同尺寸资源；`char_naiwan_walk` / `char_naiwan_idle` 已是从用户提供的 8 方向序列帧切出的
  **正式资源**（`tools/slice_reference_sheets.py`，见 `docs/art/README.md`），其余为占位/白模/合成音频，
  替换流程见 `docs/art/README.md`

## 3. 测试入口

```powershell
python -m pytest tests/core tests/standalone_a -m "not gui" -q   # 75 passed
python -m tests.standalone_a --check-save --check-assets --check-flow
python -m tests.standalone_a --check-render                       # 需要图形设备
python -m game --dev --autoplay --offscreen --seed 42             # 通关冒烟
```

验收产物：`reports/standalone/A/`
- `standalone_report.json`：13 项独立验收结果
- `autoplay.json`：48 次行动、8 个学期事件、`ending_academic`、`day_index=15`
- `offscreen.png` / `inspect_8dir.png` / `missing_asset_fallback.png`：截图证据

## 4. 验收矩阵（手册 A-01～A-06、A-ST-01～A-ST-05）

| 编号 | 操作 | 结果 |
| --- | --- | --- |
| A-01 | 干净环境 `pip install -r requirements.txt` 后 `python -m game` | ✅ 进入主菜单；日志 `[BOOT] ... root=source`，不出现本机绝对路径 |
| A-02 | 删除 `assets/characters/naiwan/walk.png` 再进校园 | ✅ 显示品红黑格；日志 `[ASSET] missing id=char_naiwan_walk path=characters/naiwan/walk.png hint=检查 manifest 与文件名大小写`（见 `missing_asset_fallback.png`） |
| A-03 | 第 3 天第 2 时段存 `slot_2`，重启读档 | ✅ 日期/5 属性/精力/关系/旗标/位置一致（`test_save_manager.py` + `A-ST-03a`） |
| A-04 | autosave 写入期间强杀进程 | ✅ 原子写入：tmp+fsync+replace，`.bak` 回退（`A-ST-03b`） |
| A-05 | 1280×720 与 1920×1080 截图 | ✅ 1080p 为 4 倍整数放大（4096 逻辑像素 → 1920），720p 按 2.6667 拉伸并居中；最近邻过滤（`A-ST-04b`） |
| A-06 | `--dev --seed 42` 跑完整一周目 | ✅ 冒烟结果 `campus → event → … → graduation`，`phase` 终态 `finished`；`play_seconds` 仅非暂停累计 |
| A-ST-01 | 无 `content/rules` 运行 `--dev --offscreen` | ✅ 主菜单可用，退出码 0 |
| A-ST-02 | 删 fixture PNG 后启动 | ✅ 品红黑格 + `asset.missing` 事件（`A-ST-02c`） |
| A-ST-03 | 损坏 JSON 存档 | ✅ `.bak` 回退或返回 `E_SAVE_CORRUPT`，不覆盖备份（`A-ST-03b/c`） |
| A-ST-04 | 6 帧离屏渲染 | ✅ 480×270 PNG，magfilter=`FT_nearest`（`A-ST-04b`） |
| A-ST-05 | 场景切换 + Esc 暂停 | ✅ `MainMenu→CampusScene→PauseMenu→CampusScene`，`GameState` 完整保留（`A-ST-05`） |

## 5. 已知缺陷

1. **字体缺失**：`assets/fonts/FusionPixel12.ttf` 未放入，中文文本无法渲染（Panda 会打
   `No definition ... for character`）。A 的替身场景已改 ASCII 标签规避，D 接入后必须补字体。
2. **替身服务**：`game/systems/*`、`game/world/*`、`game/ui/*` 未合入时，`GameFlow` 使用
   `Fallback*Service`（数值仅用于跑通流程，不代表平衡），`SceneManager` 使用替身场景。
3. **模型为白模**：23 个 `.bam` 由程序生成（立方体/盒子），只保证尺寸、命名与三角面预算，
   正式模型需按 `tools/gltf_to_bam.py` 流程替换。
4. **头像与插图仍是占位**：`portrait_naiwan_*`（8 张）与 `cg_naiwan_*`（9 张）标记 `LIC-0005`，
   需要用现有角色的正式帧放大派生或重新绘制后再解除占位。
4. **`tools/gltf_to_bam.py` 未用真实 glTF 验证**（仓库内暂无 Blender 导出物），代码路径与
   错误提示已就绪。
5. **音频为合成占位**：BGM 为 numpy 合成循环，响度按 -16 dBFS 归一，正式作曲替换前仅内部使用。
6. 窗口模式在无显示器环境无法启动（Panda3D 需要 GL 上下文），CI 请用 `--offscreen`。

## 6. 给 E 的注意事项

- `pytest.ini` 已声明 `gui` / `slow` 标记；A 的 core 测试全部可在无窗口环境运行
  （`game.core` 不在导入期依赖 panda3d）。
- `AssetRegistry.release_blockers()` 可直接用于构建拦截：返回非空列表即表示存在
  `commercial_ok != yes` 或缺 `license_id` 的资源。
- 离屏截图统一走 `LowResPipeline.save_buffer_screenshot()`，不要自己调 `win.getScreenshot()`
  （1.10 返回 `Texture`，1.11 返回 `PNMImage`，已内部兼容）。
- 若打包后启动失败，先确认 `textures-power-2 none`、`textures-power-2` 相关的 PRC 未被覆盖，
  再检查 `Filename.fromOsSpecific` 是否被替换成裸 `str`（这两点是 1.10.16 上踩过的坑）。
- 需要 A 配合的格式：`reports/standalone/A/` 下的 JSON 结构固定，可直接被汇总脚本读取。
