import functools
import logging

from aiohttp import web
import pymorphy2

from main import main, get_charged_words

logger = logging.getLogger('server')


if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    logger.setLevel(logging.DEBUG)

    morph = pymorphy2.MorphAnalyzer()
    charged_words = get_charged_words()
    prepared_main = functools.partial(main, morph, charged_words)
    application = web.Application()
    application.add_routes([web.get('/', prepared_main)])

    web.run_app(application)
