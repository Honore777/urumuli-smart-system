"""
Copper Stock Model
Represents each incoming copper stock record.
Stores quantities, suppliers, and derived calculations.
"""
from datetime import datetime
from config import db
from sqlalchemy import func
from utils import calculate_unit_percentage, calculate_net_balance, calculate_moyenne


class CopperStock(db.Model):
    """
    Represents each incoming copper stock record.
    Stores quantities, suppliers, and derived calculations.
    """
    __tablename__ = 'copper_stock'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    voucher_no = db.Column(db.String(100), unique=True, nullable=False)
    supplier = db.Column(db.String(100), nullable=False)
    
    # Input & Basic Calculations
    input_kg = db.Column(db.Float)
    percentage = db.Column(db.Float)
    nb = db.Column(db.Float)
    u = db.Column(db.Float)
    
    # Pricing
    u_price = db.Column(db.Float)
    exchange = db.Column(db.Float)
    transport_tag = db.Column(db.Float)
    
    # Calculations
    amount = db.Column(db.Float)
    tot_amount_tag = db.Column(db.Float)
    rma = db.Column(db.Float)
    inkomane = db.Column(db.Float)
    rra_3_percent = db.Column(db.Float)
    
    # Balances & Averages
    local_balance = db.Column(db.Float, default=0)
    total_local_balance = db.Column(db.Float)
    unit_percent = db.Column(db.Float)
    t_unity = db.Column(db.Float)
    net_balance = db.Column(db.Float)
    total_balance = db.Column(db.Float)
    moyenne = db.Column(db.Float, default=0)
    moyenne_nb = db.Column(db.Float, default=0)

    # Relationships
    outputs = db.relationship('CopperOutput', 
                             back_populates='stock', 
                             foreign_keys='CopperOutput.stock_id',
                             lazy=True, 
                             cascade="all, delete-orphan")
    supplier_payments = db.relationship(
        'SupplierPayment',
        backref='stock',
        lazy=True,
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<CopperStock {self.voucher_no} - {self.supplier}>"

    def remaining_stock(self):
        """Calculate remaining stock after outputs"""
        # Use a DB-side aggregate to avoid loading all output rows into Python
        from .output import CopperOutput
        outputs_total = db.session.query(func.coalesce(func.sum(CopperOutput.output_kg), 0)).filter(CopperOutput.stock_id == self.id).scalar() or 0
        return (self.input_kg or 0) - outputs_total

    def remaining_to_pay(self):
        """Calculate remaining amount to pay supplier"""
        # Use a DB-side aggregate to avoid loading payment rows into Python
        from .payment import SupplierPayment
        total_paid = db.session.query(func.coalesce(func.sum(SupplierPayment.amount), 0)).filter(SupplierPayment.stock_id == self.id).scalar() or 0
        return (self.net_balance or 0) - total_paid

    def update_calculations(self):
        """
        Recalculate all computed fields for this stock using DB-side aggregates
        where possible. This avoids loading all previous rows into Python and
        ensures we only consider stocks with `local_balance > 0` when computing
        cumulative and moyenne figures.
        """
        # Step 1: ensure defaults
        for field in ['input_kg', 'amount', 'tot_amount_tag', 'rma', 'inkomane', 'nb', 'percentage']:
            setattr(self, field, getattr(self, field) or 0.0)

        # Step 2: calculate local balance
        self.local_balance = self.remaining_stock()

        # Step 3: calculate unit %
        self.unit_percent = calculate_unit_percentage(self.local_balance, self.percentage)

        # Step 4: t_unity formula
        self.t_unity = (self.nb or 0) * (self.local_balance or 0)

        # Step 5: net balance
        self.net_balance = calculate_net_balance(self)

        # Step 6: rolling total balance (DB-side aggregate over prior stocks)
        prev_total_q = db.session.query(func.coalesce(func.sum(CopperStock.net_balance), 0)).filter(
            CopperStock.date <= self.date,
            CopperStock.id != self.id,
            CopperStock.local_balance > 0
        )
        previous_total_balance = prev_total_q.scalar() or 0
        self.total_balance = previous_total_balance + (self.net_balance or 0)

        # Step 7: total local balance (DB-side)
        prev_local_q = db.session.query(func.coalesce(func.sum(CopperStock.local_balance), 0)).filter(
            CopperStock.date <= self.date,
            CopperStock.id != self.id,
            CopperStock.local_balance > 0
        )
        previous_total_local = prev_local_q.scalar() or 0
        self.total_local_balance = previous_total_local + (self.local_balance or 0)

        # Step 8: update global moyenne and moyenne_nb
        CopperStock.update_global_moyennes()

    @staticmethod
    def update_global_moyennes():
        """Recalculate MOYENNE and MOYENNE_NB across all remaining copper stocks."""
        # Compute aggregates in the DB for remaining stocks to avoid loading
        total_unit_percent = db.session.query(func.coalesce(func.sum(CopperStock.unit_percent), 0)).filter(CopperStock.local_balance > 0).scalar()
        total_remaining_balance = db.session.query(func.coalesce(func.sum(CopperStock.local_balance), 0)).filter(CopperStock.local_balance > 0).scalar()
        if not total_remaining_balance:
            moyenne = 0
            moyenne_nb = 0
        else:
            moyenne = total_unit_percent / total_remaining_balance
            total_t_unity = db.session.query(func.coalesce(func.sum(CopperStock.t_unity), 0)).filter(CopperStock.local_balance > 0).scalar()
            moyenne_nb = total_t_unity / total_remaining_balance

        # Bulk-update all rows with the new moyennes (no commit here)
        db.session.query(CopperStock).update({
            CopperStock.moyenne: moyenne,
            CopperStock.moyenne_nb: moyenne_nb,
        }, synchronize_session=False)
