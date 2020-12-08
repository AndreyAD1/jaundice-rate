import logging

from aiohttp import web

from main import main

logger = logging.getLogger('main')

application = web.Application()
application.add_routes([web.get('/', main)])

if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    logger.setLevel(logging.DEBUG)
    web.run_app(application)
