from api.utils import *
from api.balances.get import get_balances
from api.scores.get import get_scores
import asyncio
import json
import time

async def get_positions(policy: dict):
    return json.loads(get_balances({"account": policy["address"], "chains": policy["chains"]}))


async def get_score(policy: dict, chain_id: str, request_count: int) -> bool:
    try:
        positions = await get_positions(policy)
        if len(positions) == 0:
            print(f"No position found for account: {policy['address']}")
            return policy["address"], False

        score = get_scores(policy["address"], positions)
      
        if score is None:
            raise Exception()
        score = json.loads(score)

        await store_rate(policy["address"], chain_id, policy["coverlimit"], score)
        return policy["address"], True
    except Exception as e:
        print(
            f"Error occurred while getting score info for: {policy}. Error: {e}"
        )
        return policy["address"], False


async def store_rate(address: str, chain_id: str, coverlimit: float, score: any):
    try:
        scores_s3 = s3_get(S3_SOTERIA_SCORES_FOLDER + chain_id + "/" + address + '.json')
        scores = json.loads(scores_s3)
    except Exception as e:
        print(f"No score tracking file is found for {address} in chain {chain_id}. Creating a new one.")
        scores = {'scores': []}
    
    if "address" in score:
        del score["address"]

    data = {'timestamp': score['timestamp'], 'coverlimit': coverlimit, 'score': score}
    scores['scores'].append(data)
    s3_put(S3_SOTERIA_SCORES_FOLDER + chain_id + "/" + address + ".json", json.dumps(scores))
    

async def track_policy_rates():
    for chain_id in get_supported_chains():
        print(f"Starting Soteria rate tracker for chain {chain_id}...")
        policies = get_soteri_policies(chain_id)

        if len(policies) == 0:
            print(f"No policy to track for chain {chain_id}")
            return
        
        tasks = []
        request_count = 0
        for policy in policies:
            print(f"Rate tracking for {policy} started...")
            request_count += 1
            tasks.append(asyncio.create_task(get_score(policy, chain_id, request_count)))

        try:
            completed_tasks, _ = await asyncio.wait(tasks)
            for completed_task in completed_tasks:
                result = completed_task.result()
                address = result[0]
                status = "successful" if result[1] else "unsuccessful"
                print(f"Rate tracking for: {address} was {status}. Chain id: {chain_id}")
        except Exception as e:
                print(f"Error occurred while tracking policy rates. Chain Id: {chain_id}, Error: {e}")
        print(f"Soteria rate tracking for chain {chain_id} has been finished")

def main(event, context):
    asyncio.run(track_policy_rates())

if __name__ == "__main__":
    main(None, None)
