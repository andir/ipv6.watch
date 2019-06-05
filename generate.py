#!/usr/bin/env python3
import argparse
import asyncio
import datetime
import logging
import os
from pprint import pformat

import aiodns
import jsonschema
import yaml
from jinja2 import Environment, FileSystemLoader, Template
import htmlmin

KEY_CATEGORIES = "categories"
KEY_REFNAME = "refname"
KEY_CATEGORY_UNCATEGORIZED = "Uncategorized"

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
        resolvers[name] = list(
            (server, aiodns.DNSResolver(loop=loop, nameservers=[server]))
            for server in servers)

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
                logger.debug('\033[0;32m✓\033[0m\t%s @ %s', host, nameserver)
            else:
                logger.debug('\033[0;31m✗\033[0m\t%s @ %s', host, nameserver)

            h = results[host] = results.get(host, {})
            r = h[resolver_name] = h.get(resolver_name, {})
            r[nameserver] = response

    return results

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


#
# Sort each target into the respective category
#
# targets = All targets with test results
# categories = All available categories
def sort_target_into_categories(targets, categories):
    logger.info("Sorting targets into categories")

    testresults = {}

    for current_category in categories:
        logger.debug("-> Current category: {:s}".format(current_category))

        testresults[current_category] = {} # Add empty dict

        for current_target in targets:
            # Check if the current category is listed in the targets category
            if current_category in targets[current_target]["categories"]:
                logger.debug("   Target {:s} is in there".format(current_target))
                testresults[current_category][current_target] = targets[current_target]

    return testresults

#
# Adds category "Uncategorized" to each target if it has no assigned ones
#
def add_uncategorized_category(targets):
    logger.info("Adding category \"{:s}\" to every target with missing categories".format(KEY_CATEGORY_UNCATEGORIZED))

    for current_target in targets:
        # Check if element "categories" is in the current target
        if KEY_CATEGORIES not in targets[current_target]:
            # Oh no! Add list with single item "Uncategorized"
            targets[current_target][KEY_CATEGORIES] = ( KEY_CATEGORY_UNCATEGORIZED )
            logger.debug("-> Added to {:s}".format(current_target))

#
# Adds a referenceable name key
# Changes "Telegram Messenger" to "telegrammessenger"
# Changes "Instagram" to "instagram"
#
# This is used in the jinja2 template to build HTML anchors
#
def add_referenceable_target_name(targets):
    logger.info("Adding referencable target key")

    for target in targets:
        conversion_result = target.lower().replace(" ","").replace(".","-")
        logger.debug("Converted \"{:s}\" to \"{:s}\"".format(target, conversion_result))
        targets[target][KEY_REFNAME] = conversion_result

#
# Adds the following statistics to each group:
# Amount of:
# - fully ipv6 resolveable targets
# - partial ipv6 resolveable targets
# - non ipv6 resolveable targets
#
def generate_query_results_for_each_category(categories):
    logger.info("Adding IPv6 support statistics to each group")

    stats = {}

    for category in categories:
        logger.debug("Processing category {:s}".format(category))

        countFullIPv6 = 0
        countPartialIPv6 = 0
        countNoIPv6 = 0

        stats[category] = {}

        for target in categories[category]:
            summary = categories[category][target]['query-results']['summary']

            if summary == "all":
                countFullIPv6 += 1
            elif summary == "some":
                countPartialIPv6 += 1
            else:
                countNoIPv6 += 1

        stats[category]['count_full_ipv6'] = countFullIPv6
        stats[category]['count_partial_ipv6'] = countPartialIPv6
        stats[category]['count_no_ipv6'] = countNoIPv6

        logger.debug("IPv6 support: Full -> {:d}, Partial -> {:d}, None -> {:d}".format(countFullIPv6,
            countPartialIPv6, countNoIPv6))

    return stats

#
# Checks if targets are not present in the rendered categories
# Returns a list with missing targets.
#
def check_unrendered_targets(original_targets, filled_categories):
    logger.info("Checking if targets are missing after categorization");

    targets_in_config = list(original_targets)

    for category in filled_categories:
        logger.debug("Processing category {:s}".format(category))

        for target in filled_categories[category]:
            logger.debug("Processing target {:s} in category".format(target))

            if target in targets_in_config:
                logger.debug("Found it for the first time. Removing it from leftover list!")
                targets_in_config.remove(target)

    return targets_in_config

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-c',
        '--config',
        dest='config',
        default='config.yml',
        type=argparse.FileType('r'))
    parser.add_argument(
        '-l',
        '--log-level',
        dest='log_level',
        choices=[
            'DEBUG',
            'ERROR',
            'INFO',
            'WARN'],
        help='Debug level',
        default='INFO')
    parser.add_argument('dest', default='dist', type=writeable_dir)
    parser.add_argument(
        '-m',
        '--minify',
        dest='minify',
        default=False,
        action='store_true')

    args = parser.parse_args()

    log_level = getattr(logging, args.log_level)
    logging.basicConfig(level=log_level)

    config = yaml.full_load(args.config) # https://github.com/yaml/pyyaml/wiki/PyYAML-yaml.load(input)-Deprecation
    # TODO: add item validation
    jsonschema.validate(config_schema, config)

    nameservers = config['nameservers']
    targets = config['targets']
    categories = config['categories']

    add_referenceable_target_name(targets)
    add_uncategorized_category(targets)

    loop = asyncio.get_event_loop()

    resolvers = prepare_resolvers(nameservers, loop)

    tasks = []
    for name, target in targets.items():
        tasks.append(handle_target(resolvers, name, target))

    # Wait until everything is checked?
    tasks = await asyncio.wait(tasks)

    # Sort query results to targets
    for task_list in tasks:
        for task in task_list:
            name, result = task.result()
            targets[name]["query-results"] = result

    testresults_grouped_by_category = sort_target_into_categories(targets, categories)
    querystats_grouped_by_category = generate_query_results_for_each_category(testresults_grouped_by_category)

    missing_targets = check_unrendered_targets(targets, testresults_grouped_by_category)

    if len(missing_targets) != 0:
        logger.critical("Some configured targets are not present in the final test result: {:s}".format(",".join(missing_targets)))
        exit(1)

    jinja_env = Environment(loader=FileSystemLoader('templates/'), trim_blocks=True, lstrip_blocks=True)
    template = jinja_env.get_template('index.jinja2')

    # Render the page to RAM
    renderedhtml = template.render(
        long_date=datetime.datetime.now().strftime('%B %Y'),
        messages=config['messages'],
        testresults=testresults_grouped_by_category,
        querystats=querystats_grouped_by_category,
        date=datetime.datetime.utcnow())

    if args.minify:
        logger.info("Minifying HTML")
        renderedhtml = htmlmin.minify(renderedhtml)

    with open(os.path.join(args.dest, 'index.html'), 'w') as fh:
        logger.info("Writing HTML")
        fh.write(renderedhtml)

    logger.info("Done")


if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())
