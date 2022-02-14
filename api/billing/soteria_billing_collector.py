from api.billing.helpers import *
from api.utils import *

def collect_premiums():
    for chain_id in get_supported_chains():
        try:
            signer_key, signer_address = get_premium_collector(chain_id)
            if signer_key is None or signer_address is None:
                raise Exception(f"No premium collector address")

            print(f"Charging premiums for chain {chain_id} has been started...")
            soteria_premiums = get_soteria_premiums(chain_id)
            
            if len(soteria_premiums) == 0:
                print(f"No premium is found for chain {chain_id}")
                continue

            cfg = get_config(chain_id)
            w3: Web3 = cfg["w3"]
            premiums = []
            policyholders = []

            for soteria_premium in soteria_premiums:
                policyholders.append(w3.toChecksumAddress(soteria_premium["account"]))
                premiums.append(int(soteria_premium["premium"] * 10**18))
            
            print(policyholders)
            print(premiums)

            if "soteriaContract" not in cfg:
                raise Exception(f"Soteria contract could not found for chain {chain_id} ")

            soteria_contract = cfg["soteriaContract"]
            nonce = w3.eth.getTransactionCount(signer_address)
           
            # TODO: change hard coded chain id
            tx = soteria_contract.functions.chargePremiums(policyholders, premiums).buildTransaction({"chainId": 4, "from": signer_address, "nonce": nonce})
            tx_signed = w3.eth.account.sign_transaction(tx, private_key=signer_key)
            tx_hash = w3.eth.send_raw_transaction(tx_signed.rawTransaction)
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            print(tx_receipt)

            # save results
            timestamp = get_timestamp()
            for i in range(len(premiums)):
                print(f"Premium charged for account: {policyholders[i]}. Premium(USD): {premiums[i]}")
                post_premium_charged(chain_id, policyholders[i], timestamp)

            print(f"Charging premiums for chain {chain_id} has been finished.")
        except Exception as e:
            print(f"Error occurred while charging premiums for chain {chain_id}. Error: {e}")

def main(event, context):
    collect_premiums()

if __name__ == '__main__':
    main(None, None)
