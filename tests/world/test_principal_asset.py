"""校长素材守卫：礼堂台上的人必须是正式立绘，不是占位图。

背景：开学典礼最初用代码几何拼校长 + `char_extra_1` 占位头像。现在换成用户提供的
`素材/人物/校长.jfif` 落成的立牌与头像，这条用例钉住"换上了、且接线没掉"。
"""

from __future__ import annotations

import json

import pytest
from PIL import Image

from game import config
from game.world.ceremony_scene import PRINCIPAL_ART

IDLE_ID = "char_npc_principal_idle"
PORTRAIT_ID = "portrait_npc_principal_neutral"


def _manifest() -> dict[str, dict]:
    data = json.loads((config.resource_root() / "assets" / "manifest.json").read_text("utf-8"))
    entries = data["assets"] if isinstance(data, dict) else data
    return {entry["id"]: entry for entry in entries}


@pytest.fixture(scope="module")
def manifest() -> dict[str, dict]:
    return _manifest()


def test_principal_art_id_is_the_manifest_id():
    assert PRINCIPAL_ART == IDLE_ID
    assert PRINCIPAL_ART in _manifest()


def test_principal_standee_is_48_with_feet_pivot(manifest):
    entry = manifest[IDLE_ID]
    assert entry["type"] == "sprite_sheet"
    assert (entry["frame_w"], entry["frame_h"]) == (48, 48)
    assert entry["pivot"] == [24, 46], "脚点必须是 24/46，否则会浮空或陷进地面"
    assert entry["row_order"] == ["s"]
    path = config.resource_root() / "assets" / entry["path"]
    assert path.is_file(), f"立牌文件不存在：{entry['path']}"
    image = Image.open(path)
    assert image.size == (48, 48), f"立牌尺寸 {image.size}，应为 48×48"
    alpha = image.convert("RGBA").getchannel("A")
    assert alpha.getbbox() is not None, "立牌整张透明（抠图失败）"
    # 人物要落在脚点上方、且不低于 32 px（太小会被家具挡住看不见）
    left, top, right, bottom = alpha.getbbox()
    assert 30 <= bottom <= 47, f"脚底 y={bottom}，应贴近 46"
    assert (bottom - top) >= 32, f"人物只有 {bottom - top} px 高，太小"


def test_principal_portrait_is_96_and_not_a_placeholder(manifest):
    entry = manifest[PORTRAIT_ID]
    path = config.resource_root() / "assets" / entry["path"]
    assert path.is_file(), f"头像文件不存在：{entry['path']}"
    image = Image.open(path)
    assert image.size == (96, 96), f"头像尺寸 {image.size}，应为 96×96"
    bbox = image.convert("RGBA").getchannel("A").getbbox()
    assert bbox is not None
    left_margin = bbox[0]
    right_margin = 96 - bbox[2]
    assert abs(left_margin - right_margin) <= 2, f"头像未居中：左右留白 {left_margin} vs {right_margin}"
    # 外边缘（紧邻透明背景的像素）不得残留浅灰/白底毛边
    import numpy as np

    arr = np.array(image.convert("RGBA"))
    alpha = arr[:, :, 3] > 0
    padded = np.pad(alpha, 1, constant_values=False)
    edge = alpha & (~padded[:-2, 1:-1] | ~padded[2:, 1:-1] | ~padded[1:-1, :-2] | ~padded[1:-1, 2:])
    edge_ys, edge_xs = np.where(edge)
    bad_halo = [
        (int(x), int(y), tuple(int(v) for v in arr[y, x, :3]))
        for x, y in zip(edge_xs, edge_ys)
        if y < 94 and arr[y, x, :3].mean() > 140
    ]
    assert bad_halo == [], f"头像外边缘残留白/浅灰杂像素：{bad_halo}"
    placeholder = config.resource_root() / "assets" / manifest["char_extra_1"]["path"]
    assert path.read_bytes() != placeholder.read_bytes(), "头像还是占位图"


def test_principal_standee_leg_gap_is_transparent(manifest):
    """切掉底座后双腿之间（y=39..45 中缝）必须是透明的，不能封死成白底。"""
    import numpy as np

    entry = manifest[IDLE_ID]
    arr = np.array(Image.open(config.resource_root() / "assets" / entry["path"]).convert("RGBA"))
    gap_alpha = arr[39:45, 23, 3]
    assert (gap_alpha == 0).all(), f"双腿中缝存在未抠净像素：alpha={gap_alpha.tolist()}"


def test_ceremony_dialogue_uses_the_new_portrait():
    """开学典礼 5 页讲话必须挂新头像，不能再指向 char_extra_1 占位。"""
    dialogues = json.loads(
        (config.resource_root() / "content" / "text" / "zh_CN" / "dialogues.json")
        .read_text("utf-8")
    )
    pages = {key: page for key, page in dialogues.items()
             if key.startswith("ceremony.opening.page.")}
    assert len(pages) == 5
    for key, page in pages.items():
        assert page["speaker"] == "npc_principal"
        assert page["portrait"] == PORTRAIT_ID, f"{key} 仍指向 {page['portrait']}"
