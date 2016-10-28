#!/usr/bin/env python3
import multiprocessing
import requests
import random
import yaml
from jinja2 import Environment, FileSystemLoader, Template
import argparse
import jsonschema
import asyncio
import aiodns
import os
import logging
import datetime
from pprint import pprint

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

# Change this to get more tweets (it takes a little longer)
NUMBER_OF_YEARS_TO_GET_TWEETS = 1


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
        resolvers[name] = list((server, aiodns.DNSResolver(
            loop=loop, nameservers=[server])) for server in servers)

    return resolvers


def resolve_host(target, resolver, context=None):
    try:
        response = yield from resolver.query(target, 'AAAA')
    except aiodns.error.DNSError:
        return False, context
    if len(response) == 0:
        return False, context
    return True, context


def resolve_target(target, resolvers, loop):
    tasks = []
    for host in target['hosts']:
        for name, r in resolvers.items():
            for resolver in r:
                tasks.append(resolve_host(host, resolver[
                             1], (host, name, resolver[0])))

    results = {}
    for task in tasks:
        result = loop.run_until_complete(task)
        response, context = result
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
        return template.render(target=target, conf=conf, result=result, media=media)
    else:
        raise RuntimeError('Invalid media {} for {}'.format(media, target))


def count_tweets_in_twitter_url(url):
    useragent = ["Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36","Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36","Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36","Mozilla/5.0 (Macintosh; Intel Mac OS X 10_11_6) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/53.0.2785.143 Safari/537.36","Mozilla/5.0 (Windows NT 10.0; WOW64; rv:49.0) Gecko/20100101 Firefox/49.0","Mozilla/5.0 (Windows NT 6.1; WOW64; rv:49.0) Gecko/20100101 Firefox/49.0","Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12) AppleWebKit/602.1.50 (KHTML, like Gecko) Version/10.0 Safari/602.1.50"]
    headers = {'User-Agent': random.choice(useragent)}
    r = requests.get(url, headers=headers)
    print(url,r.text.count('js-tweet-text-container'))
    return r.text.count('js-tweet-text-container')

def get_tweets(handle):
    # get_tweets returns the number of tweets that are have tweeted to the handle about ipv6
    # for the last YEARS
    YEARS = 1
    ranges = []

    now = datetime.datetime.now()
    past = now - datetime.timedelta(days=365 * YEARS)
    delta = datetime.timedelta(weeks=4)
    c = past
    while c < now:
       next = c + delta
       ranges.append((c, next))
       c = next

    dates_to_try = []
    for start, end in ranges:
       dates_to_try.append((str(start.year) + "-" + str(start.month) + "-" + str(start.day),str(end.year) + "-" + str(end.month) + "-" + str(start.day)))
            
    # Go through tweets, one month at a time, since Twitter requires loading pages if there are too many at once
    # (if there are too many, you may need to go one week/day at a time)
    urls = []
    for date_to_try in dates_to_try:
        urls.append("https://twitter.com/search?f=tweets&q=ipv6%20%23" + handle + \
            "%20since%3A" + date_to_try[0] + "%20until%3A" + date_to_try[1])
       
    p = multiprocessing.Pool(multiprocessing.cpu_count())
    total_tweets = 0
    for tweet_num in p.map(count_tweets_in_twitter_url,urls):
        total_tweets += tweet_num
    return total_tweets


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', dest='config',
                        default='conf.yaml', type=argparse.FileType('r'))
    parser.add_argument('-l', '--log-level', dest='log_level', choices=[
                        'DEBUG', 'ERROR', 'INFO', 'WARN'], help='Debug level', default='INFO')
    parser.add_argument('dest', default='dist', type=writeable_dir)

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level)
    logging.basicConfig(level=log_level)

    config = yaml.load(args.config)
    # TODO: add item validation
    jsonschema.validate(config_schema, config)

    nameservers = config['nameservers']
    targets = config['targets']

    loop = asyncio.get_event_loop()

    resolvers = prepare_resolvers(nameservers, loop)

    results = {}
    for name, target in targets.items():
        result = resolve_target(target, resolvers, loop)
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

        results[name] = dict(hosts=result, summary=msg)

    results = sorted(results.items(), key=lambda x: x[0])
    pprint(results)
    tweets = {}
    for result in results:
        tweets[result[0]] = get_tweets(result[0])

    jinja_env = Environment(loader=FileSystemLoader('templates/'))
    template = jinja_env.get_template('index.jinja2')
    with open(os.path.join(args.dest, 'index.html'), 'w') as fh:
        fh.write(template.render(long_date=datetime.datetime.now().strftime('%B %Y'),
                                 results=results, targets=targets, messages=config['messages'], date=datetime.datetime.utcnow(), tweets=tweets))


if __name__ == "__main__":
    main()
