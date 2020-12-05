import asyncio

import aiohttp
import pymorphy2

from adapters import SANITIZERS
from text_tools import split_by_words, calculate_jaundice_rate


async def fetch(session, url):
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


async def main():
    async with aiohttp.ClientSession() as session:
        html = await fetch(session, 'https://inosmi.ru/social/20201205/248649230.html')
        plain_text = SANITIZERS['inosmi_ru'](html, plaintext=True)
        morph = pymorphy2.MorphAnalyzer()
        text_words = split_by_words(morph, plain_text)
        key_words = ['одноклассники', 'исключить', 'неправильный']
        jaundice_rate = calculate_jaundice_rate(text_words, key_words)
        print('Рейтинг: ', jaundice_rate)
        print('Слов в статье: ', len(text_words))


asyncio.run(main())
