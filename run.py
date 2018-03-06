#!/usr/bin/env python3
import click
from aiohttp import web
import asyncio
import datetime
import logging
import os
from pprint import pformat

import aiodns
import jsonschema
import yaml
from jinja2 import Environment, FileSystemLoader, Template

logger = logging.getLogger(__name__)

config_schema = {
    'type': 'Object',
    'attributes': {
        'nameservers': {
            'type': 'Object'
        },
        'targets': {
            'type': 'Object'
        },
        'messages': {
            'type': 'Object'
        }
    }
}


def writeable_dir(values):
    prospective_dir = values
    if not os.path.isdir(prospective_dir):
        raise argparse.ArgumentTypeError(
            "writeable_dir:{0} is not a valid path".format(prospective_dir))
    if not os.access(prospective_dir, os.W_OK | os.R_OK):
        raise argparse.ArgumentTypeError(
            "writeable_dir:{0} is not a writeable dir".format(prospective_dir))
    return prospective_dir


def prepare_resolvers(nameservers, loop=None):
    if not loop:
        loop = asyncio.get_event_loop()

    resolvers = {}
    for name, servers in nameservers.items():
        try:
            resolvers[name] = list(
                (server, aiodns.DNSResolver(loop=loop, nameservers=[server]))
                for server in servers)
        except ValueError as e:
            logger.error('ValueError: {} @ {}'.format(e, servers))

    return resolvers


async def resolve_host(target, resolver, context=None):
    try:
        response = await resolver.query(target, 'AAAA')
    except aiodns.error.DNSError:
        return False, context
    if len(response) == 0:
        return False, context
    return True, context


async def resolve_target(target, resolvers):
    tasks = []
    for host in target['hosts']:
        for name, r in resolvers.items():
            for resolver in r:
                tasks.append(
                    resolve_host(
                        host, resolver[1],
                        (host, name, resolver[0])))

    results = {}
    r = await asyncio.wait(tasks)
    for l in r:
        for task in l:
            result = task.result()

            response, context = task.result()
            host, resolver_name, nameserver = context

            if response:
                logger.info('\033[0;32m✓\033[0m\t%s @ %s', host, nameserver)
            else:
                logger.info('\033[0;31m✗\033[0m\t%s @ %s', host, nameserver)

            h = results[host] = results.get(host, {})
            r = h[resolver_name] = h.get(resolver_name, {})
            r[nameserver] = response

    return results


def generate_message(media, target, conf, result):
    if media in conf:
        template = Template(media.get(result))
        return template.render(
            target=target,
            conf=conf,
            result=result,
            media=media)
    else:
        raise RuntimeError('Invalid media {} for {}'.format(media, target))


async def handle_target(resolvers, name, target):
    result = await resolve_target(target, resolvers)
    msg = "none"

    if any(
            success
            for host, rs in result.items()
            for resolver, servers in rs.items()
            for server, success in servers.items()
    ):
        msg = "some"

    if all(
            success
            for host, rs in result.items()
            for resolver, servers in rs.items()
            for server, success in servers.items()
    ):
        msg = "all"

    return name, dict(hosts=result, summary=msg)


async def run_queries(resolvers, targets):
    results = {}
    tasks = []
    for name, target in targets.items():
        tasks.append(handle_target(resolvers, name, target))

    tasks = await asyncio.wait(tasks)
    for task_list in tasks:
        for task in task_list:
            name, result = task.result()
            results[name] = result


    results = sorted(results.items(), key=lambda x: x[0])
    logging.debug(pformat(results))
    return results

@click.group()
@click.pass_context
@click.option('--config', '-c', default='conf.yaml', type=click.File(), help='config file')
@click.option('--log-level', '-l', default='INFO',
        type=click.Choice([
            'DEBUG',
            'ERROR',
            'INFO',
            'WARN'
        ]), help='log level')
def cli(ctx, config, log_level):
    cfg = yaml.load(config)
    jsonschema.validate(config_schema, cfg)
    ctx.meta['config'] = cfg
    log_level = getattr(logging, log_level)
    logging.basicConfig(level=log_level)


async def update(nameservers, targets, config, loop=None):
    resolvers = prepare_resolvers(nameservers, loop=loop)
    results = await run_queries(resolvers, targets)

    jinja_env = Environment(loader=FileSystemLoader('templates/'))
    template = jinja_env.get_template('index.jinja2')
    return template.render(
                long_date=datetime.datetime.now().strftime('%B %Y'),
                results=results,
                targets=targets,
                messages=config['messages'],
                date=datetime.datetime.utcnow())

@cli.command()
@click.pass_context
@click.argument('filename', type=click.Path(writable=True))
def gen(ctx, filename):
    loop = asyncio.get_event_loop()

    nameservers = ctx.meta['config']['nameservers']
    targets = ctx.meta['config']['targets']

    content = loop.run_until_complete(update(nameservers, targets, ctx.meta['config']))
    with open(filename, 'w') as fh:
        fh.write(content)


async def handle_index(request):
    content = request.app.get('content')
    if asyncio.iscoroutine(content) or isinstance(content, asyncio.Future):
        content = await content
    else:
        if content is None:
            return web.Response(text='booting', status=501)

    return web.Response(body=content.encode('utf-8'), content_type='text/html')


async def background_update(app):
    nameservers, targets = [app['ctx']['config'][key]
            for key in ['nameservers', 'targets']]
    future = asyncio.Future()
    app['content'] = future
    while True:
        logger.info('Updating')
        content = await update(nameservers, targets, app['ctx']['config'])
        future.set_result(content)
        app['content'] = content
        await asyncio.sleep(60)


async def start_background_tasks(app):
    app['update_task'] = app.loop.create_task(background_update(app))

async def cleanup_background_tasks(app):
    app['update_task'].cancel()
    await app['update_task']


@cli.command()
@click.pass_context
@click.argument('port', type=int, default=8080)
def serve(ctx, port):
    app = web.Application()
    app['ctx'] = ctx.meta
    app.router.add_get('/', handle_index)
    app.router.add_static('/', './dist')


    app.on_startup.append(start_background_tasks)
    app.on_cleanup.append(cleanup_background_tasks)

    web.run_app(app, port=port)


if __name__ == "__main__":
    cli()
