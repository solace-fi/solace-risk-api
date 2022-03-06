# globally used stuff goes here

import json
from typing import List
import boto3
import os
import sys
from datetime import datetime
from calendar import monthcalendar
import requests

import web3
Web3 = web3.Web3
from web3.auto import w3 as w3auto
from eth_account.messages import encode_structured_data
from eth_account import Account
import asn1tools

DATA_BUCKET = os.environ.get("DATA_BUCKET", "risk-data.solace.fi.data")
DEAD_LETTER_TOPIC = os.environ.get("DEAD_LETTER_TOPIC", "arn:aws:sns:us-west-2:151427405638:RiskDataDeadLetterQueue")
S3_SOTERIA_SCORES_FOLDER = 'soteria-scores/'
S3_SOTERIA_PROCESSED_SCORES_FOLDER = 'soteria-processed-scores/'
S3_BILLINGS_FOLDER = 'soteria-billings/'
S3_BILLINGS_FILE = 'billings.json'
S3_BILLING_ERRORS_FILE = 'billing_errors.json'
S3_TO_BE_SCORED_FOLDER = "to-be-scored/"
S3_ASKED_FOR_QUOTE_FOLDER = 'asked-for-quote/'
S3_SERIES_FILE = 'current-rate-data/series.json'

s3_client = boto3.client("s3", region_name="us-west-2")
s3_resource = boto3.resource("s3", region_name="us-west-2")
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

def s3_move(key: str, new_key: str):
    copy_source = {'Bucket': DATA_BUCKET, 'Key': key}
    s3_client.copy_object(Bucket=DATA_BUCKET, CopySource=copy_source, Key=new_key)
    s3_client.delete_object(Bucket=DATA_BUCKET, Key=key)


def s3_get_files(folder):
    files = []
    res = s3_client.list_objects_v2(Bucket=DATA_BUCKET, Prefix=folder)
    contents = res.get("Contents")
    if contents:
        for content in contents:
            files.append(content['Key'])
    return files
    
def sns_publish(message):
    sns_client.publish(
        TopicArn=DEAD_LETTER_TOPIC,
        Message=message
    )

def read_json_file(filename):
    with open(filename) as f:
        return json.loads(f.read())

def get_file_name(file):
    return os.path.splitext(os.path.basename(file))[0]

def to_32byte_hex(val):
    return Web3.toHex(Web3.toBytes(val).rjust(32, b'\0'))

def stringify_error(e):
    traceback = e.__traceback__
    s = str(e)
    while traceback:
        s = "{}\n{}: {}".format(s, traceback.tb_frame.f_code.co_filename, traceback.tb_lineno)
        traceback = traceback.tb_next
    return s

def get_IP_address():
    # gets the IP of the lambda instance
    try:
        url = "https://checkip.amazonaws.com/"
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        return response.text.rstrip()
    except Exception as e:
        return 'unknown'

def get_week_of_month(year, month, day):
    return next(
        (
            week_number
            for week_number, days_of_week in enumerate(monthcalendar(year, month), start=1)
            if day in days_of_week
        ),
        None,
    )

def get_date_string():
  return datetime.now().strftime("%Y-%m-%d")

def get_timestamp():
    return datetime.now().strftime("%Y/%m/%d, %H:%M:%S")

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

alchemy_config = json.loads(s3_get("alchemy_config.json", cache=True))

class InputException(Exception):
    pass

ETH_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
ADDRESS_SIZE = 40 # 20 bytes or 40 hex chars
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
SOLACE_ADDRESS = "0x501acE9c35E60f03A2af4d484f49F9B1EFde9f40"
xSOLACE_ADDRESS = "0x501AcE5aC3Af20F49D53242B6D208f3B91cfc411"
erc20Json = json.loads(s3_get("abi/other/ERC20.json", cache=True))
ONE_ETHER = 1000000000000000000

# chainId => network
NETWORKS = {1: 'ethereum', 137: 'polygon'}
config_s3 = json.loads(s3_get('config2.json', cache=True))

def get_supported_chains():
    return config_s3['supported_chains']

