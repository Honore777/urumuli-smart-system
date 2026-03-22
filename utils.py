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


# Async email helper
from threading import Thread
import threading as _threading
import logging
from flask import current_app


def _send_async_email(app, mail, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception:
            # use app logger to record failure
            try:
                app.logger.exception("Async mail send failed")
            except Exception:
                pass


def send_email(mail, msg):
    """Send `msg` using `mail` in a background thread to avoid blocking requests."""
    try:
        app = current_app._get_current_object()
    except Exception:
        # fallback: call synchronously if current_app not available
        try:
            mail.send(msg)
        except Exception:
            pass
        return

    # Log enqueue and active thread count for monitoring
    try:
        app.logger.info("Enqueuing email to %s", getattr(msg, 'recipients', None))
    except Exception:
        try:
            logging.info("Enqueuing email to %s", getattr(msg, 'recipients', None))
        except Exception:
            pass

    try:
        # print active thread count to console for quick monitoring
        count = _threading.active_count()
        app.logger.info("Active threads before enqueue: %d", count)
        print(f"[email] Active threads: {count}")
    except Exception:
        pass

    t = Thread(target=_send_async_email, args=(app, mail, msg), daemon=True)
    t.start()
