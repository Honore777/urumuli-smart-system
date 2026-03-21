"""
Copper forms module
Import all forms here for easier access
"""
from .stock_form import CopperStockForm
from .output_form import CopperOutputForm
from .debt_form import DebtTrackingForm
from .optimization_form import CopperOptimizationForm

from .payment_form import SupplierPaymentForm
from .worker_payment_form import WorkerPaymentForm

__all__ = [
    'CopperStockForm',
    'CopperOutputForm',
    'DebtTrackingForm',
    'CopperOptimizationForm',
    'SupplierPaymentForm',
    'WorkerPaymentForm'
]
