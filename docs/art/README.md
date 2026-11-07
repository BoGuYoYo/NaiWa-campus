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

| 资源 | 状态 | 来源 |
| --- | --- | --- |
| `char_naiwan_walk` / `char_naiwan_idle` | **正式资源**（`LIC-0001`） | 用户提供的单方向序列帧（8 张，每张 8 帧），经 `tools/slice_reference_sheets.py` 自动切片 |
| 其余全部美术与音频 | 同尺寸占位资源 | `tools/make_placeholders.py` 程序生成 |

## 2.1 当前角色规格（2026-11-07 素材更新）

| 项 | 值 |
| --- | --- |
| 行走表 | `walk.png` 384×384：**8 帧** × 8 方向，8 fps |
| 待机表 | `idle.png` 144×384：3 帧 × 8 方向，3 fps |
| 单帧 | 48×48，脚点 (24,46)，实测身高 39～42 像素 |
| 素材来源 | 素材目录 8 张单方向图：向前走 / 右前前进 / 向右走 / 右后行走 / 向后行走 / 左后行走 / 向左走 / 左前前进 |

`walk.png` 从 A8 表的 4 帧（192×384）升级到 8 帧（384×384）：新素材本身就是 8 帧循环，
丢掉一半会破坏接触—经过的节奏。行宽由 `manifest.json` 的 `cols` 驱动，App/渲染层不做硬编码。

切片的完整流程（可重复执行，结果稳定）：

```powershell
python tools/slice_reference_sheets.py --verify   # 只输出 build/_slice_contact_{walk,idle}.png 核对图
python tools/slice_reference_sheets.py            # 写入 assets/characters/naiwan/{walk,idle}.png
python tools/slice_reference_sheets.py --idle-source "..\素材\待机.jfif"   # 有专门待机图时
```

切片做的处理（每一步都能在脚本里查到）：

1. 素材识别：按文件名关键字把 8 张图映射到方向（向前→s、右前→se、向右→e、右后→ne、
   向后→n、左后→nw、向左→w、左前→sw），缺方向或少文件会直接报错；
2. 面板定位：黄色身体掩码 → 1/4 降采样连通域 → 按行/列排序成 FRAME 01～08（杂乱小块按面积过滤）；
3. 抠背景：从 bbox 边界对灰色背景洪水填充，3×3 开闭去噪，再按“贴着身体 + 面积占比”保留
   分离的手臂/脚（只留最大连通域会把背面视图的胳膊吃掉）；
4. 缩放：整张表统一用一个 `scale` 做面积（BOX）缩放——新素材的放大倍数不是整数（≈15.3），
   块众数会随网格漂移把眼睛和描边吃掉；
5. 落位：身高归一到 38 像素、脚点 (24,46)、加 1 像素 `#2B2235` 描边、量化到 32 色、
   透明像素 RGB 置 0；
6. 待机：没有待机素材时用各方向行走首帧 + 1 像素呼吸位移（3 帧）；有 `--idle-source` 就用它。

注意：`tools/make_placeholders.py art` 会跳过 `FINAL_ASSETS`（`walk.png`、`idle.png`），
不会被占位图覆盖回去。要恢复占位图必须先手动删除这两张正式资源。

占位资源清单（其余部分仍需按 A9 重绘）：

清单（与 `assets/manifest.json` 一致，共 109 条）：

| 类别 | 数量 | 规格 | 状态 |
| --- | --- | --- | --- |
| `char_naiwan_walk` | 1 | 384×384，8 帧 × 8 方向，8 fps | 正式（切片） |
| `char_naiwan_idle` | 1 | 144×384，3 帧 × 8 方向，3 fps | 正式（切片） |
| `char_shadow` | 1 | 24×8 | 占位 |
| `portrait_naiwan_*` | 8 | 96×96（neutral happy sad tired surprised determined shy proud） | 占位 |
| `cg_naiwan_*` | 9 | 160×90（9 个活动插图） | 占位 |
| `char_npc_*_idle` | 3 | 96×192，2 帧 × 4 方向（s e n w），2 fps | 占位 |
| `portrait_npc_*` | 12 | 96×96，每人 4 个表情 | 占位 |
| `char_extra_*` | 4 | 48×48 单帧 s 方向 | 占位 |
| `model_*` | 5 + 5 + 1 + 12 | 5 栋建筑、5 个室内、地面、12 种道具 | 白模 |
| `ui_*` | 34 | 面板九宫格 48×48（边距 16）、图标、按键提示、时段点、血条、光标 | 占位 |
| `palette` | 1 | 128×64（32 色 × 16px） | 定稿 |
| `font_ui` | 1 | Fusion Pixel 12px（**待放入**，见下） | 待补 |
| `bgm_*` / `sfx_*` | 4 / 12 | OGG Vorbis | 合成占位 |

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
不进入发布包**）。比例要点：蛋形圆身、奶油色肚皮占下半身约 2/3、四肢深橄榄色、眼睛靠近头顶。
切片后的正式行走表见 `docs/art/preview/naiwan_walk.gif`（4 帧 × 8 方向循环）。

## 5. 字体（待办）

`assets/fonts/FusionPixel12.ttf`（SIL OFL 1.1，`LIC-0301`）尚未放入仓库。放入前：

- D 的 `TextDB` 使用 `AssetRegistry.load_font("font_ui")`，返回 `None` 时回退引擎默认字体，
  日志会出现 `[ASSET] missing id=font_ui`；
- 中文字符缺字体时 Panda3D 会打印 `:text(warning): No definition in ... for character U+....`，
  A 的替身场景因此全部改用 ASCII 标签。
