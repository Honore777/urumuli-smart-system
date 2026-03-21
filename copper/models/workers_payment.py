from datetime import datetime
from config import db

class WorkerPayment(db.Model):
    __tablename__ = 'worker_payment'

    id = db.Column(db.Integer, primary_key=True)
    worker_name = db.Column(db.String(100), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    paid_at = db.Column(db.DateTime, default=datetime.utcnow)
    method = db.Column(db.String(50))  # cash, bank, momo
    reference = db.Column(db.String(100))  # receipt/transaction id
    note = db.Column(db.Text)

    def __repr__(self):
        return f"<WorkerPayment {self.amount} RWF to {self.worker_name}>"
