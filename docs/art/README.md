# 美术与音频规格说明（A 维护）

## 1. 全局规格

| 项目 | 规定 |
| --- | --- |
| 像素密度 | 每米 24 像素，场景纹理与角色共用，禁止混用 |
| 调色板 | `assets/palette.png`，32 色，`tools/make_placeholders.py` 的 `PALETTE` 是唯一来源 |
| 描边 | 角色/NPC 1 像素，颜色 `#2B2235`；场景物体不描边 |
| 方向顺序 | `s se e ne n nw w sw`（s 表示面朝镜头） |
| 角色帧 | 48×48，脚点 pivot `(24,46)`，身高约 38 像素（≈1.6 米） |
| 文件格式 | PNG RGBA 8 位，透明像素 RGB 置 0，禁止嵌入色彩配置 |
| 阴影 | `char_shadow` 24×8 椭圆，黑色 40% 不透明度，是唯一允许半透明的贴图 |
| 模型 | Blender 4.x → glTF 2.0 → `tools/gltf_to_bam.py`；单栋建筑 ≤ 800 三角面，室外 ≤ 30,000 |
| 模型纹理 | 边长 2 的幂（64～512），最近邻，不生成 mipmap |
| 音频 | BGM：OGG Vorbis 44.1kHz 立体声、60～120 秒可无缝循环、约 -16 LUFS；SFX：单声道，峰值 ≤ -3 dBFS |

## 2. 当前资源状态（第 1 周）

全部资源都是**同尺寸占位资源**，由 `tools/make_placeholders.py` 程序生成：

```powershell
python tools/make_placeholders.py art       # 69 张 PNG
python tools/make_placeholders.py audio     # 4 BGM + 12 SFX（需要 numpy + ffmpeg）
python tools/make_placeholders.py models    # 23 个 .bam（需要 panda3d）
python tools/make_placeholders.py manifest  # 重写 manifest.json 与 LICENSES.csv
python tools/make_placeholders.py check     # 校验 manifest / 文件 / 许可三者一致
```

清单（与 `assets/manifest.json` 一致，共 109 条）：

| 类别 | 数量 | 规格 |
| --- | --- | --- |
| `char_naiwan_walk` | 1 | 192×384，4 帧 × 8 方向，8 fps |
| `char_naiwan_idle` | 1 | 144×384，3 帧 × 8 方向，3 fps |
| `char_shadow` | 1 | 24×8 |
| `portrait_naiwan_*` | 8 | 96×96（neutral happy sad tired surprised determined shy proud） |
| `cg_naiwan_*` | 9 | 160×90（9 个活动插图） |
| `char_npc_*_idle` | 3 | 96×192，2 帧 × 4 方向（s e n w），2 fps |
| `portrait_npc_*` | 12 | 96×96，每人 4 个表情 |
| `char_extra_*` | 4 | 48×48 单帧 s 方向 |
| `model_*` | 5 + 5 + 1 + 12 | 5 栋建筑、5 个室内、地面、12 种道具 |
| `ui_*` | 34 | 面板九宫格 48×48（边距 16）、图标、按键提示、时段点、血条、光标 |
| `palette` | 1 | 128×64（32 色 × 16px） |
| `font_ui` | 1 | Fusion Pixel 12px（**待放入**，见下） |
| `bgm_*` / `sfx_*` | 4 / 12 | OGG Vorbis |

## 3. 正式素材替换流程（每人只需覆盖同名文件）

1. 在 `docs/art/frames/<asset>/` 下画单帧，命名 `<方向>_<序号>.png`（例如 `ne_3.png`）；
2. 用打包脚本生成精灵表与预览：

```powershell
python tools/pack_sprites.py --input docs/art/frames/naiwan_walk `
    --output assets/characters/naiwan/walk.png --cols 4 --frame 48x48 `
    --preview docs/art/preview/naiwan_walk.gif --max-colors 12
```

3. 更新 `assets/LICENSES.csv`（作者、来源、许可、是否修改、日期、AI 工具与条款版本）；
4. `python tools/make_placeholders.py check` 必须零缺失零未登记；
5. `python -m tests.standalone_a --check-assets` 复验，再提合并请求。

## 4. 角色比例参考

`docs/art/naiwan_ref.png` 来自用户提供的三视图（`naiwan_ref_source.jfif`，AI 生成，**仅作参考，
不进入发布包**）。比例要点：蛋形圆身、奶油色肚皮占下半身约 2/3、四肢深橄榄色、眼睛靠近头顶、
整体高度约为身宽的 1.6 倍。正式绘制前需去背景、去参考线、去底部文字。

## 5. 字体（待办）

`assets/fonts/FusionPixel12.ttf`（SIL OFL 1.1，`LIC-0301`）尚未放入仓库。放入前：

- D 的 `TextDB` 使用 `AssetRegistry.load_font("font_ui")`，返回 `None` 时回退引擎默认字体，
  日志会出现 `[ASSET] missing id=font_ui`；
- 中文字符缺字体时 Panda3D 会打印 `:text(warning): No definition in ... for character U+....`，
  A 的替身场景因此全部改用 ASCII 标签。
