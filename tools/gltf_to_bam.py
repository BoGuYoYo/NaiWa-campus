"""A 的工具：glTF 2.0 -> Panda3D .bam，并按 A7 规格设置最近邻、不生成 mipmap。

用法：
    python tools/gltf_to_bam.py assets/campus/dorm.gltf assets/campus/dorm.bam

依赖 panda3d-gltf（requirements-dev.txt）。若未安装，脚本会给出安装提示而不是静默失败。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def load_gltf(path: Path):
    """优先用 panda3d-gltf，其次尝试 panda3d.core.AssetLoader。"""
    from panda3d.core import NodePath

    try:
        from gltf import load_model as gltf_load_model  # type: ignore

        model = gltf_load_model(str(path))
        # panda3d-gltf 1.3 returns ModelRoot; the rest of this tool uses NodePath APIs.
        return model if isinstance(model, NodePath) else NodePath(model)
    except ImportError:
        pass
    try:
        from panda3d.core import AssetLoader, Filename

        loader = AssetLoader.getGlobalPtr()
        model = loader.load_sync(Filename.fromOsSpecific(str(path)))
        if model is None:
            raise SystemExit(f"AssetLoader 无法读取 {path}")
        return model if isinstance(model, NodePath) else NodePath(model)
    except ImportError as exc:
        raise SystemExit("需要 panda3d-gltf：pip install panda3d-gltf") from exc


def apply_pixel_rules(node) -> int:
    """模型纹理统一最近邻 + 不生成 mipmap（A7 第 4 行）。"""
    from panda3d.core import SamplerState

    count = 0
    for texture in node.findAllTextures():
        texture.setMagfilter(SamplerState.FT_nearest)
        texture.setMinfilter(SamplerState.FT_nearest)
        texture.setKeepRamImage(False)
        count += 1
    return count


def apply_material_colors(node) -> int:
    """Bake glTF material base colors into ColorAttrib for the game's unlit renderer."""
    from panda3d.core import MaterialAttrib

    count = 0
    for path in node.findAllMatches("**/+GeomNode"):
        geom_node = path.node()
        for index in range(geom_node.getNumGeoms()):
            state = geom_node.getGeomState(index)
            attrib = state.getAttrib(MaterialAttrib.getClassType())
            if attrib is None:
                continue
            color = attrib.getMaterial().getBaseColor()
            path.setColor(color, 1)
            count += 1
            break
    return count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="glTF 2.0 -> .bam")
    parser.add_argument("source", help="输入 .gltf / .glb")
    parser.add_argument("target", help="输出 .bam 路径")
    parser.add_argument("--no-nearest", action="store_true", help="不强制最近邻过滤")
    args = parser.parse_args(argv)

    source = Path(args.source)
    target = Path(args.target)
    if not source.exists():
        raise SystemExit(f"输入不存在: {source}")

    node = load_gltf(source)
    if node is None:
        raise SystemExit(f"转换失败: {source}")
    textures = 0 if args.no_nearest else apply_pixel_rules(node)
    colors = apply_material_colors(node)

    from panda3d.core import Filename

    target.parent.mkdir(parents=True, exist_ok=True)
    # 必须使用 Filename.fromOsSpecific：直接传 str 会走 model-path 并丢掉非 ASCII 字符
    ok = node.writeBamFile(Filename.fromOsSpecific(str(target)))
    if not ok or not target.exists():
        raise SystemExit(f"写入 .bam 失败: {target}")
    print(f"ok: {target} (textures={textures}, colors={colors})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
