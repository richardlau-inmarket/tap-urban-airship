#!/usr/bin/env python3

import datetime
import os
import sys

import backoff
import requests
import singer
from singer import utils

from .transform import transform_row


BASE_URL = "https://go.urbanairship.com/api/"
CONFIG = {
    'app_key': None,
    'app_secret': None,
    'start_date': None,
}
STATE = {}

LOGGER = singer.get_logger()
SESSION = requests.Session()

def get_abs_path(path):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)

def load_schema(entity):
    return utils.load_json(get_abs_path("schemas/{}.json".format(entity)))


def get_start(entity):
    if entity not in STATE:
        STATE[entity] = CONFIG['start_date']

    return STATE[entity]

@backoff.on_exception(backoff.expo,
                      (requests.exceptions.RequestException),
                      max_tries=5,
                      giveup=lambda e: e.response is not None \
                          and 400 <= e.response.status_code < 500,
                      factor=2)
def request(url):
    auth = requests.auth.HTTPBasicAuth(CONFIG['app_key'], CONFIG['app_secret'])
    headers = {'Accept': "application/vnd.urbanairship+json; version=3;"}
    if 'user_agent' in CONFIG:
        headers['User-Agent'] = CONFIG['user_agent']

    req = requests.Request('GET', url, auth=auth, headers=headers).prepare()
    LOGGER.info("GET {}".format(req.url))
    resp = SESSION.send(req)
    if resp.status_code >= 400:
        try:
            data = resp.json()
            LOGGER.error("GET {0} [{1.status_code} - {error} ({error_code})]".format(
                req.url, resp, **data))
        except Exception:
            LOGGER.error("GET {0} [{1.status_code} - {1.content}]".format(req.url, resp))

        sys.exit(1)

    return resp


def gen_request(endpoint):
    url = BASE_URL + endpoint
    while url:
        resp = request(url)
        data = resp.json()
        for row in data[endpoint]:
            yield row

        url = data.get('next_page')


def sync_entity(entity, primary_keys, date_keys=None, transform=None):
    schema = load_schema(entity)
    singer.write_schema(entity, schema, primary_keys)

    start_date = get_start(entity)
    for row in gen_request(entity):
        if transform:
            row = transform(row)

        if date_keys:
            # Rows can have various values for various date keys (See the calls to
            # `sync_entity` in `do_sync`), usually dates of creation and update.
            # But in some cases some keys may not be present.
            #
            # To handle this we:
            #
            # 1. Get _all_ the values for all the keys that are actually present in
            # the row (not every row has every key), and exclude missing ones.
            #
            # 2. Take the max of those values as the bookmark for that entity.
            #
            # A KeyError is raised if the row has none of the date keys.
            if not any(date_key in row for date_key in date_keys):
                raise KeyError('None of date keys found in the row')
            last_touched = max(row[date_key] for date_key in date_keys if date_key in row)
            utils.update_state(STATE, entity, last_touched)
            if last_touched < start_date:
                continue

        row = transform_row(row, schema)

        singer.write_record(entity, row)

    singer.write_state(STATE)


def do_sync():
    LOGGER.info("Starting sync")

    # Lists, Channels, and Segments are very straight forward to sync. They
    # each have two dates that need to be examined to determine the last time
    # the record was touched.
    sync_entity("lists", ["name"], ["created", "last_updated"])
    sync_entity("channels", ["channel_id"], ["created", "last_registration"])
    sync_entity("segments", ["id"], ["creation_date", "modificiation_date"])

    # Named Users have full channel objects nested in them. We only need the
    # ids for generating the join table, so we transform the list of channel
    # objects into a list of channel ids before transforming the row based on
    # the schema.
    def flatten_channels(item):
        item['channels'] = [c['channel_id'] for c in item['channels']]
        return item

    # The date fields are not described in API documentation
    # https://docs.urbanairship.com/api/ua/#schemas/nameduserresponsebody,
    # but actually they are present.
    sync_entity("named_users", ["named_user_id"], ["created", "last_modified"], transform=flatten_channels)

    LOGGER.info("Sync completed")


def main_impl():
    args = utils.parse_args(["app_key", "app_secret", "start_date"])
    CONFIG.update(args.config)

    if args.state:
        STATE.update(args.state)

    do_sync()

def main():
    try:
        main_impl()
    except Exception as exc:
        LOGGER.critical(exc)
        raise exc



if __name__ == '__main__':
    main()
