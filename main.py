import aiohttp
import asyncio

from adapters import SANITIZERS


async def fetch(session, url):
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


async def main():
    async with aiohttp.ClientSession() as session:
        html = await fetch(session, 'https://inosmi.ru/social/20201205/248649230.html')
        plain_text = SANITIZERS['inosmi_ru'](html, plaintext=True)
        print(plain_text)


asyncio.run(main())
