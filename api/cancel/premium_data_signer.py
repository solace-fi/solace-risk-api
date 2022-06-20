from api.utils import *
from decimal import Decimal

SECP256_K1_N = int("fffffffffffffffffffffffffffffffebaaedce6af48a03bbfd25e8cd0364141", 16)
PREMIUM_DATA_SIGNER_KEY = "premium_data_signer_key.txt"
DOMAIN_NAME = "Solace.fi-SolaceSigner"
VERSION = "1"
TYPE_NAME = "PremiumData"

initialized = False
signerKeyID = ""
signerAddress = ""
verifyingContracts = {}
solaceSignerAbi = []

if not initialized:
    signerKeyID = swc_configs["signerKeyID"]
    signerAddress = swc_configs["signerAddress"]
    verifyingContracts = get_swc_contracts()
    solaceSignerAbi = json.loads(s3_get('abi/other/SolaceSigner.json', cache=True))
    initialized = True


def sign(premium, policyholder, chainID):

    # get config values
    if chainID not in verifyingContracts:
        raise Exception(f"Verifiying contract could not found chain {chainID}")

    deadline = int(datetime.now().timestamp()) + 3600 # one hour from now
    verifying_contract = verifyingContracts[chainID]["address"]
    w3 = verifyingContracts[chainID]["web3"]
    instance = verifyingContracts[chainID]["instance"]
    premium_normalized = w3.toWei(premium, 'ether')

    # sign the message so the user can submit it
    primitive = {
        "types": {
            "EIP712Domain": [
                { "name": "name", "type": "string" },
                { "name": "version", "type": "string" },
                { "name": "chainId", "type": "uint256" },
                { "name": "verifyingContract", "type": "address" }
            ],
            TYPE_NAME: [
                { "name": "premium", "type": "uint256" },
                { "name": "policyholder", "type": "address" },
                { "name": "deadline", "type": "uint256" }
            ]
        },
        "primaryType": TYPE_NAME,
        "domain": {
            "name": DOMAIN_NAME,
            "version": VERSION,
            "chainId": int(chainID),
            "verifyingContract": verifying_contract
        },
        "message": {
            "premium": premium_normalized,
            "policyholder": policyholder,
            "deadline": deadline
        }
    }

    # sign and verify it works
    isValid = False
    signature = ""
    while not isValid:
        try:
            block_number = w3.eth.block_number
            signature = sign_premium(primitive, signerKeyID)
            # verify signature
            isValid = instance.functions.verifyPremium(premium_normalized, policyholder, deadline, signature).call(block_identifier=block_number)
            print(f"Valid: {isValid}")
        except Exception as e:
            print(e)
            continue

    return {"premium_usd": premium, "premium": premium_normalized, "policyholder": policyholder,  "deadline": deadline,  "signature": signature}


def sign_premium(primitive, kms_key_id):
    # encode the message
    message = encode_structured_data(primitive=primitive)
    # hash the message
    # TODO: this gets the hash of the message by signing it first (with the old paclas signer with the plaintext key)
    # not a security issue, just an inefficiency
    private_key = s3_get(PREMIUM_DATA_SIGNER_KEY, cache=True)
    signed_message = w3auto.eth.account.sign_message(message, private_key=private_key)
    message_hash = signed_message.messageHash
    # download public key from KMS
    pub_key = get_kms_public_key(kms_key_id)
    # calculate the Ethereum public address from public key
    eth_checksum_addr = calc_eth_address(pub_key)
    # actually sign with KMS
    message_sig = find_eth_signature(kms_key_id=kms_key_id, plaintext=message_hash)
    # calculate v
    message_eth_recovered_pub_addr = get_recovery_id(msg_hash=message_hash,r=message_sig['r'],s=message_sig['s'],eth_checksum_addr=eth_checksum_addr)
    # assemble signature
    r = hex(message_sig['r'])[2:]
    s = hex(message_sig['s'])[2:]
    v = hex(message_eth_recovered_pub_addr['v'])[2:]
    signature = '0x{}{}{}'.format(r,s,v)
    return signature

class EthKmsParams:
    def __init__(self, kms_key_id: str, eth_network: str):
        self._kms_key_id = kms_key_id
        self._eth_network = eth_network
    def get_ksm_key_id(self) -> str:
        return self._kms_key_id

def get_params() -> EthKmsParams:
    for param in ['KMS_KEY_ID', 'ETH_NETWORK']:
        value = os.getenv(param)
        if not value:
            if param in ['ETH_NETWORK']:
                continue
            else:
                raise ValueError('missing value for parameter: {}'.format(param))
    return EthKmsParams(
        kms_key_id=os.getenv('KMS_KEY_ID'),
        eth_network=os.getenv('ETH_NETWORK')
    )

def get_kms_public_key(key_id: str) -> bytes:
    client = boto3.client('kms')
    response = client.get_public_key(
        KeyId=key_id
    )
    return response['PublicKey']

def sign_kms(key_id: str, msg_hash: bytes) -> dict:
    client = boto3.client('kms')
    response = client.sign(
        KeyId=key_id,
        Message=msg_hash,
        MessageType='DIGEST',
        SigningAlgorithm='ECDSA_SHA_256'
    )
    return response

def calc_eth_address(pub_key) -> str:
    SUBJECT_ASN = '''
    Key DEFINITIONS ::= BEGIN

    SubjectPublicKeyInfo  ::=  SEQUENCE  {
       algorithm         AlgorithmIdentifier,
       subjectPublicKey  BIT STRING
     }

    AlgorithmIdentifier  ::=  SEQUENCE  {
        algorithm   OBJECT IDENTIFIER,
        parameters  ANY DEFINED BY algorithm OPTIONAL
      }

    END
    '''
    key = asn1tools.compile_string(SUBJECT_ASN)
    key_decoded = key.decode('SubjectPublicKeyInfo', pub_key)
    pub_key_raw = key_decoded['subjectPublicKey'][0]
    pub_key = pub_key_raw[1:len(pub_key_raw)]
    # https://www.oreilly.com/library/view/mastering-ethereum/9781491971932/ch04.html
    hex_address = w3auto.keccak(bytes(pub_key)).hex()
    eth_address = '0x{}'.format(hex_address[-40:])
    eth_checksum_addr = w3auto.toChecksumAddress(eth_address)
    return eth_checksum_addr

def find_eth_signature(kms_key_id: str, plaintext: bytes) -> dict:
    SIGNATURE_ASN = '''
    Signature DEFINITIONS ::= BEGIN

    Ecdsa-Sig-Value  ::=  SEQUENCE  {
           r     INTEGER,
           s     INTEGER  }

    END
    '''
    signature_schema = asn1tools.compile_string(SIGNATURE_ASN)
    signature = sign_kms(kms_key_id, plaintext)
    # https://tools.ietf.org/html/rfc3279#section-2.2.3
    signature_decoded = signature_schema.decode('Ecdsa-Sig-Value', signature['Signature'])
    s = signature_decoded['s']
    r = signature_decoded['r']
    secp256_k1_n_half = SECP256_K1_N / 2
    if s > secp256_k1_n_half:
        s = SECP256_K1_N - s
    return {'r': r, 's': s}

def get_recovery_id(msg_hash, r, s, eth_checksum_addr) -> dict:
    for v in [27, 28]:
        recovered_addr = Account.recoverHash(message_hash=msg_hash,
                                             vrs=(v, r, s))
        if recovered_addr == eth_checksum_addr:
            return {'recovered_addr': recovered_addr, 'v': v}
    return {}
