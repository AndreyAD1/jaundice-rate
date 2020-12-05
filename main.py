import os.path

import aiohttp
from anyio import create_task_group, run
import pymorphy2

from adapters import SANITIZERS
from text_tools import split_by_words, calculate_jaundice_rate


POSITIVE_WORDS_FILEPATH = os.path.join('charged_dict', 'positive_words.txt')
NEGATIVE_WORDS_FILEPATH = os.path.join('charged_dict', 'negative_words.txt')
TEST_ARTICLES = [
    (
        'https://inosmi.ru/social/20201205/248649230.html',
        'Milliyet (Турция): смотрите, что происходит, если вы пьете две чашки липового чая в день'
    ),
    (
        'https://inosmi.ru/social/20201205/248681932.html',
        'WirtschaftsWoche (Германия): российский женский парадокс'
    ),
    (
        'https://inosmi.ru/social/20201205/248690078.html',
        'The Wall Street Journal (США): Pfizer сократила число доз вакцины от covid-19, которые она планирует произвести до конца года'
    ),
    (
        'https://inosmi.ru/politic/20201205/248690006.html',
        'Пашиняну дали время до вторника: "Уйди в отставку!" (Haqqin, Азербайджан)'
    ),
    (
        'https://inosmi.ru/social/20201205/248679078.html',
        'Helsingin Sanomat (Финляндия): почему одни зимой мерзнут, а другие — нет'
    )
]


def get_charged_words():
    charged_words = []
    for path in [POSITIVE_WORDS_FILEPATH, NEGATIVE_WORDS_FILEPATH]:
        with open(path, 'r') as file:
            charged_words.extend([word.strip() for word in file])
    return charged_words


async def fetch(session, url):
    async with session.get(url) as response:
        response.raise_for_status()
        return await response.text()


async def process_article(session, morph, charged_words, url, title):
    html = await fetch(session, url)
    plain_text = SANITIZERS['inosmi_ru'](html, plaintext=True)
    article_words = split_by_words(morph, plain_text)
    score = calculate_jaundice_rate(article_words, charged_words)
    print('Заголовок:', title)
    print('Рейтинг:', score)
    print('Слов в статье:', len(article_words))
    print()


async def main():
    async with aiohttp.ClientSession() as session:
        morph = pymorphy2.MorphAnalyzer()
        charged_words = get_charged_words()
        async with create_task_group() as task_group:
            for article_url, title in TEST_ARTICLES:
                await task_group.spawn(
                    process_article,
                    session,
                    morph,
                    charged_words,
                    article_url,
                    title
                )


run(main)
