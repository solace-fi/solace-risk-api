from api.utils import *
from api.balances.get import get_balances
from api.scores.get import get_scores
from datetime import datetime
import asyncio
import json

SOTERIA_SCORES_BUCKET_NAME = 'soteria-scores/'
# 1=ethereum mainnet
CHAIN_IDS = ['1']

async def get_positions(address: str, chainId: str):
    return json.loads(get_balances({"account": address, "chainId": chainId}))


async def get_score(policyholder: dict(), chainId: str) -> bool:
    try:
        positions = await get_positions(policyholder["address"], chainId)
        score = json.loads(get_scores(policyholder["address"], positions))
        await store_rate(policyholder["address"], chainId, policyholder["coverLimit"], score)
        return policyholder["address"], True
    except Exception as e:
        print(
            f"Error occurred while getting score info for: {policyholder}. Error: {e}"
        )
        return policyholder["address"], False


async def store_rate(address: str, chainId: str, coverLimit: float, score: any):
    try:
        scores_s3 = s3_get(SOTERIA_SCORES_BUCKET_NAME + chainId + "/" + address + '.json')
        scores = json.loads(scores_s3)
    except Exception as e:
        print(f"No score tracking file is found for {address} in chain {chainId}. Creating a new one.")
        scores = {'scores': []}
    
    if "address" in score:
        del score["address"]
    if "metadata" in score:
        del score["metadata"]

    data = {'timestamp': datetime.now().strftime("%d/%m/%Y, %H:%M:%S"), 'coverlimit': coverLimit, 'score': score}
    scores['scores'].append(data)
    s3_put(SOTERIA_SCORES_BUCKET_NAME + chainId + "/" + address + ".json", json.dumps(scores))
    

async def track_policy_rates():
    for chainId in get_supported_chains():
        policyholders = get_soteria_policy_holders(chainId)
        tasks = []
        for policyholder in policyholders:
            tasks.append(asyncio.create_task(get_score(policyholder, chainId)))

            try:
                completed_tasks, _ = await asyncio.wait(tasks)
                for completed_task in completed_tasks:
                    result = completed_task.result()
                    address = result[0]
                    status = "successful" if result[1] else "unsuccessful"
                    print(f"Rate tracking for: {address} was {status}")
            except Exception as e:
                print(f"Error occurred while tracking policy rates. Chain Id: {chainId}, Error: {e}")


if __name__ == "__main__":
    asyncio.run(track_policy_rates())
