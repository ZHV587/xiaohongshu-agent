import asyncio

from data_foundation.sync_service import _run_coro


async def _echo(value):
    return value


def test_run_coro_without_running_loop():
    # 生产主路径:同步工具被卸到线程,线程内无 running loop → 走 asyncio.run,行为不变。
    assert _run_coro(_echo(7)) == 7


def test_run_coro_inside_running_loop_does_not_crash():
    # 防御路径:若在事件循环线程里同步调用,不得抛 "cannot be called from a running event loop"。
    async def driver():
        return _run_coro(_echo(9))

    assert asyncio.run(driver()) == 9
