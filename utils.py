# utils.py

import os
import time
import logging
import functools
from flask import current_app

# Configure simple app-wide logging. Control level with the LOG_LEVEL env var.
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def trace_time(func):
    """Decorator to log execution time of functions.

    Usage:
        @trace_time
        def heavy():
            ...
    Logs an INFO line with elapsed seconds after the call. If an exception
    occurs, logs the full traceback using `current_app.logger.exception` when
    available, otherwise falls back to the module logger.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            # Prefer app logger when running inside Flask app context
            try:
                current_app.logger.exception("Exception in %s", func.__name__)
            except Exception:
                logger.exception("Exception in %s", func.__name__)
            raise
        finally:
            end = time.perf_counter()
            try:
                try:
                    current_app.logger.info("TIMER: %s took %.4f seconds", func.__name__, end - start)
                except Exception:
                    logger.info("TIMER: %s took %.4f seconds", func.__name__, end - start)
            except Exception:
                pass

        return result

    return wrapper


def update_stock(stock_id):
    """Small debug helper to trace stock calculation steps.

    Replace or call this from real update functions where you need
    per-stock tracing.
    """
    logger.debug("Starting calculation for stock %s", stock_id)
    try:
        # placeholder for calculation logic
        logger.info("Successfully updated stock %s", stock_id)
    except Exception as e:
        logger.error("Failed to update stock %s: %s", stock_id, e)


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


from threading import Thread


# --- Brevo / sib-api-v3-sdk transactional email helper ---
try:
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
    from sib_api_v3_sdk.models.send_smtp_email import SendSmtpEmail
except Exception:
    sib_api_v3_sdk = None
    ApiException = Exception
    SendSmtpEmail = None


def _init_brevo_client():
    """Create and return a TransactionalEmailsApi instance or None.

    Uses the `BREVO_API_KEY` env var. Returns (api_instance, error_message)
    where api_instance is None on failure.
    """
    try:
        api_key = os.getenv('BREVO_API_KEY')
        if not api_key or not sib_api_v3_sdk:
            return None, 'BREVO_API_KEY not set or sib-api-v3-sdk not installed'

        configuration = sib_api_v3_sdk.Configuration()
        configuration.api_key['api-key'] = api_key
        api = sib_api_v3_sdk.TransactionalEmailsApi(sib_api_v3_sdk.ApiClient(configuration))
        return api, None
    except Exception as e:
        return None, str(e)


# Initialize at import time if possible (non-fatal if not configured)
_BREVO_API, _BREVO_ERR = _init_brevo_client()


def send_brevo_email(subject, html_content, to_emails, sender_email=None, sender_name='Urumuli Smart System'):
    """Send email via Brevo Transactional API synchronously.

    Returns True on success, False on failure.
    """
    try:
        # If the module-level client wasn't initialized at import time (for
        # example the process started before .env was loaded), try to initialize
        # it now. This avoids the "Brevo API not configured" race on first use.
        global _BREVO_API, _BREVO_ERR
        if not _BREVO_API:
            _BREVO_API, _BREVO_ERR = _init_brevo_client()
            if not _BREVO_API:
                try:
                    current_app.logger.warning("Brevo API not configured (late init): %s", _BREVO_ERR)
                except Exception:
                    logging.warning("Brevo API not configured (late init): %s", _BREVO_ERR)
                return False

        sender = {
            'name': sender_name,
            'email': sender_email or os.getenv('BREVO_SENDER_EMAIL') or 'no-reply@example.com'
        }

        send_smtp = SendSmtpEmail(
            to=[{"email": e} for e in to_emails],
            sender=sender,
            subject=subject,
            html_content=html_content,
        )

        resp = _BREVO_API.send_transac_email(send_smtp)
        try:
            current_app.logger.info("Brevo email sent: %s", getattr(resp, 'messageId', resp))
        except Exception:
            logging.info("Brevo email sent: %s", resp)
        return True
    except ApiException as e:
        try:
            current_app.logger.exception("Brevo ApiException sending email: %s", e)
        except Exception:
            logging.exception("Brevo ApiException sending email: %s", e)
        return False
    except Exception as e:
        try:
            current_app.logger.exception("Unexpected error sending Brevo email: %s", e)
        except Exception:
            logging.exception("Unexpected error sending Brevo email: %s", e)
        return False


def send_brevo_email_async(subject, html_content, to_emails, sender_email=None, sender_name='Urumuli Smart System'):
    """Non-blocking wrapper that sends Brevo emails in a daemon thread."""
    try:
        try:
            current_app.logger.info("ENQUEUE BREVO: to=%s subject=%s", to_emails, subject)
        except Exception:
            logging.info("ENQUEUE BREVO: to=%s subject=%s", to_emails, subject)
        t = Thread(target=send_brevo_email, args=(subject, html_content, to_emails, sender_email, sender_name), daemon=True)
        t.start()
    except Exception:
        try:
            current_app.logger.exception("Failed to spawn Brevo mail thread")
        except Exception:
            logging.exception("Failed to spawn Brevo mail thread")
