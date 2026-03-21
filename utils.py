# utils.py

def calculate_unit_percentage(local_balance, percentage):
    if local_balance is None or percentage is None:
        return 0  # or return None based on business logic
    return local_balance * percentage

def calculate_moyenne(stocks):
    """
    Calculate MOYENNE = sum(unit%) / sum(balance)
    stocks: list of stock records
    """
    total_unit_percent = sum([s.unit_percent for s in stocks])
    total_balance = sum([s.input_kg for s in stocks])
    if total_balance == 0:
        return 0
    return total_unit_percent / total_balance

def calculate_net_balance(stock):
    """
    Calculate NET BALANCE = AMOUNT - TOT.AMOUNT TAG - RMA - INKOMANE - 3%RRA
    """
    return (
    (stock.amount or 0)
    - (stock.tot_amount_tag or 0)
    - (stock.rma or 0)
    - (stock.inkomane or 0)
    - (stock.rra_3_percent or 0)
)


def calculate_total_balance(stocks):
    """
    Rolling sum of NET BALANCE for all previous stocks
    """
    total = 0
    for s in stocks:
        total += s.net_balance
    return total
