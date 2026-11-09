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
| `char_naiwan_walk` / `char_naiwan_idle` | **正式**（`LIC-0001`） | 用户提供的单方向序列帧 + `待机图.jfif`，经 `tools/slice_reference_sheets.py` 切片 |
| `portrait_naiwan_*`（8 张） | **正式**（`LIC-0006`） | 用户提供的 `素材/小表情/`，经 `tools/import_generated_art.py` 落位 |
| `cg_naiwan_*`（9 张） | **正式**（`LIC-0006`） | 用户提供的 `素材/场景/`，同一工具落位 |
| UI 皮肤 `ui_*`（29 张） | **正式**（`LIC-0210`） | 用户提供的 `素材/UI/` 合成图，经 `tools/import_ui_skin.py` 去背、最近邻缩放和 32 色量化 |
| 其余全部美术与音频 | 同尺寸占位资源 | `tools/make_placeholders.py` 程序生成 |

## 2.1 当前角色规格（2026-11-08 素材更新后）

| 项 | 值 |
| --- | --- |
| 行走表 | `walk.png` 384×384：**8 帧** × 8 方向，8 fps |
| 待机表 | `idle.png` 144×384：3 帧 × 8 方向，3 fps（来自 `素材/待机图.jfif`） |
| 单帧 | 48×48，脚点 (24,46)，实测身高 39～42 像素 |
| 头像 | `portraits/naiwan/<表情>.png` 96×96：neutral happy sad **angry** surprised **speechless** shy proud |
| 活动插图 | `art/cg/naiwan_<活动>.png` 160×90，9 个活动各一张 |

> 表情 ID 在 2026-11-08 调整：用户实际交付的是 `生气/无语`，因此
> `portrait_naiwan_tired` → `portrait_naiwan_angry`、`portrait_naiwan_determined` →
> `portrait_naiwan_speechless`（旧 ID 已从 manifest 移除，`game/core` 无任何硬编码引用）。

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

### 头像与活动插图的落位（`tools/import_generated_art.py`）

```powershell
python tools/import_generated_art.py --all --verify   # 只出核对图 build/_cg_final.png / _portraits_final.png
python tools/import_generated_art.py --all            # 写入 assets/art/cg 与 assets/portraits/naiwan
```

- **场景**：2752×1536 居中裁成 16:9 → 面积缩放到 160×90 → 自适应量化 64 色（插图细节多，
  不套用 32 色角色板）；
- **表情**：1024×1024 抠灰底（边界洪水填充 + 最大连通域）→ 按**肩宽**归一裁剪成半身像
  （8 张站姿不同，按 bbox 高度裁会让头像忽大忽小）→ 缩到 96×96 → 量化 32 色 → 透明像素 RGB 置 0。

游戏里已经接上：`game/app.py` 的替身 `ResultPanel` 会按 `cg_naiwan_<activity_id>` 显示活动插图
（缺失时 registry 自动回退占位图），文本与插图分居左下 / 中上，互不遮挡。

### UI 皮肤导入（2026-11-09，`LIC-0210`）

`素材/UI/` 本次交付的是 10 张合成 JPEG：6 张属性图标、1 张 3×3 活动图标表、1 张共用键帽、
1 张点/条/光标表和 1 张面板。`tools/import_ui_skin.py` 按现有 29 个 `ui_*` asset_id 切分并写回
原路径，不改变游戏或 UI 模块接口：

```powershell
python tools/import_ui_skin.py --source "..\素材\UI"
python tools/import_ui_skin.py --verify
```

处理规则为边界泛洪去背、整数网格上的最近邻缩放、映射到 `PALETTE` 的 32 色、透明像素 RGB 清零；
键帽文字由工具以 3×5 像素字烧入。对照图写入 `reports/review/ui_skin_sheet.png`，面板额外检查
四角镜像和 16×16 中心纯色，数值条额外检查两端 2 像素列可复用。

### 建筑正面贴图（2026-11-09）

当前游戏优先使用用户生成的 5 张正面建筑图（`LIC-0208`），建筑按原图比例绘制，和角色卡片
以相同俯角朝向正交摄像机，避免正面图再次受到透视压缩。原有 BAM 建筑保留为资源缺失时的回退。

```powershell
python tools/process_building_textures.py
# 也可指定源目录：
python tools/process_building_textures.py --source "..\素材\建筑"
```

| 原图 | 透明输出 | 注册 ID |
| --- | --- | --- |
| 教学楼.jfif | campus/textures/teaching_front.png | campus_texture_teaching |
| 宿舍楼.jfif | campus/textures/dorm_front.png | campus_texture_dorm |
| 图书馆.jfif | campus/textures/library_front.png | campus_texture_library |
| 社团中心.jfif | campus/textures/club_front.png | campus_texture_club |
| 食堂.jfif | campus/textures/canteen_front.png | campus_texture_canteen |

