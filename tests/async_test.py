import asyncio

async def slow_task(name: str, delay: int) :
    print(f"{name} 开始")
    await asyncio.sleep(delay)
    print(f"{name} 结束(等了{delay}秒)")
    return f"{name} 的结果"

async def main() :
    print("===串行执行===")
    result1 = await slow_task("任务1",3)
    result2 = await slow_task("任务2",2)
    print(f"{result1}, {result2}")
    print(f"总耗时，6秒")

    print("\n===并发执行===")
    results = await asyncio.gather(
        slow_task("任务1",3),
        slow_task("任务2",3)
    )
    print(f"{results}")
    print(f"总耗时，3秒")

asyncio.run(main())
