from __future__ import annotations

import asyncio

from market_data.liquidity_engine.config import LiquidityEngineConfig
from market_data.liquidity_engine.runtime.supervisor import LiquidityEngineSupervisor


async def _run() -> None:
    cfg = LiquidityEngineConfig.from_env()
    supervisor = LiquidityEngineSupervisor(cfg)
    await supervisor.start()
    try:
        while True:
            await asyncio.sleep(5)
    finally:
        await supervisor.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
