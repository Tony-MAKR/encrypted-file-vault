#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "无法导入 Django。请确认已在 backend/.venv 中安装依赖，"
            "并先运行 scripts/setup-dev.ps1。"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
