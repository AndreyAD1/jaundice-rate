from aiohttp import web


async def handle(request):
    query_dict = {k: value.split(',') for k, value in request.query.items()}
    return web.json_response(query_dict)

application = web.Application()
application.add_routes([web.get('/', handle)])

if __name__ == '__main__':
    web.run_app(application)
