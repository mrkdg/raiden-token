from populus.utils.wait import wait_for_transaction_receipt
from ecdsa import SigningKey, SECP256k1
import sha3
from ethereum.utils import encode_hex

from web3.formatters import input_filter_params_formatter, log_array_formatter
from web3.utils.events import get_event_data
from web3.utils.filters import construct_event_filter_params


def createWallet():
    keccak = sha3.keccak_256()
    priv = SigningKey.generate(curve=SECP256k1)
    pub = priv.get_verifying_key().to_string()
    keccak.update(pub)
    address = keccak.hexdigest()[24:]
    return (encode_hex(priv.to_string()), address)


def check_succesful_tx(web3, txid, timeout=180) -> dict:

    receipt = wait_for_transaction_receipt(web3, txid, timeout=timeout)
    txinfo = web3.eth.getTransaction(txid)

    # EVM has only one error mode and it's consume all gas
    assert txinfo["gas"] != receipt["gasUsed"]
    return receipt


class LogFilter:
    def __init__(self,
        web3,
        abi,
        address,
        event_name,
        from_block=0,
        to_block='latest',
        filters=None,
        callback=None):
        self.web3 = web3
        filter_kwargs = {
            'fromBlock': from_block,
            'toBlock': to_block,
            'address': address
        }
        self.event_abi = [i for i in abi if i['type'] == 'event' and i['name'] == event_name][0]
        assert self.event_abi
        filters = filters if filters else {}
        self.filter = construct_event_filter_params(
            self.event_abi,
            argument_filters=filters,
            **filter_kwargs)[1]
        filter_params = input_filter_params_formatter(self.filter)

        self.filter = web3.eth.filter(filter_params)

        for log in self.get_logs():
            callback(log)

        self.watch_logs(callback)

    def get_logs(self):
        response = self.web3.eth.getFilterLogs(self.filter.filter_id)
        logs = log_array_formatter(response)
        logs = [dict(log) for log in logs]
        for log in logs:
            log = self.set_log_data(log)
        return logs

    def set_log_data(self, log):
        log['args'] = get_event_data(self.event_abi, log)['args']
        return log

    def watch_logs(self, callback):
        def log_callback(log):
            callback(self.set_log_data(log))

        self.filter.watch(log_callback)

    def stop(self):
        self.filter.stop_watching()
        self.web3.eth.uninstallFilter(self.filter.filter_id)


def watch_logs(contract, event, callback, params={}):
    transfer_filter = contract.on(event, params)
    transfer_filter.watch(callback)


def print_logs(contract, event, name=''):
    watch_logs(contract, event, lambda x: print('--(', name, ') event ', event, x['args']))


# We don't need this anymore, as the auction funds go to the owner after all tokens are claimed
# Return funds to owner, so we keep most of the ETH in the simulation
def returnFundsToOwner(web3, owner, bidders):
    for bidder in bidders:
        # Return most ETH to owner
        value = web3.eth.getBalance(bidder)
        gas_estimate = web3.eth.estimateGas({'from': bidder, 'to': owner, 'value': value}) + 10000
        value -= gas_estimate

        if value < 0:
            continue

        # We have to unlock the account first
        unlocked = web3.personal.unlockAccount(bidder, passphrase)
        txhash = web3.eth.sendTransaction({'from': bidder, 'to': owner, 'value': value})
        receipt = check_succesful_tx(web3, txhash, tx_timeout)


def assignFundsToBidders(web3, owner, bidders):
    approx_bid_txn_cost = 40000
    # Transfer some testnet ether to the bidders
    print('Assign random ETH amounts to bidders')

    # Make sure we have some 1 ETH bids
    txhash = web3.eth.sendTransaction({'from': owner, 'to': bidders[0], 'value': 1 + approx_bid_txn_cost})
    receipt = check_succesful_tx(web3, txhash, tx_timeout)

    txhash = web3.eth.sendTransaction({'from': owner, 'to': bidders[1], 'value': 1 + approx_bid_txn_cost})
    receipt = check_succesful_tx(web3, txhash, tx_timeout)

    txhash = web3.eth.sendTransaction({'from': owner, 'to': bidders[2], 'value': 2 + approx_bid_txn_cost})
    receipt = check_succesful_tx(web3, txhash, tx_timeout)

    # Make sure bidders have random ETH
    for i in range(3, bidders_len - 1):
        bidder = bidders[i]
        owner_balance = web3.eth.getBalance(owner)
        max_bid = int(owner_balance / (bidders_len - i))
        max_bid = max(max_bid, 10**18 * 5)
        value = random.randint(max_bid / 2, max_bid)
        print('i', i, bidder, amount_format(web3, value))

        txhash = web3.eth.sendTransaction({'from': owner, 'to': bidder, 'value': value})
        receipt = check_succesful_tx(web3, txhash, tx_timeout)

    owner_balance = web3.eth.getBalance(owner)
    if owner_balance > 0:
        bidder = bidders[bidders_len - 1]
        value = owner_balance - approx_payable_txn_cost
        print('i', bidders_len - 1, bidder, amount_format(web3, value))

        txhash = web3.eth.sendTransaction({'from': owner, 'to': bidders[bidders_len - 1], 'value': value})
        receipt = check_succesful_tx(web3, txhash, tx_timeout)