def get_config(chain_id: str):
    if chain_id in get_supported_chains():
        if chain_id == "1":
            cfg = config_s3[chain_id]
            w3 = Web3(Web3.HTTPProvider(alchemy_config["1"]))
            cfg["w3"] = w3

            if len(cfg['soteria']) > 0:
                soteria_json = json.loads(s3_get('abi/soteria/SolaceCoverProduct.json', cache=True))
                soteriaContract = w3.eth.contract(address=cfg["soteria"], abi=soteria_json["abi"])
                cfg["soteriaContract"] = soteriaContract
            return cfg
        elif chain_id == "137":
            cfg = config_s3[chain_id]
            w3 = Web3(Web3.HTTPProvider(alchemy_config["137"]))
            cfg["w3"] = w3

            if len(cfg['soteria']) > 0:
                soteria_json = json.loads(s3_get('abi/soteria/SolaceCoverProductV2.json', cache=True))
                soteriaContract = w3.eth.contract(address=cfg["soteria"], abi=soteria_json["abi"])
                cfg["soteriaContract"] = soteriaContract
            return cfg
        else:
            return None
    else:
        return None

def get_premium_collector(chain_id: str):
    if chain_id in get_supported_chains():
        signer_key = os.environ.get("PREMIUM_COLLECTOR")
        signer_address = os.environ.get("PREMIUM_COLLECTOR_ADDRESS")
        return signer_key, signer_address
    return None, None

def get_networks(chains: list) -> list:
    networks = []
    for chain in chains:
        if chain in NETWORKS:
           networks.append(NETWORKS[chain])
    if len(networks) == 0:
        return None
    return networks

def get_soteria_billings(chain_id: str) -> dict:
    try:
        billings = json.loads(s3_get(S3_BILLINGS_FOLDER + chain_id + "/" + S3_BILLINGS_FILE))
        return billings
    except Exception as e:
        print(f"No billings file found for chain {chain_id}. Creating new one..")
        return {}

def get_billing_errors(chain_id: str) -> dict:
    try:
        billing_errors = json.loads(s3_get(S3_BILLINGS_FOLDER + chain_id + "/" + S3_BILLING_ERRORS_FILE))
        return billing_errors
    except Exception as e:
        print(f"No billings error file found for chain {chain_id}. Creating new one..")
        return {}
      
def get_soteria_score_files(chain_id: str) -> List:
    try:
        score_files = s3_get_files(S3_SOTERIA_SCORES_FOLDER + chain_id + "/")
        if score_files:
            score_files = list(filter(lambda score_file: score_file[-1] != '/' or 'archived' not in score_file , score_files))
        return score_files
    except Exception as e:
        print(e)
        return []

def get_soteria_score_file(chain_id: str, account: str):
    try:
        score_file = s3_get(S3_SOTERIA_SCORES_FOLDER + chain_id + "/" + account + ".json", cache=True)
        return score_file
    except Exception as e:
        print(e)
        return {}

def save_billings(chainId: str, billings: dict) -> bool:
    try:
        s3_put(S3_BILLINGS_FOLDER + chainId + "/" + S3_BILLINGS_FILE, json.dumps(billings))
        return True
    except Exception as e:
        handle_error({"resource": "utils.save_billings()"}, e, 500)
        return False

def save_billing_errors(chainId: str, billing_errors: dict) -> bool:
    try:
        s3_put(S3_BILLINGS_FOLDER + chainId + "/" + S3_BILLING_ERRORS_FILE, json.dumps(billing_errors))
        return True
    except Exception as e:
        handle_error({"resource": "utils.save_billing_errors()"}, e, 500)
        return False

def get_soteri_policies(chainId: str) -> list:
    cfg = get_config(chainId)
    if cfg is None:
        raise InputException(f"Bad request. Not found config for the chain id: {chainId}")

    block_number = cfg['w3'].eth.block_number
    policies = []
    # policy id starts from 1
    policy_count = cfg['soteriaContract'].functions.policyCount().call(block_identifier=block_number)
    for policy_id in range(1, policy_count+1):
        policyholder = cfg['soteriaContract'].functions.ownerOf(policy_id).call(block_identifier=block_number)
        coverlimit = cfg['soteriaContract'].functions.coverLimitOf(policy_id).call(block_identifier=block_number)

        # polygon supports multichain positions
        chains = []
        if chainId == "137":
            chains.append(cfg['soteriaContract'].functions.getPolicyChainInfo(policy_id).call(block_identifier=block_number))
        else:
            chains.append(1)
        policies.append({"address": policyholder, "coverlimit": coverlimit, "chains": chains})
    return policies
