"""礼堂贴图守卫：红毯 / 幕布 / 演讲台三张图必须存在、尺寸正确、已接线。

画布在 `docs/art/character_prop_prompts.md` §3.2 里定死：
红毯 86×163（3.6×6.8 m 整块）、幕布 288×43（12 m×1.8 m）、演讲台 41×43（1.71×1.79 m）。
"""

from __future__ import annotations

import json

import pytest
from PIL import Image

from game import config
from game.world.ceremony_scene import CEREMONY_ART, PODIUM_CARD_HEIGHT, PODIUM_CARD_WIDTH

EXPECTED = {
    "ceremony_carpet": ("carpet", (86, 163)),
    "ceremony_curtain": ("curtain", (288, 43)),
    "ceremony_podium": ("podium", (41, 43)),
}


def _manifest() -> dict[str, dict]:
    data = json.loads((config.resource_root() / "assets" / "manifest.json").read_text("utf-8"))
    entries = data["assets"] if isinstance(data, dict) else data
    return {entry["id"]: entry for entry in entries}


@pytest.fixture(scope="module")
def manifest() -> dict[str, dict]:
    return _manifest()


@pytest.mark.parametrize("asset_id", sorted(EXPECTED))
def test_ceremony_texture_exists_with_expected_canvas(asset_id, manifest):
    key, size = EXPECTED[asset_id]
    assert CEREMONY_ART[key] == asset_id, f"{key} 映射到了 {CEREMONY_ART[key]}"
    entry = manifest[asset_id]
    path = config.resource_root() / "assets" / entry["path"]
    assert path.is_file(), f"贴图文件不存在：{entry['path']}"
    image = Image.open(path)
    assert image.size == size, f"{asset_id} 是 {image.size}，应为 {size}"
    assert entry.get("canvas") == list(size), "manifest 的 canvas 与实际尺寸不一致"


def test_podium_card_size_matches_texture():
    """演讲台立牌的米数必须等于 41×43 px ÷ 24，否则会被拉伸。"""
    assert PODIUM_CARD_WIDTH == pytest.approx(41 / 24.0)
    assert PODIUM_CARD_HEIGHT == pytest.approx(43 / 24.0)


def test_ceremony_scene_uses_textures_when_provided():
    """给 textures 时不该再画代码几何（否则红毯/幕布/演讲台会重影）。"""
    import inspect

    from game.world.ceremony_scene import CeremonyScene

    source = inspect.getsource(CeremonyScene._build)
    assert "self.textures.get(\"carpet\")" in source
    assert "self.textures.get(\"curtain\")" in source
    podium_source = inspect.getsource(CeremonyScene._build_podium)
    assert "self.textures.get(\"podium\")" in podium_source
    # 贴图分支必须排在纯色分支之前（有图时直接 return）
    assert podium_source.index("self.textures.get(\"podium\")") < podium_source.index("PODIUM_WOOD_COLOR")
    # 演讲台是独立道具立牌，按相机俯角倾斜，不能再用垂直墙面导致纵向压扁
    assert "set_p(config.CAMERA_TILT_DEGREES)" in podium_source
    assert "make_wall_panel" not in podium_source
