from api.billing.helpers import *
from api.referral.handler import get_reward_info, update_used_rewards
from api.utils import *
import math

def collect_premiums():
    if len(get_billing_chains()) == 0:
        print("No supported chain to collect billings")
        return

    swc_contracts = get_swc_contracts()
    for chain_id in get_billing_chains():
        try:
            print(f"Charging premiums for chain {chain_id} has been started...")

            # get chain contract
            if chain_id not in swc_contracts:
                print(f"No swc contract instance found for chain {chain_id}")
                continue
            swc =  swc_contracts[chain_id]["instance"]
            w3  =  swc_contracts[chain_id]["web3"]

            # get collector
            signer_key, signer_address = get_premium_collector(chain_id)
            if signer_key is None or signer_address is None:
                raise Exception(f"No premium collector address")

            # check collector balance
            collector_balance = w3.eth.get_balance(signer_address)
            amount = collector_balance / 10**18
            if amount == 0 or (chain_id == "1" and amount < 0.2):
                message = f"The premium collector {signer_address} has no enough balance to run transactions\nBalance(Wei): {collector_balance}\nBalance(Ether): {amount}"
                print(message)
                sns_publish(message)
                continue
         
            # get scp contract
            scp = get_scp(chain=chain_id)

            # check collector is scp mover
            is_scp_mover = scp.functions.isScpMover(signer_address).call()
            if not is_scp_mover:
                raise Exception(f"The premium collector {signer_address} is not SCP mover.")

            # get premiums
            swc_premiums = get_soteria_premiums(chain_id)
            
            # filter zero premiums
            swc_premiums = list(filter(lambda swc_premium: swc_premium['premium'] > 0, swc_premiums))
            if len(swc_premiums) == 0:
                print(f"No premium is found for chain {chain_id}")
                continue
            
            paid_accounts = []
            print("\nPaying with rewards =========================================================================================>>")
            # first pay with policyholders's rewards
            for swc_premium in swc_premiums:
                swc_premium["used_rewards"] = 0
                account = swc_premium["account"]
                try:
                    reward_info = get_reward_info(account)
                    if reward_info is None:
                        continue

                    promo_rewards = reward_info["promo_rewards"]
                    referred_earns = reward_info["referred_earns"]
                    used_rewards = reward_info["used_rewards"]
                    current_premium = swc_premium["premium"]
                    spendable_rewards = (promo_rewards + referred_earns) - used_rewards

                    if spendable_rewards == 0:
                        continue

                    current_used_reward = 0
                    if spendable_rewards >= current_premium:
                        # pay with all rewards
                        current_used_reward = used_rewards + current_premium
                        swc_premium["premium"] = 0
                        paid_accounts.append(account)
                        print(f"Premium paid with rewards. User: {account}, Premium: {current_premium}, Rewards(Used): {current_premium}")
                    else:
                        # pay with partial rewards
                        current_used_reward = used_rewards + spendable_rewards
                        swc_premium["premium"] = current_premium - spendable_rewards
                        print(f"Premium partially paid with rewards. User: {account}, Premium: {current_premium}, Rewards(Used): {spendable_rewards}")

                    update_used_rewards(account, float(current_used_reward))
                except Exception as e:
                    print(f"Error occurred while getting reward infor for user {account}. Premium will be charged as usual.")
                    continue
            
            # filter zero premiums
            swc_premiums = list(filter(lambda swc_premium: swc_premium['premium'] > 0, swc_premiums))

            print("\nChecking will be cannceled policies =========================================================================>>")
            # check will be cancelled accounts
            cancel_subscriptions = []
            for premium in swc_premiums:
                scp_amount = scp.functions.balanceOf(premium["account"]).call() / 10**18
                if scp_amount < premium["premium"]:
                    premium["premium"] = scp_amount
                    cancel_subscriptions.append(premium["account"])

            swc_premiums = list(filter(lambda swc_premium: swc_premium['premium'] > 0, swc_premiums))
            total_amount = sum(list(map(lambda premium: premium["premium"], swc_premiums)))
            if len(swc_premiums) == 0:
                print(f"There is no premium to charge in chain {chain_id}")
                continue

            print("\n#################################################")
            print(f"Total premium count: {len(swc_premiums)}")
            print(f"Total premium amount: {total_amount}")
            print(f"Total will be cancelled policy count: {len(cancel_subscriptions)}")
            print("#################################################\n")

            print("\nPaying with SCP =============================================================================================>>")
            batch_count = math.ceil(len(swc_premiums) / 100)
            for batch in range(0, batch_count):
                swc_premium_batches = swc_premiums[batch*100:(batch+1)*100]
               
                policyholders = []
                premiums = []
                for swc_premium in swc_premium_batches:
                    policyholders.append(w3.toChecksumAddress(swc_premium["account"]))
                    premiums.append(int(swc_premium["premium"] * 10**18))
                # create tx
                nonce = w3.eth.getTransactionCount(signer_address)
            
                tx = scp.functions.burnMultiple(policyholders, premiums).buildTransaction({"chainId": int(chain_id), "from": signer_address, "nonce": nonce})
                tx_signed = w3.eth.account.sign_transaction(tx, private_key=signer_key)
                tx_hash = w3.eth.send_raw_transaction(tx_signed.rawTransaction)
                tx_receipt = dict(w3.eth.wait_for_transaction_receipt(tx_hash))

                # save results
                if tx_receipt["status"] == 1:
                    paid_accounts = paid_accounts + policyholders
                    print(f"Transaction for charging premiums for chain {chain_id} was successful. Tx hash: {tx_hash}")
                else:
                    print(f"Transaction for charging premium for chain {chain_id} was unsuccesful. Tx hash: {tx_hash}")
            # save results
            save_premiums_charged(chain_id, paid_accounts)
           
            print("\Setting premium charged time =============================================================================================>>")
            # create set latest charged time tx
            charged_time = int(datetime.now().timestamp())
            print(f"Setting charged timestamp {charged_time} for chain {chain_id}")
            nonce = w3.eth.getTransactionCount(signer_address)
            tx = swc.functions.setChargedTime(charged_time).buildTransaction({"chainId": int(chain_id), "from": signer_address, "nonce": nonce})
            tx_signed = w3.eth.account.sign_transaction(tx, private_key=signer_key)
            tx_hash = w3.eth.send_raw_transaction(tx_signed.rawTransaction)
            tx_receipt = dict(w3.eth.wait_for_transaction_receipt(tx_hash))
            if tx_receipt["status"] == 1:
                print(f"Transaction for setting latest charge time in chain {chain_id} was successful. Tx hash: {tx_hash}")
            else:
                print(f"Transaction for setting latest charge time in chain {chain_id} was unsuccessful. Tx hash: {tx_hash}")

            print("\nCancelling policies =============================================================================================>>")
            # create cancel policies tx
            if len(cancel_subscriptions) > 0:
                print(f"There is/are {len(cancel_subscriptions)} account to cancel policies. Cancelling them..")
                print(f"Accounts: {cancel_subscriptions}")
                nonce = w3.eth.getTransactionCount(signer_address)
                tx = swc.functions.cancelPolicies(cancel_subscriptions).buildTransaction({"chainId": int(chain_id), "from": signer_address, "nonce": nonce})
                tx_signed = w3.eth.account.sign_transaction(tx, private_key=signer_key)
                tx_hash = w3.eth.send_raw_transaction(tx_signed.rawTransaction)
                tx_receipt = dict(w3.eth.wait_for_transaction_receipt(tx_hash))
                if tx_receipt["status"] == 1:
                    print(f"Transaction for cancelling policies in chain {chain_id} was successful. Tx hash: {tx_hash}")
                else:
                    print(f"Transaction for cancelling policies in chain {chain_id} was unsuccessful. Tx hash: {tx_hash}")

        except Exception as e:
            print(f"Error occurred while charging premiums for chain {chain_id}. Error: {e}")


def main(event, context):
    try:
        collect_premiums()
        return {
            "statusCode": 200,
            "headers": headers
        }
    except Exception as e:
        return handle_error(event, e, 500)
