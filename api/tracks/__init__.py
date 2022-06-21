from api.utils import *
from api.balances.get import get_balances
from api.scores.get import get_scores

class BaseRateTracker:
    def __init__(self, chain: str, tracker_id: int):
        self.chain = chain
        self.tracker_id = tracker_id if tracker_id > 0 else 1
        self.contract = None
        self.w3 = None
        self.supported_chains = get_supported_chains()
        self.__set_configs()

    def get_name(self):
        pass

    def get_tracker_id(self):
        return self.tracker_id        

    def __set_configs(self):
        contract_info = get_swc_contracts()
        if self.chain not in contract_info:
            raise Exception(f"{self.get_name()}: No contract info found for chain {self.chain}")
        self.contract = contract_info[self.chain]["instance"]
        self.w3 = contract_info[self.chain]["web3"]

    def get_policies(self) -> list:
        block_number = self.w3.eth.block_number
        policies = []

        if self.contract:
            policy_count = self.contract.functions.totalSupply().call(block_identifier=block_number)
            start_index = (self.tracker_id - 1) * 100 + 1
            end_index = (self.tracker_id * 100) + 1

            if policy_count < (end_index-1):
                end_index = policy_count + 1
            print(f"Total policy count: {policy_count}\nPolicyID Start: {start_index}\nPolicyID End: {end_index-1}")

            for policy_id in range(start_index, end_index):
                policyholder = self.contract.functions.ownerOf(policy_id).call(block_identifier=block_number)
                coverlimit   = self.contract.functions.coverLimitOf(policy_id).call(block_identifier=block_number)
                policies.append({"address": policyholder, "coverlimit": coverlimit, "chains": self.supported_chains})
        return policies

    def store_rate(self, address: str, coverlimit: float, score: any):
        try:
            chain = self.chain
            score_file = S3_SOTERIA_SCORES_FOLDER + chain + "/" + address + '.json'
            scores_s3 = s3_get(score_file)
            scores = json.loads(scores_s3)
        except Exception as e:
            print(f"No score tracking file is found for {address} in chain {chain}. Creating a new one.")
            scores = {'scores': []}
        
        if "address" in score:
            del score["address"]
        
        data = {'timestamp': score['timestamp'], 'coverlimit': coverlimit, 'score': score}
        scores['scores'].append(data)
        s3_put(score_file, json.dumps(scores))

    def get_positions(self, policy: dict):
        return json.loads(get_balances({"account": policy["address"], "chains": policy["chains"]}, max_cache_age=86400))

    def get_score(self, policy: dict) -> bool:
        try:
            positions =  self.get_positions(policy)
            if len(positions) == 0:
                print(f"No position found for account: {policy['address']}")
                return policy["address"], False

            score = get_scores(policy["address"], positions)
        
            if score is None:
                raise Exception()
            score = json.loads(score)

            self.store_rate(policy["address"], policy["coverlimit"], score)
            return policy["address"], True
        except Exception as e:
            print(f"Error occurred while getting score info for: {policy}. Error: {e}")
            return policy["address"], False

    def track(self):
        try:
            print(f"{self.get_name()}({self.tracker_id}) has been started..")
            for policy in self.get_policies():
                print(f"Calculating rate score for {policy}...")
                address, result = self.get_score(policy)
                status = "successful" if result else "unsuccessful"
                print(f"Calculating rate score for {address} was {status}.")
            print(f"{self.get_name()} has been finished")
        except Exception as e:
            print(f"{self.get_name()}({self.tracker_id}): Error occurred while tracking policy rates. Chain Id: {self.chain}, Error: {e}")
