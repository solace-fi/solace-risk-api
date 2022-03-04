from api.utils import *
from datetime import datetime
import pandas as pd
import numpy as np
import json
import re

def verify_account(params, cfg):
    if "account" not in params:
        raise InputException("missing account") # check policy id exists
    try:
        addr = cfg['w3'].toChecksumAddress(params["account"])
        if not cfg['w3'].isAddress(addr):
            raise "invalid address"
        return addr
    except Exception as e:
        raise InputException(f"invalid account: '{params['account']}'") # check policy id exists

def verify_params(params, cfg):
    if params is None:
        raise InputException("missing params")
    return {
        "account": verify_account(params, cfg)
    }

def fetch_eth_price():
    for i in range(5):
        try:
            url = "https://api.zapper.fi/v1/prices/0x0000000000000000000000000000000000000000?network=ethereum&timeFrame=hour&currency=USD&api_key=96e0cc51-a62e-42ca-acee-910ea7d2a241"
            response = requests.get(url, timeout=600)
            response.raise_for_status()
            res = response.json()
            # gives prices over the last hour, average
            prices = res["prices"]
            count = 0
            s = 0
            for price in prices:
                count += 1
                s += price[1]
            price = s / count
            if price <= 1000 or price >= 10000:
                raise("price out of range")
            return price
        except Exception as e:
            print(e)
    raise Exception("error fetching data")

def fetch_positions(params):
    api_key = "96e0cc51-a62e-42ca-acee-910ea7d2a241" # only key key, public
    url = f"https://api.zapper.fi/v1/balances-v3?api_key={api_key}&addresses[]={params['account']}"
    for i in range(1):
        try:
            response = requests.get(url, timeout=600)
            response.raise_for_status()
            sns_publish('successful call to zapper get balances')
            return response.text
        except Exception as e:
            msg = f"In Solace Risk API get balances. Error fetching data from zapper\nURL   : {url}\nIP    : {get_IP_address()}\nError : {e}"
            print(msg)
            sns_publish(msg)
    raise Exception("error fetching data")

def parse_positions(s, network):
    try:
        positions = []
        matches = re.findall("event: protocol\ndata: {*.*}", s)
        for match in matches:
            index = match.find('{')
            index2 = match.rfind('}')
            if index == -1 or index2 == -1:
                break
            position = json.loads(match[index:index2+1])
            positions.append(position)
        # order by network, app
        if network is not None:
            positions = list(filter(lambda position: 'network' in position and position['network'] == network, positions))
        positions = list(sorted(positions, key = lambda pos: f"{pos['network']} {pos['appId']}"))
        return positions
    except Exception as e:
        raise Exception(f"Error parsing data. Error: {e}")

def clean_positions(positions2, account):
    eth_price = fetch_eth_price()
    try:
        positions3 = []
        account = account.lower()
        for position in positions2:
            # filter out zero balance positions
            if len(position["data"]) == 0:
                continue
            # filter out nfts and tokens
            if position["appId"] == "tokens" or position["appId"] == "nft":
                continue
            # flatten
            balanceUSD = 0
            for pos in position["data"]:
                if pos["type"] != "position":
                    continue
                balanceUSD += pos["balanceUSD"]
            position["balanceUSD"] = balanceUSD
            position["balanceETH"] = balanceUSD / eth_price
            position.pop("balances", None)
            positions3.append(position)
        return positions3
    except Exception as e:
        raise Exception(f"error cleaning positions data. Error {e}")

def calculate_weights(positions):
    try:
        weighted_positions = []
        balance_sum = sum([position["balanceETH"] for position in positions])
        for position in positions:
            weighted_position = {"protocol": position["appId"], "weight": position["balanceETH"] / balance_sum}
            weighted_positions.append(weighted_position)
        return weighted_positions
    except Exception as e:
        raise Exception(f"error calculating weights. Error: {e}")

def get_balances(params):
    network = None
    if 'chain_id' not in params:
        raise InputException(f"Bad request. Chain id is not provided")
    network = get_network(params['chain_id'])
    if network is None:
        raise InputException(f"Bad request. Network name is not found for chain id: {params['chain_id']}")
    cfg = get_config(params['chain_id'])
    params2 = verify_params(params, cfg)
    positions = fetch_positions(params2)
    positions2 = parse_positions(positions, network)
    positions3 = clean_positions(positions2, params2["account"])
    return json.dumps(positions3)

def handler(event, context):
    try:
        response_body = get_balances(event["queryStringParameters"])
        return {
            "statusCode": 200,
            "body": response_body,
            "headers": headers
        }
    except InputException as e:
        return handle_error(event, e, 400)
    except Exception as e:
        return handle_error(event, e, 500)


if __name__ == '__main__':
    event = {"queryStringParameters": {"chain_id": "1", "account": "0x09748F07b839EDD1d79A429d3ad918f670D602Cd"}}
    print(handler(event, None))