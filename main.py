import asyncio
from enum import Enum
import json
import logging
import os

import aiohttp
from aiohttp import web
from anyio import create_task_group
from async_timeout import timeout
import pymorphy2
import pytest

from adapters import SANITIZERS, exceptions
from text_tools import split_by_words, calculate_jaundice_rate


logger = logging.getLogger('main')

TIMEOUT_SECONDS = 5


class ProcessingStatus(Enum):
    OK = 'OK'
    FETCH_ERROR = 'FETCH_ERROR'
    PARSING_ERROR = 'PARSING_ERROR'
    TIMEOUT = 'TIMEOUT'


POSITIVE_WORDS_FILEPATH = os.path.join('charged_dict', 'positive_words.txt')
NEGATIVE_WORDS_FILEPATH = os.path.join('charged_dict', 'negative_words.txt')


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


async def process_article(
    session,
    morph,
    charged_words,
    url,
    processing_outputs,
    sanitizer_func=None
):
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
        if sanitizer_func:
            try:
                plain_text = sanitizer_func(html, plaintext=True)
            except exceptions.ArticleNotFound:
                logger.warning(f'No article found on "{url}"')
                status = ProcessingStatus.PARSING_ERROR
        else:
            plain_text = html

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

    processing_outputs.append((url, status, score, word_number, processing_time))


async def handle_root_get_request(morph, charged_words, request):
    logger.info(f'Request handling started: {request}')
    urls_parameter_value = request.query.get('urls')
    if not urls_parameter_value:
        return web.json_response({})

    requested_urls = urls_parameter_value.split(',')
    if len(requested_urls) > 10:
        error_message = 'too many urls in request, should be 10 or less'
        logger.warning(error_message)
        raise web.HTTPBadRequest(
            content_type='application/json',
            text=json.dumps({'error': error_message})
        )

    async with aiohttp.ClientSession() as session:
        processing_results = []
        async with create_task_group() as task_group:
            for article_url in requested_urls:
                await task_group.spawn(
                    process_article,
                    session,
                    morph,
                    charged_words,
                    article_url,
                    processing_results,
                    SANITIZERS['inosmi_ru']
                )

        response = []
        for url, status, score, word_number, _ in processing_results:
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
            'http://example.com': ProcessingStatus.PARSING_ERROR
        },
        {
            'invalid_url': ProcessingStatus.FETCH_ERROR,
            'https://absent_url.org': ProcessingStatus.FETCH_ERROR
        },
        {
            'https://absent_url.org': ProcessingStatus.FETCH_ERROR,
            'https://inosmi.ru/social/20201205/248649230.html': ProcessingStatus.OK,
            'http://example.com': ProcessingStatus.PARSING_ERROR,
            'https://inosmi.ru/social/20201205/248681932.html': ProcessingStatus.OK,
            'invalid_url': ProcessingStatus.FETCH_ERROR,
        },
    ],
)
@pytest.mark.parametrize('anyio_backend', ['asyncio'])
async def test_process_article(anyio_backend, expected_status_per_url):
    processing_ouputs = []
    async with aiohttp.ClientSession() as session:
        morph = pymorphy2.MorphAnalyzer()
        charged_words = get_charged_words()
        async with create_task_group() as task_group:
            for article_url in expected_status_per_url:
                await task_group.spawn(
                    process_article,
                    session,
                    morph,
                    charged_words,
                    article_url,
                    processing_ouputs,
                    SANITIZERS['inosmi_ru']
                )

    assert len(processing_ouputs) == len(expected_status_per_url)
    for article_features in processing_ouputs:
        assert len(article_features) == 5
        url, status, score, word_num, processing_time = article_features
        assert url in expected_status_per_url
        expected_status = expected_status_per_url[url]
        assert status == expected_status
        if expected_status == ProcessingStatus.OK:
            assert all([score, word_num, processing_time])
        else:
            assert all(
                [score is None, word_num is None, processing_time is None]
            )


@pytest.mark.parametrize('anyio_backend', ['asyncio'])
async def test_too_big_article(anyio_backend):
    url = 'https://dvmn.org/media/filer_public/51/83/51830f54-7ec7-4702-847b-c5790ed3724c/gogol_nikolay_taras_bulba_-_bookscafenet.txt'
    async with aiohttp.ClientSession() as session:
        morph = pymorphy2.MorphAnalyzer()
        charged_words = get_charged_words()
        processing_ouputs = []
        await process_article(session, morph, charged_words, url, processing_ouputs)

    assert len(processing_ouputs) == 1
    article_features = processing_ouputs[0]
    assert len(article_features) == 5
    returned_url, status, score, word_num, processing_time = article_features
    assert returned_url == url
    assert status == ProcessingStatus.TIMEOUT
    assert all(
        [score is None, word_num is None, processing_time == TIMEOUT_SECONDS]
    )
