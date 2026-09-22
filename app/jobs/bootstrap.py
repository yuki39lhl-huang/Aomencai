"""命令行首次全量刷新：python -m app.jobs.bootstrap"""
from __future__ import annotations

import asyncio
import json

from app.jobs.pipeline import refresh_all


async def main():
    result = await refresh_all(full_history=True)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
