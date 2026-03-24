"""
Cassiterite Stock Model
Represents each cassiterite stock entry from supplier.
Similar to copper but without moyenne_nb, with additional LME fields.
"""
from datetime import datetime
from config import db
from sqlalchemy import func, or_
from utils import calculate_unit_percentage, calculate_net_balance, trace_time, logger


class CassiteriteStock(db.Model):
    """
    Represents cassiterite stocks.
    Stores quantities, suppliers, and derived calculations.
    """
    __tablename__ = 'cassiterite_stock'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    voucher_no = db.Column(db.String(100), unique=True, nullable=False)
    supplier = db.Column(db.String(100), nullable=False)
    
    # Input & Basic Calculations
    input_kg = db.Column(db.Float)
    percentage = db.Column(db.Float)
    u = db.Column(db.Float)
    
    # Cassiterite-Specific Fields
    lme = db.Column(db.Float)  # London Metal Exchange reference price
    m_lme = db.Column(db.Float)  # LME markup/margin
    sec = db.Column(db.Float)  # Security fee
    tc = db.Column(db.Float)  # Transport cost
    
    # Pricing
    u_price = db.Column(db.Float)  # = LME + M_LME
    exchange = db.Column(db.Float)
    transport_tag = db.Column(db.Float)
    
    # Calculations
    amount = db.Column(db.Float)  # = input_kg × u_price
    amount_with_taxes = db.Column(db.Float)  # Total after deductions
    tot_amount_tag = db.Column(db.Float)  # = input_kg × transport_tag
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
    balance_to_pay = db.Column(db.Float)  # Net amount to pay supplier
    moyenne = db.Column(db.Float, default=0)  # Average purity (NO moyenne_nb)

    # Relationships
    outputs = db.relationship('CassiteriteOutput', 
                             back_populates='stock', 
                             foreign_keys='CassiteriteOutput.stock_id',
                             lazy=True, 
                             cascade="all, delete-orphan")
    
    supplier_payments = db.relationship('CassiteriteSupplierPayment',
                                       foreign_keys='CassiteriteSupplierPayment.stock_id',
                                       lazy=True,
                                       cascade="all, delete-orphan")

    def __repr__(self):
        return f"<CassiteriteStock {self.voucher_no} - {self.supplier}>"

    def remaining_stock(self):
        """Calculate remaining stock after outputs"""
        # DB-side aggregate to avoid loading all outputs into Python
        from .output import CassiteriteOutput
        outputs_total = db.session.query(func.coalesce(func.sum(CassiteriteOutput.output_kg), 0)).filter(CassiteriteOutput.stock_id == self.id).scalar() or 0
        return (self.input_kg or 0) - outputs_total

    def remaining_to_pay(self):
        """Calculate remaining amount to pay supplier"""
        # DB-side aggregate to avoid loading supplier payment rows into Python
        from .payment import CassiteriteSupplierPayment
        total_paid = db.session.query(func.coalesce(func.sum(CassiteriteSupplierPayment.amount), 0)).filter(CassiteriteSupplierPayment.stock_id == self.id).scalar() or 0
        return (self.balance_to_pay or 0) - total_paid

    @trace_time
    def update_calculations(self):
        """
        Recalculate all computed fields for this cassiterite stock.
        Called after stock entry or output changes.
        Formulas match CSV calculations exactly.
        """
        try:
            # Step 1: ensure defaults
            for field in ['input_kg', 'tot_amount_tag', 'rma', 'inkomane', 'percentage', 'lme', 'sec', 'tc', 'transport_tag', 'exchange']:
                setattr(self, field, getattr(self, field) or 0.0)

            # Step 2: calculate local_balance (remaining stock after outputs)
            self.local_balance = self.remaining_stock()

            # Step 3: calculate unit_percent using remaining local balance (consistent with copper)
            # Use percentage * local_balance so unit_percent decreases as stock is consumed
            self.unit_percent = calculate_unit_percentage(self.local_balance, self.percentage)

            # Step 4: t_unity should be the per-stock contribution for optimization
            # (not a cumulative rolling value). This matches copper's per-stock t_unity usage.
            self.t_unity = self.unit_percent

            # Step 5: calculate u_price = (lme - sec) × percentage / 100
            self.u_price = ((self.lme or 0) - (self.sec or 0)) * (self.percentage or 0) / 100

            # Step 6: calculate amount (total_amount_per_kg) = (u_price - tc) / 1000
            self.amount = ((self.u_price or 0) - (self.tc or 0)) / 1000

            # Step 7: calculate amount_with_taxes = amount × exchange × input_kg
            self.amount_with_taxes = (self.amount or 0) * (self.exchange or 0) * (self.input_kg or 0)

            # Step 8: calculate tot_amount_tag = transport_tag × input_kg
            self.tot_amount_tag = (self.transport_tag or 0) * (self.input_kg or 0)

            # Step 9: calculate rra_3_percent = ((((lme × percentage / 100) - 500) / 1000) × exchange × input_kg × 3) / 100
            rra_base = (((self.lme or 0) * (self.percentage or 0) / 100) - 500) / 1000
            self.rra_3_percent = (rra_base * (self.exchange or 0) * (self.input_kg or 0) * 3) / 100

            # Step 10: calculate balance_to_pay = amount_with_taxes - tot_amount_tag - rma - inkomane - rra_3_percent
            self.balance_to_pay = (self.amount_with_taxes or 0) - (self.tot_amount_tag or 0) - (self.rma or 0) - (self.inkomane or 0) - (self.rra_3_percent or 0)

            # Step 11: net_balance (same as balance_to_pay for cassiterite)
            self.net_balance = self.balance_to_pay

            # Step 12: rolling total balance = DB-side SUM of prior net_balance (only remaining stocks)
            prev_balance_q = db.session.query(func.coalesce(func.sum(CassiteriteStock.net_balance), 0)).filter(
                or_(
                    CassiteriteStock.date < self.date,
                    # include same-date rows that are "before" this one by id when id exists
                    (CassiteriteStock.date == self.date) & (CassiteriteStock.id < (self.id or 0))
                ),
                CassiteriteStock.local_balance > 0
            )
            previous_total_balance = prev_balance_q.scalar() or 0
            self.total_balance = previous_total_balance + (self.net_balance or 0)

            # Step 13: total local balance (DB-side SUM of prior local_balance)
            prev_local_q = db.session.query(func.coalesce(func.sum(CassiteriteStock.local_balance), 0)).filter(
                or_(
                    CassiteriteStock.date < self.date,
                    (CassiteriteStock.date == self.date) & (CassiteriteStock.id < (self.id or 0))
                ),
                CassiteriteStock.local_balance > 0
            )
            previous_total_local = prev_local_q.scalar() or 0
            self.total_local_balance = previous_total_local + (self.local_balance or 0)

            # Step 14: update global moyenne
            CassiteriteStock.update_global_moyennes()
        except Exception:
            try:
                logger.exception("update_calculations failed for CassiteriteStock id=%s", getattr(self, 'id', None))
            except Exception:
                pass
            raise

    @staticmethod
    def update_global_moyennes():
        """Recalculate MOYENNE across all remaining cassiterite stocks."""
        # Compute aggregates in the DB for remaining stocks to avoid loading
        total_unit_percent = db.session.query(func.coalesce(func.sum(CassiteriteStock.unit_percent), 0)).filter(CassiteriteStock.local_balance > 0).scalar()
        total_remaining_balance = db.session.query(func.coalesce(func.sum(CassiteriteStock.local_balance), 0)).filter(CassiteriteStock.local_balance > 0).scalar()
        if not total_remaining_balance:
            moyenne = 0
        else:
            moyenne = total_unit_percent / total_remaining_balance

        # Bulk-update all rows with the new moyenne (no commit here)
        db.session.query(CassiteriteStock).update({
            CassiteriteStock.moyenne: moyenne,
        }, synchronize_session=False)
