"""Debt Routes
Handles customer debt tracking and customer payments for copper.

IMPORTANT:
- These routes are accountant-only (see role_required decorator).
- When an accountant records a customer payment we also create a
    PaymentReview row so the boss can later approve/reject it from
    the boss dashboard.
"""
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user

from config import db
from copper.models import CopperOutput
from copper import copper_bp
from core.auth import role_required
from core.models import PaymentReview, User, create_notification
from sqlalchemy import func


@copper_bp.route('/track_debts', methods=['GET', 'POST'])
@role_required("accountant")
def track_debts():
        """Track copper customer debts"""
        from copper.forms import DebtTrackingForm
        
        form = DebtTrackingForm()

        customers_with_debt = (
            CopperOutput.query.filter(CopperOutput.debt_remaining > 0).all()
        )

        selected_customer = None
        filtered_debts = []

        if request.method == 'POST' and form.validate_on_submit():
            selected_customer = form.customer.data
            payment_amount = form.payment_amount.data

            filtered_debts = (
                CopperOutput.query.filter(CopperOutput.customer == selected_customer)
                .filter(CopperOutput.debt_remaining > 0).all()
            )

        else:
            filtered_debts = customers_with_debt

        return render_template(
            'copper/debt_tracking.html',
            form=form,
            debts=filtered_debts,
            selected_customer=selected_customer
        )


@copper_bp.route('/update_payment', methods=['POST'])
@role_required("accountant")
def update_payment():
        """Update customer payment for copper"""
        from copper.forms import DebtTrackingForm
        
        form = DebtTrackingForm()

        if form.validate_on_submit():
            customer_name = form.customer.data
            payment_amount = float(form.payment_amount.data)

            outputs_with_debt = (
                CopperOutput.query.filter(CopperOutput.customer == customer_name)
                .filter(CopperOutput.debt_remaining > 0)
                .order_by(CopperOutput.date)
                .all()
            )

            remaining_payment = payment_amount

            for output in outputs_with_debt:
                if remaining_payment <= 0:
                    break

                debt = output.debt_remaining or 0

                if remaining_payment >= debt:
                    output.amount_paid += debt
                    output.debt_remaining = 0
                    remaining_payment -= debt
                else:
                    # Partial payment
                    output.amount_paid += remaining_payment
                    output.debt_remaining -= remaining_payment
                    remaining_payment = 0

                db.session.add(output)

            # At this point, all affected CopperOutput rows have updated
            # amount_paid / debt_remaining values. We now create a
            # PaymentReview so the boss can see and approve this payment.

            review = PaymentReview(
                mineral_type="coltan",           # identifies the module (display as coltan)
                type="customer",
                customer=customer_name,
                amount=payment_amount,            # total payment just applied
                currency="RWF",                  # your working currency
                payment_id=None,                  # optional, no separate payment table yet
                created_by_id=current_user.id     # the accountant who did this
            )
            db.session.add(review)

            # Optionally notify all active bosses that a new payment
            # is waiting for review on their dashboard (fetch ids only)
            boss_rows = db.session.query(User.id).filter_by(role="boss", is_active=True).all()
            message = (
                f"Hasabwe kwemeza: Kwishyura umukiriya kuri Coltan - {customer_name}, Amafaranga: {payment_amount} RWF."
            )
            for (boss_id,) in boss_rows:
                create_notification(
                    user_id=boss_id,
                    type_="PAYMENT_REVIEW_CREATED",
                    message=message,
                    related_type="payment_review",
                    related_id=review.id,
                )

            db.session.commit()
            flash(f"Payment of {payment_amount} applied to {customer_name} and sent for boss review.", "success")

        else:
            flash("Invalid form submission. Please check the inputs.", "error")

        return redirect(url_for("copper.track_debts"))


@copper_bp.route('/customer_ledger/<customer>')
def customer_ledger(customer):
    """View customer transaction ledger - sums proportional amounts by date"""
    from collections import defaultdict
    
    outputs = CopperOutput.query.filter_by(customer=customer).order_by(CopperOutput.date).all()
    
    # Group by date and sum proportional amounts
    by_date = defaultdict(lambda: {'output_amount': 0, 'amount_paid': 0, 'output_kg': 0})
    
    for output in outputs:
        date_key = output.date
        by_date[date_key]['output_amount'] += (output.output_amount or 0)
        by_date[date_key]['amount_paid'] += (output.amount_paid or 0)
        by_date[date_key]['output_kg'] += (output.output_kg or 0)
    
    ledger = []
    running_balance = 0
    
    # Process each date
    for date in sorted(by_date.keys()):
        data = by_date[date]
        
        # Total output for this date
        running_balance += data['output_amount']
        ledger.append({
            'date': date,
            'description': f"Total Output ({data['output_kg']} kg)",
            'debit': data['output_amount'],
            'credit': 0,
            'balance': running_balance,
            'output_kg': data['output_kg'],
            'batch_id': None
        })
        
        # Total payment for this date (if any)
        if data['amount_paid'] > 0:
            running_balance -= data['amount_paid']
            ledger.append({
                'date': date,
                'description': f"Payment",
                'debit': 0,
                'credit': data['amount_paid'],
                'balance': running_balance,
                'output_kg': 0,
                'batch_id': None
            })
    
    return render_template(
        'copper/customer_ledger.html',
        customer=customer,
        ledger=ledger,
        total_owed=db.session.query(func.coalesce(func.sum(CopperOutput.output_amount), 0)).filter(CopperOutput.customer == customer).scalar(),
        total_paid=db.session.query(func.coalesce(func.sum(CopperOutput.amount_paid), 0)).filter(CopperOutput.customer == customer).scalar(),
        remaining=(db.session.query(func.coalesce(func.sum(CopperOutput.output_amount), 0)).filter(CopperOutput.customer == customer).scalar() - db.session.query(func.coalesce(func.sum(CopperOutput.amount_paid), 0)).filter(CopperOutput.customer == customer).scalar()),
        user_role=getattr(current_user, 'role', None)
    )
