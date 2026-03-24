"""Cassiterite Debt Routes

Handles customer debt tracking and customer payments for cassiterite.

As with copper, when an accountant records a payment here we also
create a PaymentReview so the boss sees it on the consolidated
approval dashboard.
"""
from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import func
from config import db
from cassiterite.models import CassiteriteOutput
from cassiterite.forms import RecordCassiteritePaymentForm
from cassiterite.routes import cassiterite_bp
from core.auth import role_required
from core.models import PaymentReview, User, create_notification


def _populate_customer_choices(form: RecordCassiteritePaymentForm) -> None:
    """Populate dropdown with customers that still have cassiterite debt.

    Choices look like: "CustomerName - Remaining: 123,456.78 RWF".
    """
    customers_with_debt = (
        db.session.query(
            CassiteriteOutput.customer,
            func.sum(CassiteriteOutput.debt_remaining).label('total_debt'),
        )
        .filter(CassiteriteOutput.debt_remaining > 0)
        .group_by(CassiteriteOutput.customer)
        .all()
    )

    form.customer.choices = [
        (
            row.customer,
            f"{row.customer} - Remaining: {row.total_debt:,.2f} RWF",
        )
        for row in customers_with_debt
        if row.customer
    ]


@cassiterite_bp.route('/track_debts', methods=['GET', 'POST'])
@role_required("accountant")
def track_debts():
    """Track cassiterite customer debts"""
    form = RecordCassiteritePaymentForm()
    _populate_customer_choices(form)

    selected_customer = None

    # Base query: all outputs that still have remaining debt
    debts_query = CassiteriteOutput.query.filter(
        CassiteriteOutput.debt_remaining > 0
    )

    if request.method == 'POST' and form.validate_on_submit():
        selected_customer = form.customer.data
        debts_query = debts_query.filter(CassiteriteOutput.customer == selected_customer)

    filtered_debts = debts_query.order_by(CassiteriteOutput.date).all()
    
    return render_template(
        'cassiterite/debt_tracking.html',
        form=form,
        debts=filtered_debts,
        selected_customer=selected_customer
    )


@cassiterite_bp.route('/update_payment', methods=['POST'])
@role_required("accountant")
def update_payment():
    """Update customer payment for cassiterite"""
    form = RecordCassiteritePaymentForm()
    _populate_customer_choices(form)

    if form.validate_on_submit():
        customer_name = form.customer.data
        payment_amount = float(form.payment_amount.data)
        
        outputs_with_debt = (
            CassiteriteOutput.query.filter(CassiteriteOutput.customer == customer_name)
            .filter(CassiteriteOutput.debt_remaining > 0)
            .order_by(CassiteriteOutput.date)
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

        # Create a PaymentReview entry so the boss can approve this
        # cassiterite customer payment from the boss dashboard.
        review = PaymentReview(
            mineral_type="cassiterite",
            type="customer",
            customer=customer_name,
            amount=payment_amount,
            currency="RWF",
            payment_id=None,
            created_by_id=current_user.id,
        )
        db.session.add(review)

        # Notify all active bosses that a cassiterite payment is
        # waiting for review (ids only)
        boss_rows = db.session.query(User.id).filter_by(role="boss", is_active=True).all()
        message = (
            f"Hasabwe kwemeza: Kwishyura umukiriya kuri Gasegereti - {customer_name}, Amafaranga: {payment_amount} RWF."
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
    
    return redirect(url_for("cassiterite.track_debts"))


@cassiterite_bp.route('/customer_ledger/<customer>')
def customer_ledger(customer):
    """View customer transaction ledger - sums proportional amounts by date"""
    from collections import defaultdict
    
    outputs = CassiteriteOutput.query.filter_by(customer=customer).order_by(CassiteriteOutput.date).all()
    
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
        'cassiterite/customer_ledger.html',
        customer=customer,
        ledger=ledger,
        total_owed=db.session.query(func.coalesce(func.sum(CassiteriteOutput.output_amount), 0)).filter(CassiteriteOutput.customer == customer).scalar(),
        total_paid=db.session.query(func.coalesce(func.sum(CassiteriteOutput.amount_paid), 0)).filter(CassiteriteOutput.customer == customer).scalar(),
        remaining=(db.session.query(func.coalesce(func.sum(CassiteriteOutput.output_amount), 0)).filter(CassiteriteOutput.customer == customer).scalar() - db.session.query(func.coalesce(func.sum(CassiteriteOutput.amount_paid), 0)).filter(CassiteriteOutput.customer == customer).scalar()),
        user_role=getattr(current_user, 'role', None)
    )
