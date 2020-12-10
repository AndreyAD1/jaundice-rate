import asyncio
from enum import Enum
import json
import logging
import os.path

import aiohttp
from aiohttp import web
from anyio import create_task_group
from async_timeout import timeout
import pymorphy2
import pytest

from adapters import SANITIZERS, exceptions
from text_tools import split_by_words, calculate_jaundice_rate


logger = logging.getLogger('main')
POSITIVE_WORDS_FILEPATH = os.path.join('charged_dict', 'positive_words.txt')
NEGATIVE_WORDS_FILEPATH = os.path.join('charged_dict', 'negative_words.txt')
TIMEOUT_SECONDS = 10


class ProcessingStatus(Enum):
    OK = 'OK'
    FETCH_ERROR = 'FETCH_ERROR'
    PARSING_ERROR = 'PARSING_ERROR'
    TIMEOUT = 'TIMEOUT'


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


async def process_article(session, morph, charged_words, url, results):
    status = ProcessingStatus.OK
    try:
        async with timeout(TIMEOUT_SECONDS) as timeout_manager:
            html = await fetch(session, url)
    except (aiohttp.ClientConnectorError, aiohttp.InvalidURL):
        logger.warning(f'Can not connect to "{url}"')
        status = ProcessingStatus.FETCH_ERROR
    except asyncio.TimeoutError:
        if not timeout_manager.expired:
            raise
        status = ProcessingStatus.TIMEOUT

    score = None
    word_number = None
    processing_time = None
    plain_text = None
    if status == ProcessingStatus.OK:
        try:
            plain_text = SANITIZERS['inosmi_ru'](html, plaintext=True)
        except exceptions.ArticleNotFound:
            logger.warning(f'No article found on "{url}"')
            status = ProcessingStatus.PARSING_ERROR

    if status == ProcessingStatus.OK:
        try:
            async with timeout(TIMEOUT_SECONDS) as timeout_manager:
                article_words = await split_by_words(morph, plain_text)
        except asyncio.TimeoutError:
            if not timeout_manager.expired:
                raise
            status = ProcessingStatus.TIMEOUT
            processing_time = TIMEOUT_SECONDS
            logger.debug(
                f'Timeout exceeded while processing an article on {url}'
            )

    if status == ProcessingStatus.OK:
        score = calculate_jaundice_rate(article_words, charged_words)
        word_number = len(article_words)
        processing_time = TIMEOUT_SECONDS - timeout_manager.remaining
        logger.debug(f'{url} has been processed in {processing_time} seconds')

    results.append((url, status, score, word_number, processing_time))


async def main(request):
    logger.info(f'Request handling started: {request}')
    urls = request.query.get('urls')
    if not urls:
        return web.json_response({})

    url_list = urls.split(',')
    if len(url_list) > 10:
        error_message = 'too many urls in request, should be 10 or less'
        logger.warning(error_message)
        raise web.HTTPBadRequest(
            content_type='application/json',
            text=json.dumps({'error': error_message})
        )

    async with aiohttp.ClientSession() as session:
        morph = pymorphy2.MorphAnalyzer()
        charged_words = get_charged_words()
        article_features = []
        async with create_task_group() as task_group:
            for article_url in url_list:
                await task_group.spawn(
                    process_article,
                    session,
                    morph,
                    charged_words,
                    article_url,
                    article_features
                )

        response = []
        for url, status, score, word_number, _ in article_features:
            url_result = {
                'status': status.name,
                'url': url,
                'score': score,
                'words_count': word_number
            }
            response.append(url_result)

    logger.info(f'Response body: {response}')
    return web.json_response(response)


@pytest.mark.parametrize(
    'expected_status_per_url',
    [
        {'https://inosmi.ru/social/20201205/248649230.html': ProcessingStatus.OK},
        {
            'https://inosmi.ru/social/20201205/248649230.html': ProcessingStatus.OK,
            'https://inosmi.ru/social/20201205/248681932.html': ProcessingStatus.OK
        },
        {
            'http://google.com': ProcessingStatus.PARSING_ERROR
        }
    ],
)
@pytest.mark.parametrize('anyio_backend', ['asyncio'])
async def test_process_article(anyio_backend, expected_status_per_url):
    result_list = []
    async with aiohttp.ClientSession() as session:
        morph = pymorphy2.MorphAnalyzer()
        charged_words = get_charged_words()
        async with create_task_group() as task_group:
            for article_url in expected_status_per_url.keys():
                await task_group.spawn(
                    process_article,
                    session,
                    morph,
                    charged_words,
                    article_url,
                    result_list
                )

    assert len(result_list) == len(expected_status_per_url)
    for article_features in result_list:
        assert len(article_features) == 5
        url, status, score, word_num, processing_time = article_features
        assert url in expected_status_per_url
        expected_status = expected_status_per_url[url]
        assert status == expected_status
        if expected_status == ProcessingStatus.OK:
            assert all([score, word_num, processing_time])
        else:
            assert not any([score, word_num, processing_time])
