"""
Copper Stock Model
Represents each incoming copper stock record.
Stores quantities, suppliers, and derived calculations.
"""
from datetime import datetime
from config import db
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
        outputs_total = sum(o.output_kg for o in self.outputs or [])
        return (self.input_kg or 0) - outputs_total

    def remaining_to_pay(self):
        """Calculate remaining amount to pay supplier"""
        total_paid = sum(p.amount for p in self.supplier_payments or [])
        return (self.net_balance or 0) - total_paid

    def update_calculations(self, previous_stocks):
        """
        Recalculate all computed fields for this stock.
        Called after stock entry or output changes.
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

        # Step 6: rolling total balance
        previous_total_balance = sum((s.net_balance or 0) for s in previous_stocks)
        self.total_balance = previous_total_balance + self.net_balance

        # Step 7: total local balance
        previous_total_local = sum((s.local_balance or 0) for s in previous_stocks)
        self.total_local_balance = previous_total_local + self.local_balance

        # Step 8: update global moyenne and moyenne_nb
        CopperStock.update_global_moyennes()

    @staticmethod
    def update_global_moyennes():
        """Recalculate MOYENNE and MOYENNE_NB across all remaining copper stocks."""
        all_stocks = CopperStock.query.all()
        if not all_stocks:
            return

        remaining_stocks = [s for s in all_stocks if s.local_balance > 0]

        # Ensure no None values break calculations
        for s in remaining_stocks:
            s.unit_percent = s.unit_percent or 0.0
            s.t_unity = s.t_unity or 0.0

        total_unit_percent = sum(s.unit_percent for s in remaining_stocks)
        total_remaining_balance = sum(s.local_balance for s in remaining_stocks)
        moyenne = total_unit_percent / total_remaining_balance if total_remaining_balance else 0

        total_t_unity = sum(s.t_unity for s in remaining_stocks)
        moyenne_nb = total_t_unity / total_remaining_balance if total_remaining_balance else 0

        # Update all stocks
        for s in all_stocks:
            s.moyenne = moyenne
            s.moyenne_nb = moyenne_nb
        
        # NOTE: Do NOT commit here - let calling function handle commits
        # This allows multiple updates before a single final commit