- 这批原图实际为 2752×1536 RGB JPEG，棋盘格已烘焙在图片中。工具使用为当前五张图描好的
  外轮廓生成 Alpha，保留灰色墙面、阳台和台阶，裁去多余边距，透明像素 RGB 置 0。
  若新图改变构图，需要重描工具中的轮廓坐标；原始素材不改写。
- 这些立面图保留原图色彩与裁切后的分辨率，是上方 512 像素模型贴图限制的例外。
  缩小时使用线性 mipmap 过滤，进入 480×270 游戏画布后仍按全局最近邻规则放大。
- 卡片底边对齐原占地南沿，使用 `MBinary` 和深度写入：角色在前方可见、在后方被遮挡，
  图像透明角落不会挡住角色；实机检查覆盖全部 5 栋。
- 保留加大的建筑横向间距与 1.25 倍相机视野；食堂向南再移 8 米，避免遮住社团入口。
  外围草地和南北道路已延伸覆盖新的布局。

### 草坪贴图与道具立牌（2026-11-09，`LIC-0209`）

用户在 `素材/建筑/` 追加了 1 张草坪贴图和 4 张道具正面图，由
`tools/import_campus_props.py` 接入（白底泛洪去背 → 去掉烘焙的地面投影 →
按内容裁切缩放 → PNG）：

```powershell
python tools/import_campus_props.py            # 草坪 + 4 个道具
python tools/import_campus_props.py --props    # 只处理道具
```

| 原图 | 输出 | 注册 ID | 用途 |
| --- | --- | --- | --- |
| 草坪贴图.jfif | campus/textures/ground_grass.png（512²，64 色） | campus_texture_ground | 地面平铺贴图，4 米一循环 |
| 树.jfif | campus/textures/props/tree.png（191×256） | campus_texture_prop_tree | 行道树/景观树立牌，4.5 米高 |
| 路灯.jfif | campus/textures/props/lamp.png（43×256） | campus_texture_prop_lamp | 路灯立牌，4.0 米高 |
| 垃圾桶.jfif | campus/textures/props/bin.png（113×160） | campus_texture_prop_bin | 垃圾桶立牌，1.0 米高 |
| 告示牌.jfif | campus/textures/props/sign.png（94×200） | campus_texture_prop_sign | 校门告示牌立牌，2.4 米高 |

处理细节（踩过的坑）：

- **不能用全局颜色键**：路灯灯罩、告示牌板面本身就接近白色，全局抠会把它们打穿；
  改成「从四边泛洪」只吃掉与边界连通的白色。
- 原图底部烧了一块灰色地面投影，贴到草地上会变成灰斑：在内容包围盒下半部，
  把「低饱和 + 中亮」的像素一并去掉（树干棕色、灯座深灰、轮子近黑都不在区间内）。
- 树根之间还有与背景不连通的纯白空隙，同样按「底部区域 + 纯白」二次清理。
- 道具用 `MBinary`（alpha 测试）而不是 `MAlpha`，这样能正常写深度，树与树之间不穿插。
- 草地靠 UV>1 平铺，**必须显式 `set_wrap_u/v(WM_repeat)`**：TexturePool 默认 clamp，
  否则整片草地只会采样到贴图边缘，看起来是一块纯色。

`content/world/map.json` 里的 `props` 已登记 25 个阻挡物（长椅、告示牌、13 棵树、
5 盏路灯、5 个垃圾桶），布置规则写在文件头的 `notes` 里；移动或改名后要重跑
`tests.standalone_c --route C-R1`（C-R1 的直行走廊在 x=44.5，道具不能压线）。

### 校园模型（`tools/build_campus_models.py`；建筑为回退资源）

用户提供的等距参考图（`素材/建筑/`：宿舍楼、教学楼、图书馆、社团、饭堂、12 个道具、草地1）
已经在 Blender 4.5.11 中重构，并通过 glTF 2.0 → `.bam` 导入游戏；游戏资源使用烘焙后的 ColorAttrib，**无贴图**：

```powershell
python tools/build_campus_models.py          # 写入 assets/campus/*.bam
```

| 模型 | 三角面 | 造型要点（对照参考图） |
| --- | --- | --- |
| `dorm` | 1,040 | 四层冷灰墙、砖红双坡屋顶 + 3 个老虎窗、四腿水塔 + 天线 + 烟囱、阳台/晾衣杆、雨棚台阶 |
| `teaching` | 824 | 四层 U 形、奶油墙 + 分格窗带、红色女儿墙、中央钟塔 + 圆钟、旗杆红旗、屋顶空调箱 |
| `library` | 1,710 | 三层方体 + 分层转角石块、四坡屋顶 + 采光脊、通高中央窗、四柱门廊 + 宽台阶 |
| `club` | 684 | 两层灰绿、红女儿墙、屋顶招牌（双柱）、六段彩色雨棚、底层大玻璃 |
| `canteen` | 716 | 单层赭黄、非对称双坡屋顶、三根排烟管、四柱深挑檐、外侧售餐台 |
| `ground` | 468 | 80×45 草地 + 分层土壤、南北主路（世界 x 38~44）+ 东西支路（世界 y 6~11）、深色草斑与草簇 |
| 12 个道具 | 30~348 | 圆树冠/路灯/分木条长椅/围栏/告示牌/带灌木花坛/垃圾桶/弧形车架/旗杆/石头/花圃/路面 |

