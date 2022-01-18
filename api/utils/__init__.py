# globally used stuff goes here

import json
import boto3
import os
import sys
from datetime import datetime
import requests

import web3
Web3 = web3.Web3
from web3.auto import w3 as w3auto
from eth_account.messages import encode_structured_data
from eth_account import Account
import asn1tools

DATA_BUCKET = os.environ.get("DATA_BUCKET", "risk-data.solace.fi.data")
DEAD_LETTER_TOPIC = os.environ.get("DEAD_LETTER_TOPIC", "arn:aws:sns:us-west-2:151427405638:RiskDataDeadLetterQueue")

s3_client = boto3.client("s3", region_name="us-west-2")
sns_client = boto3.client("sns", region_name="us-west-2")

s3_cache = {}

# retrieves an object from S3, optionally reading from cache
def s3_get(key, cache=False):
    if cache and key in s3_cache:
        return s3_cache[key]
    else:
        res = s3_client.get_object(Bucket=DATA_BUCKET, Key=key)["Body"].read().decode("utf-8").strip()
        s3_cache[key] = res
        return res

def s3_put(key, body):
    s3_client.put_object(Bucket=DATA_BUCKET, Body=body, Key=key)

def sns_publish(message):
    sns_client.publish(
        TopicArn=DEAD_LETTER_TOPIC,
        Message=message
    )

def read_json_file(filename):
    with open(filename) as f:
        return json.loads(f.read())

def to_32byte_hex(val):
    return Web3.toHex(Web3.toBytes(val).rjust(32, b'\0'))

def stringify_error(e):
    traceback = e.__traceback__
    s = str(e)
    while traceback:
        s = "{}\n{}: {}".format(s, traceback.tb_frame.f_code.co_filename, traceback.tb_lineno)
        traceback = traceback.tb_next
    return s


def handle_error(event, e, statusCode):
    print(e)
    resource = event["resource"] if "resource" in event else ".unknown()"
    queryStringParameters = event["queryStringParameters"] if "queryStringParameters" in event else ""
    sns_message = "The following {} error occurred in solace-risk-data{}:\n{}\n{}".format(statusCode, resource, queryStringParameters, stringify_error(e))
    sns_publish(sns_message)
    http_message = str(e)
    return {
        "statusCode": statusCode,
        "body": http_message,
        "headers": headers
    }

headers = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "OPTIONS,GET,POST,PUT,DELETE"
}

alchemy_key = s3_get("alchemy_key.txt", cache=True)
alchemy_mainnet_key = ""
ETH_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"

class InputException(Exception):
    pass

ADDRESS_SIZE = 40 # 20 bytes or 40 hex chars
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
SOLACE_ADDRESS = "0x501acE9c35E60f03A2af4d484f49F9B1EFde9f40"
xSOLACE_ADDRESS = "0x501AcE5aC3Af20F49D53242B6D208f3B91cfc411"
erc20Json = json.loads(s3_get("abi/other/ERC20.json", cache=True))
ONE_ETHER = 1000000000000000000

# chainId => network
NETWORKS = {'1': 'ethereum', '4': 'rinkeby'}
config_s3 = json.loads(s3_get('config.json', cache=True))

def get_supported_chains():
    return config_s3['supported_chains']

def get_config(chainId: str):
    if chainId in get_supported_chains():
        cfg = config_s3[chainId]
        w3 = Web3(Web3.HTTPProvider(cfg["alchemyUrl"].format(alchemy_key)))
        cfg["w3"] = w3

        if len(cfg['soteria']) > 0:
            soteriaABI = json.loads(s3_get('abi/soteria/SoteriaCoverageProduct.json', cache=True))
            soteriaContract = w3.eth.contract(address=cfg["soteria"], abi=soteriaABI)
            cfg["soteriaContract"] = soteriaContract
        return cfg
    else:
        return None

def get_network(chainId: str) -> str:
    if chainId in NETWORKS:
        return NETWORKS[chainId]
    return None

def get_soteria_policy_holders(chainId: str) -> list:
    cfg = get_config(chainId)
    if cfg is None:
        raise InputException(f"Bad request. Not found config for the chain id: {chainId}")

    # TODO: make contract call
    policyholder1 = {
        "address": "0x09748F07b839EDD1d79A429d3ad918f670D602Cd",
        "coverLimit": 1000,
    }
    policyholder2 = {
        "address": "0x11BB97923209Df97E8c9839E1e394798cb0C0336",
        "coverLimit": 2000,
    }
    return [policyholder1, policyholder2]