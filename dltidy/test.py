import asyncio


async def echo(num):
    # time.sleep(num / 1000) # time.sleep() はブロッキング処理であり、asyncioのイベントループがブロックされるため、10, 0, 20の順番のまま出力される
    await asyncio.sleep(num / 1000)
    print(num)


class Executor:
    def __init__(self, arg):
        self.arg = arg

    async def async_init(self):
        await echo(self.arg)


async def main():
    print("start!")

    arr = [10, 0, 20]

    tasks = []
    for elm in arr:
        executor = Executor(elm)
        task = asyncio.create_task(executor.async_init())
        tasks.append(task)

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
    print("end!")