室外模型合计 **7,120 三角面**（建筑、地面与道具，预算 30,000）；含 5 个室内模型共 **7,816 三角面**。Blender 导出模型保留更多窗框与屋顶细节，单栋面数以最终 BAM 为准。

- 命名 `mesh_*`、原点在占地西南角、Z 向上、1 单位 = 1 米；
- 没有法线（= 引擎不参与光照，颜色直出），符合像素风平涂；
- 碰撞体不在模型里，`content/world/map.json` 由 C 提供；
- `game/app.py` 的替身校园已按 `BUILDINGS` 表摆放这 5 栋 + 18 个道具，模型缺失时自动退回占位方块。
- **待办**：建筑占地目前是 A 的布景值，等 C 的地图表定稿后需要对齐（`docs/integration/week-1.md` 已登记）。

注意：`tools/make_placeholders.py art` 会跳过 `FINAL_ASSETS`（`walk.png`、`idle.png`），
不会被占位图覆盖回去。要恢复占位图必须先手动删除这两张正式资源。

占位资源清单（其余部分仍需按 A9 重绘）：

清单（与 `assets/manifest.json` 一致，共 114 条）：

| 类别 | 数量 | 规格 | 状态 |
| --- | --- | --- | --- |
| `char_naiwan_walk` | 1 | 384×384，8 帧 × 8 方向，8 fps | 正式（切片） |
| `char_naiwan_idle` | 1 | 144×384，3 帧 × 8 方向，3 fps | 正式（切片） |
| `char_shadow` | 1 | 24×8 | 占位 |
| `portrait_naiwan_*` | 8 | 96×96（neutral happy sad angry surprised speechless shy proud） | 正式（生成落位） |
| `cg_naiwan_*` | 9 | 160×90（9 个活动插图） | 正式（生成落位） |
| `char_npc_*_idle` | 3 | 96×192，2 帧 × 4 方向（s e n w），2 fps | 占位 |
| `portrait_npc_*` | 12 | 96×96，每人 4 个表情 | 占位 |
| `char_extra_*` | 4 | 48×48 单帧 s 方向 | 占位 |
| `model_*` | 5 + 5 + 1 + 12 | 5 栋建筑、5 个室内、地面、12 种道具 | 正式（程序建模，`LIC-0207`） |
| `campus_texture_*` | 5 + 5 | 5 张建筑正面立面图（`LIC-0208`）+ 草坪贴图与 4 个道具立牌（`LIC-0209`） | 正式（用户生成图） |
| `ui_*` | 29 | 九宫格面板 48×48（边距 16）×1、属性图标 16×16 ×6、活动图标 16×16 ×9、按键提示 16×16 ×8、时段点 8×8 ×2、血条框/填充 100×8 ×2、光标 8×8 ×1 | 占位（生图提示词见 `docs/art/ui_skin_prompts.md`） |
| `palette` | 1 | 128×64（32 色 × 16px） | 定稿 |
| `font_ui` | 1 | Fusion Pixel 12px（**待放入**，见下） | 待补 |
| `bgm_*` / `sfx_*` | 4 / 12 | OGG Vorbis | 合成占位 |

### 9 张活动插图与活动名对照（`cg_naiwan_*`，160×90）

| asset_id | 活动 ID | 显示名 | 画面内容 |
| --- | --- | --- | --- |
| `cg_naiwan_attend_class` | `attend_class` | 上课 | 教室、黑板、课桌 |
| `cg_naiwan_library_study` | `library_study` | 图书馆学习 | 书架、台灯、书 |
| `cg_naiwan_play_games` | `play_games` | 打游戏 | 显示器、手柄 |
| `cg_naiwan_create_work` | `create_work` | **敲代码** | 双屏代码窗口、笔记本、咖啡 |
| `cg_naiwan_join_club` | `join_club` | 参加社团 | 横幅、活动室 |
| `cg_naiwan_exercise` | `exercise` | 锻炼 | 跑道、球 |
| `cg_naiwan_eat_canteen` | `eat_canteen` | 食堂用餐 | 餐盘、饭桌 |
| `cg_naiwan_rest_dorm` | `rest_dorm` | 宿舍休息 | 床铺、被子 |
| `cg_naiwan_campus_walk` | `campus_walk` | 校园闲逛 | 林荫道、路灯 |

> 2026-11-07 变更：`create_work` 的语义由「创作（画画）」调整为「敲代码」。
> 活动 ID 保持不变（ID 冻结原则，文件仍叫 `create_work`），只改显示名、插图与图标
> （`ui/icons/activity_create_work.png` 从画笔改为终端 + 代码行）。
> 结局 `ending_creator` 的文案建议一并改成「独立开发者」口径，由 B/D 在内容 JSON 里落实。

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
