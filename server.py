import functools
import logging

from aiohttp import web
import pymorphy2

from main import handle_root_get_request, get_charged_words

logger = logging.getLogger('server')


if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    logger.setLevel(logging.DEBUG)

    morph = pymorphy2.MorphAnalyzer()
    charged_words = get_charged_words()
    prepared_root_get_handler = functools.partial(
        handle_root_get_request,
        morph,
        charged_words
    )
    application = web.Application()
    application.add_routes([web.get('/', prepared_root_get_handler)])

    web.run_app(application)
