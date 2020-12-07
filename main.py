import asyncio
from contextlib import contextmanager
from enum import Enum
import logging
import os.path
import time

import aiohttp
from anyio import create_task_group, run
from async_timeout import timeout
import pymorphy2

from adapters import SANITIZERS, exceptions
from text_tools import split_by_words, calculate_jaundice_rate


logger = logging.getLogger(__file__)
POSITIVE_WORDS_FILEPATH = os.path.join('charged_dict', 'positive_words.txt')
NEGATIVE_WORDS_FILEPATH = os.path.join('charged_dict', 'negative_words.txt')
TEST_ARTICLES = [
    (
        'https://dvmn.org/media/filer_public/51/83/51830f54-7ec7-4702-847b-c5790ed3724c/gogol_nikolay_taras_bulba_-_bookscafenet.txt',
        'Книга'
    )
    # (
    #     'http://google.com',
    #     'Google'
    # ),
    # (
    #     '$&*%JF',
    #     'Fake'
    # ),
    # (
    #     'https://iinvalid_url',
    #     'Fake'
    # ),
    # (
    #     'https://inosmi.ru/social/20201205/248649230.html',
    #     'Milliyet (Турция): смотрите, что происходит, если вы пьете две чашки липового чая в день'
    # ),
    # (
    #     'https://inosmi.ru/social/20201205/248681932.html',
    #     'WirtschaftsWoche (Германия): российский женский парадокс'
    # ),
    # (
    #     'https://inosmi.ru/social/20201205/248690078.html',
    #     'The Wall Street Journal (США): Pfizer сократила число доз вакцины от covid-19, которые она планирует произвести до конца года'
    # ),
    # (
    #     'https://inosmi.ru/politic/20201205/248690006.html',
    #     'Пашиняну дали время до вторника: "Уйди в отставку!" (Haqqin, Азербайджан)'
    # ),
    # (
    #     'https://inosmi.ru/social/20201205/248679078.html',
    #     'Helsingin Sanomat (Финляндия): почему одни зимой мерзнут, а другие — нет'
    # )
]
TIMEOUT_SECONDS = 3


class ProcessingStatus(Enum):
    OK = 'OK'
    FETCH_ERROR = 'FETCH_ERROR'
    PARSING_ERROR = 'PARSING_ERROR'
    TIMEOUT = 'TIMEOUT'


class Timer:
    def __init__(self, start):
        self.start = start
        self.end = None

    @property
    def timer_result(self):
        if self.end is not None:
            return self.end - self.start


@contextmanager
def timer():
    processing_start_time = time.monotonic()
    process_timer = Timer(processing_start_time)
    try:
        yield process_timer
    finally:
        process_timer.end = time.monotonic()


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


async def process_article(session, morph, charged_words, url, title, results):
    status = ProcessingStatus.OK
    try:
        async with timeout(TIMEOUT_SECONDS) as timeout_manager:
            html = await fetch(session, url)
    except (aiohttp.ClientConnectorError, aiohttp.InvalidURL):
        title = f'Can not connect to "{url}"'
        status = ProcessingStatus.FETCH_ERROR
    except asyncio.TimeoutError:
        if not timeout_manager.expired:
            raise
        status = ProcessingStatus.TIMEOUT

    score = None
    word_number = None
    processing_time = None
    if status == ProcessingStatus.OK:
        try:
            # plain_text = SANITIZERS['inosmi_ru'](html, plaintext=True)
            plain_text = html
        except exceptions.ArticleNotFound:
            title = f'No article found on "{url}"'
            status = ProcessingStatus.PARSING_ERROR
            score = None
            word_number = None
        else:
            try:
                async with timeout(TIMEOUT_SECONDS) as timeout_manager:
                    article_words = await split_by_words(morph, plain_text)
            except asyncio.TimeoutError:
                if not timeout_manager.expired:
                    raise
                status = ProcessingStatus.TIMEOUT
                processing_time = TIMEOUT_SECONDS
            else:
                status = ProcessingStatus.OK
                score = calculate_jaundice_rate(article_words, charged_words)
                word_number = len(article_words)
                processing_time = TIMEOUT_SECONDS - timeout_manager.remaining

    results.append((title, status, score, word_number, processing_time))


async def main():
    async with aiohttp.ClientSession() as session:
        morph = pymorphy2.MorphAnalyzer()
        charged_words = get_charged_words()
        article_features = []
        async with create_task_group() as task_group:
            for article_url, title in TEST_ARTICLES:
                await task_group.spawn(
                    process_article,
                    session,
                    morph,
                    charged_words,
                    article_url,
                    title,
                    article_features
                )

        for title, score, status, word_number, duration in article_features:
            print('Заголовок:', title)
            print('Статус:', status)
            print('Рейтинг:', score)
            print('Слов в статье:', word_number)
            print(f'Анализ закончен за {round(duration, 2)} сек')
            print()


if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    logger.setLevel(logging.DEBUG)
    run(main)
