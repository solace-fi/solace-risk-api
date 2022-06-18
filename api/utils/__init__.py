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
S3_VOLATILITY_CACHE_FOLDER = 'volatility-cache/'

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

def s3_get_zip(key, cache=False):
    if cache and key in s3_cache:
        return s3_cache[key]
    else:
        res = s3_client.get_object(Bucket=DATA_BUCKET, Key=key)["Body"].read()
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

    queryStringParameters = ""
    resource = ".unknown()"
    if event is not None:
        resource = event["resource"]
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

provider_config = json.loads(s3_get("provider_config.json", cache=True))

class InputException(Exception):
    pass

ETH_ADDRESS = "0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE"
ADDRESS_SIZE = 40 # 20 bytes or 40 hex chars
ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"
SOLACE_ADDRESS = "0x501acE9c35E60f03A2af4d484f49F9B1EFde9f40"
xSOLACE_ADDRESS = "0x501AcE5aC3Af20F49D53242B6D208f3B91cfc411"
SCP_ADDRESS = "0x501ACE72166956F57b44dbBcc531A8E741449997"
erc20Json = json.loads(s3_get("abi/other/ERC20.json", cache=True))
scpJson = json.loads(s3_get("abi/scp/SCP.json", cache=True))
ONE_ETHER = 1000000000000000000

# chainId => network
NETWORKS = {1: 'ethereum', 137: 'polygon', 250: 'fantom', 1313161554: 'aurora', 4: 'ethereum'}
swc_configs = json.loads(s3_get('swc_configs.json', cache=True))
referral_configs = json.loads(s3_get('referral_config.json', cache=True))
ZAPPER_API_KEY = s3_get('zapper.json', cache=True)
COVALENT_API_KEY = s3_get('covalent.json', cache=True)

def get_supported_chains():
    supported_chains = []
    for chain in swc_configs['supported_chains']:
        supported_chains.append(int(chain))
    return supported_chains

def get_billing_chains():
    if 'billing_chains' in swc_configs:
        return swc_configs['billing_chains']
    return []

def get_premium_collector(chain_id: str):
    if chain_id in get_supported_chains():
        signer_key = os.environ.get("PREMIUM_COLLECTOR")
        signer_address = os.environ.get("PREMIUM_COLLECTOR_ADDRESS")
        return signer_key, signer_address
    return None, None

def get_networks(chains: list) -> list:
    networks = []
    for chain in chains:
        if int(chain) in NETWORKS:
            networks.append(NETWORKS[int(chain)])
    if len(networks) == 0:
        return None
    return networks

def get_swc_billing_data_from_s3(chain_id: str) -> dict:
    try:
        billings = json.loads(s3_get(S3_BILLINGS_FOLDER + chain_id + "/" + S3_BILLINGS_FILE))
        return billings
    except Exception as e:
        print(f"No billings file found for chain {chain_id}. Creating new one..")
        return {}

def get_swc_billing_error_data_from_s3(chain_id: str) -> dict:
    try:
        billing_errors = json.loads(s3_get(S3_BILLINGS_FOLDER + chain_id + "/" + S3_BILLING_ERRORS_FILE))
        return billing_errors
    except Exception as e:
        print(f"No billings error file found for chain {chain_id}. Creating new one..")
        return {}
      
def get_swc_score_files_from_s3(chain_id: str) -> List:
    try:
        score_files = s3_get_files(S3_SOTERIA_SCORES_FOLDER + chain_id + "/")
        if score_files:
            score_files = list(filter(lambda score_file: score_file[-1] != '/' or 'archived' not in score_file , score_files))
        return score_files
    except Exception as e:
        print(e)
        return []
    

def get_swc_score_file_from_s3(chain_id: str, account: str):
    try:
        score_file = s3_get(S3_SOTERIA_SCORES_FOLDER + chain_id + "/" + account + ".json", cache=True)
        return score_file
    except Exception as e:
        print(e)
        return {}

def save_billings_data_to_s3(chainId: str, billings: dict) -> bool:
    try:
        s3_put(S3_BILLINGS_FOLDER + chainId + "/" + S3_BILLINGS_FILE, json.dumps(billings))
        return True
    except Exception as e:
        handle_error({"resource": "utils.save_billings()"}, e, 500)
        return False

def save_billing_error_data_s3(chainId: str, billing_errors: dict) -> bool:
    try:
        s3_put(S3_BILLINGS_FOLDER + chainId + "/" + S3_BILLING_ERRORS_FILE, json.dumps(billing_errors))
        return True
    except Exception as e:
        handle_error({"resource": "utils.save_billing_errors()"}, e, 500)
        return False

def get_swc_contracts():
    # get supported chains
    if 'supported_chains' not in swc_configs:
        raise Exception(f"No config found for supported chains")
    supported_chains = swc_configs['supported_chains']

    contract_info = {}
    for chain in supported_chains:
        # web3
        if chain not in provider_config:
            raise Exception(f"No web3 config found for chain {chain}")
        w3 = Web3(Web3.HTTPProvider(provider_config[chain]))
    
        # contracts
        if "contract" not in swc_configs[chain]:
            raise Exception(f"No contract config found for chain {chain}")
        
        contract = swc_configs[chain]["contract"] 
        if type(contract) != dict:
            raise Exception(f"No contract config found for chain {chain}")
    
        abi = json.loads(s3_get(contract["abi"], cache=True))
        try:
            instance = w3.eth.contract(address=contract["address"], abi=abi)
            contract_info[chain] = { "instance": instance, "web3": w3, "address": contract["address"]}
        except Exception as e:
            print(f"Error occured while creating swc contract instance for chain {chain}")
    return contract_info


def get_scp(chain: str):
    if chain not in get_billing_chains():
        raise Exception(f"Chain {chain} is not in supported billing chains")
    
    if chain not in provider_config:
        raise Exception(f"No web3 config found for chain {chain}")
    w3 = Web3(Web3.HTTPProvider(provider_config[chain]))
    scp = w3.eth.contract(address=SCP_ADDRESS, abi=scpJson)
    return scp


