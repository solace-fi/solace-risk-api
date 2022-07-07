from api.utils import *
import math


# constants
S3_SCORE_TRACKER_CODE_FOLDER = "score-tracker-functions"
EVENT_RULE_NAME = 'score_tracker_event'
SPLIT_NUMBER = 100

LAMBDA_FUNCTION_NAME_MAP = {
    '1':   "SolaceRiskDataMainnetScoreTrackerFunction",
    '137': "SolaceRiskDataPolygonScoreTrackerFunction",
    '205': "SolaceRiskDataFantomScoreTrackerFunction",
    '1313161554': "SolaceRiskDataAuroraScoreTrackerFunction",

}

CODE_MAP = {
    '1': "mainnet",
    '137': "polygon",
    '205': "fantom",
    '1313161554': "aurora"
}

# aws clients
iam_client = boto3.client('iam')
lambda_client = boto3.client('lambda', region_name="us-west-2")
event_client = boto3.client('events')

def get_role():
   role = iam_client.get_role(RoleName='SolaceRiskDataLambdaExecutionRole')
   return role

def create_event():
    event = event_client.put_rule(Name=EVENT_RULE_NAME, ScheduleExpression='rate(60 minutes)', State='ENABLED')
    return event

def get_code(chain):
    filename = None
    if CODE_MAP[chain] == 'polygon':
        filename = 'polygon.zip'
    elif CODE_MAP[chain] == 'mainnet':
        filename = 'mainnet.zip'
    elif CODE_MAP[chain] == 'fantom':
        filename = 'fantom.zip'
    elif CODE_MAP[chain] == 'aurora':
        filename = 'aurora.zip'
    else:
        raise Exception(f"Unsupported network name for chain {chain}")

    print(S3_SCORE_TRACKER_CODE_FOLDER + "/" + filename)
    code = s3_get_zip(S3_SCORE_TRACKER_CODE_FOLDER + "/" + filename, cache=True)
    return code

def get_tracker_lambda_function_count(chain):
    function_name = LAMBDA_FUNCTION_NAME_MAP[chain]
    result = lambda_client.list_functions()
    function_count = 0
    for function in result['Functions']:
        if function['FunctionName'].startswith(function_name):
            print(f"Function Name ==> {function['FunctionName']}")
            function_count += 1
    return function_count

def get_scaling_info():
    contracts = get_swc_contracts()
    policy_counts = dict()
    for chain, contract in contracts.items():
        if chain not in policy_counts:
            policy_counts[chain] = 0
        policy_counts[chain] += contract["instance"].functions.totalSupply().call()

    scales = []
    for chain, count in policy_counts.items():
        if count <= SPLIT_NUMBER:
            continue
       
        function_count = get_tracker_lambda_function_count(chain=chain)
        required_count = math.ceil(count / SPLIT_NUMBER)
        print(f"Policy Count: {count} Function Count: {function_count} Required Count: {required_count} Chain: {chain}")
        if function_count >= required_count:
            continue

        #scales.append({"chain": chain, "id_start": function_count + 1, "id_end": required_count})
        scales.append({"chain": chain, "id_start": 4, "id_end": 4})

    return scales

def main(event, context):
    try:
        print(f"Rate tracker scaler has been started..")
        scales = get_scaling_info()

        if len(scales) == 0:
            print(f"There is no scaling need")
        
        # get lambda execution role
        role = get_role()
        # create/retrieve scheduler rule
        create_event()

        for scale_info in scales:
            chain = scale_info["chain"]
            code = get_code(chain)
            start = scale_info["id_start"]
            end = scale_info["id_end"]
            for tracker_id in range(start, end+1):
                function_name = LAMBDA_FUNCTION_NAME_MAP[chain] + str(tracker_id)
                handler = CODE_MAP[chain] + "." + "main"
                print(f"Deploying new lambda function. Lambda name: {function_name}")
                
                response = lambda_client.create_function(
                    FunctionName=function_name,
                    Runtime='python3.8',
                    Role=role['Role']['Arn'],
                    Handler=handler,
                    Code=dict(ZipFile=code),
                    Timeout=300,
                    Environment={
                        'Variables': {
                            'tracker_id': str(tracker_id)
                        }
                    },
                )
                # setup scheduler
                event_client.put_targets(Rule=EVENT_RULE_NAME, Targets=[{'Arn': response['FunctionArn'], 'Id': response['RevisionId']}])
        print(f"Rate tracker scaler finished ")
    except Exception as e:
        print(e)
        #return handle_error(event, e, 500)

if __name__ == '__main__':
    main(None, None)