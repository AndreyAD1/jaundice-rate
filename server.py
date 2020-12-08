import logging

from aiohttp import web

from main import main

logger = logging.getLogger(__file__)


async def handle(request):
    query_dict = {k: value.split(',') for k, value in request.query.items()}
    return web.json_response(query_dict)

application = web.Application()
application.add_routes([web.get('/', main)])

if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    logger.setLevel(logging.DEBUG)
    web.run_app(application)
