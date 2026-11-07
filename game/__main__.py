"""A 维护：python -m game 入口。"""

from __future__ import annotations

import sys

from . import config


def main(argv: list[str] | None = None) -> int:
    options = config.parse_args(argv)
    config.setup_logging(options)
    from .app import run

    return run(options)


if __name__ == "__main__":
    sys.exit(main())
