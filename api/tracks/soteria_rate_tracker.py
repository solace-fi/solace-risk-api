from api.utils import *
from api.balances.get import get_balances
from api.scores.get import get_scores
from datetime import datetime
import asyncio
import json

async def get_positions(address: str, chain_id: str):
    return json.loads(get_balances({"account": address, "chain_id": chain_id}))


async def get_score(policyholder: dict, chain_id: str) -> bool:
    try:
        positions = await get_positions(policyholder["address"], chain_id)
        score = get_scores(policyholder["address"], positions)
      
        if score is None:
            raise Exception()
        score = json.loads(score)

        await store_rate(policyholder["address"], chain_id, policyholder["coverlimit"], score)
        return policyholder["address"], True
    except Exception as e:
        print(
            f"Error occurred while getting score info for: {policyholder}. Error: {e}"
        )
        return policyholder["address"], False


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
        policyholders = get_soteria_policy_holders(chain_id)
        tasks = []
        for policyholder in policyholders:
            print(f"Rate tracking for {policyholder} started...")
            tasks.append(asyncio.create_task(get_score(policyholder, chain_id)))

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
