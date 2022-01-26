from api.billing.helpers import *
from api.utils import *

def collect_premiums():
    for chain_id in get_supported_chains():
        try:
            print(f"Charging premiums for chain {chain_id} has been started...")
            soteria_premiums = get_soteria_premiums(chain_id)
            
            if len(soteria_premiums) == 0:
                print(f"No premium is found for chain {chain_id}")
                continue

            premiums = []
            policyholders = []
            for soteria_premium in soteria_premiums:
                policyholders.append(soteria_premium["account"])
                premiums.append(soteria_premium["premium_in_eth"])
            
            print(policyholders)
            print(premiums)

            # TODO: Make contract call to charge premiums
            signer = get_premium_collector_signer(chain_id)
            cfg = get_config(chain_id)
            if "soteriaContract" not in cfg:
                raise Exception(f"Soteria contract could not found for chain {chain_id} ")
            soteria_contract = cfg["soteriaContract"]
            w3 = cfg["w3"]

            # save results
            # TODO: Get timestamp from transaction
            timestamp = get_timestamp()
            for i in range(len(premiums)):
                print(f"Premium charged for account: {policyholders[i]}. Premium(eth): {premiums[i]}")
                post_premium_charged(chain_id, policyholders[i], timestamp)

            print(f"Charging premiums for chain {chain_id} has been finished.")
        except Exception as e:
            print(f"Error occurred while charging premiums for chain {chain_id}. Error: {e}")

def main(event, context):
    collect_premiums()

if __name__ == '__main__':
    main(None, None)
