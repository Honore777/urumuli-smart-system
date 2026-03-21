"""Cassiterite Stock Routes.

This module handles:
- Creating cassiterite stock entries
- Rendering the cassiterite dashboard (with KPIs)
    including optional notifications for the logged-in user.
"""
from flask import render_template, request, redirect, url_for, flash, jsonify
from config import db
from cassiterite.models import CassiteriteStock
from cassiterite.forms import AddCassiteriteStockForm
from cassiterite.routes import cassiterite_bp
from core.auth import role_required
from core.models import Notification, create_notification, User
from flask_login import current_user

@role_required("accountant")
@cassiterite_bp.route('/add_stock', methods=['GET', 'POST'])
def add_stock():
    """Add new cassiterite stock"""
    form = AddCassiteriteStockForm()
    
    if form.validate_on_submit():
        # Check if voucher already exists
        existing = CassiteriteStock.query.filter_by(voucher_no=form.voucher_no.data).first()
        if existing:
            flash(f"Voucher {form.voucher_no.data} already exists!", "error")
            return redirect(url_for('cassiterite.add_stock'))
        
        # Create new stock
        stock = CassiteriteStock(
            date=form.date.data,
            voucher_no=form.voucher_no.data,
            supplier=form.supplier.data,
            input_kg=form.input_kg.data,
            percentage=form.percentage.data,
            lme=form.lme.data,
            m_lme=form.m_lme.data,
            sec=form.sec.data,
            tc=form.tc.data,
            exchange=form.exchange.data,
            transport_tag=form.transport_tag.data,
            rma=form.rma.data,
            inkomane=form.inkomane.data
        )
        
        # Get previous stocks for calculations
        previous_stocks = CassiteriteStock.query.order_by(CassiteriteStock.date).all()
        stock.update_calculations(previous_stocks)
        
        db.session.add(stock)
        db.session.commit()
        
        flash(f"Cassiterite stock {stock.voucher_no} added successfully!", "success")
        return redirect(url_for('cassiterite.dashboard'))
    
    return render_template('cassiterite/add_entry.html', form=form)


@role_required("accountant")
@cassiterite_bp.route('/stock/<int:stock_id>/delete', methods=['POST'])
def delete_stock(stock_id):
    """Delete a cassiterite stock and its related outputs/payments, then redirect to dashboard."""
    stock = CassiteriteStock.query.get_or_404(stock_id)
    voucher = stock.voucher_no
    db.session.delete(stock)
    db.session.commit()

    # Notify all bosses
    bosses = User.query.filter_by(role="boss", is_active=True).all()
    for boss in bosses:
        create_notification(
            user_id=boss.id,
            type_="stock_delete",
            message=f"Accountant {getattr(current_user, 'username', 'unknown')} deleted cassiterite stock {voucher}.",
            related_type="cassiterite_stock",
            related_id=stock_id
        )
    db.session.commit()

    flash(f"Cassiterite stock {voucher} deleted.", "success")
    return redirect(url_for('cassiterite.dashboard'))


@role_required("accountant")
@cassiterite_bp.route('/stock/<int:stock_id>/edit', methods=['POST'])
def edit_stock(stock_id):
    """Basic in-place edit for core cassiterite stock fields, then recalculate all derived values."""
    stock = CassiteriteStock.query.get_or_404(stock_id)

    from datetime import datetime as _dt2

    date_raw = request.form.get('date')
    try:
        date_val = _dt2.strptime(date_raw, '%Y-%m-%d').date() if date_raw else stock.date
    except Exception:
        date_val = stock.date

    voucher = request.form.get('voucher_no') or stock.voucher_no
    supplier = request.form.get('supplier') or stock.supplier
    input_kg = float(request.form.get('input_kg') or stock.input_kg or 0)
    percentage = float(request.form.get('percentage') or stock.percentage or 0)
    lme = float(request.form.get('lme') or stock.lme or 0)
    m_lme = float(request.form.get('m_lme') or stock.m_lme or 0)
    sec = float(request.form.get('sec') or stock.sec or 0)
    tc = float(request.form.get('tc') or stock.tc or 0)
    exchange = float(request.form.get('exchange') or stock.exchange or 0)
    transport_tag = float(request.form.get('transport_tag') or stock.transport_tag or 0)

    # Handle duplicate voucher if changed
    if voucher != stock.voucher_no:
        existing = CassiteriteStock.query.filter_by(voucher_no=voucher).first()
        if existing:
            flash(f"Lot/voucher number {voucher} already exists.", "error")
            return redirect(url_for('cassiterite.dashboard'))

    # Update base fields
    stock.date = date_val
    stock.voucher_no = voucher
    stock.supplier = supplier
    stock.input_kg = input_kg
    stock.percentage = percentage
    stock.lme = lme
    stock.m_lme = m_lme
    stock.sec = sec
    stock.tc = tc
    stock.exchange = exchange
    stock.transport_tag = transport_tag

    # Build previous stocks list for calculations (all stocks dated before this one)
    previous_stocks = (
        CassiteriteStock.query
        .filter(CassiteriteStock.id != stock.id, CassiteriteStock.date <= stock.date)
        .order_by(CassiteriteStock.date)
        .all()
    )

    stock.update_calculations(previous_stocks)
    db.session.commit()

    # Notify all bosses
    bosses = User.query.filter_by(role="boss", is_active=True).all()
    for boss in bosses:
        create_notification(
            user_id=boss.id,
            type_="stock_edit",
            message=f"Accountant {getattr(current_user, 'username', 'unknown')} edited cassiterite stock {voucher}.",
            related_type="cassiterite_stock",
            related_id=stock_id
        )
    db.session.commit()

    flash(f"Cassiterite stock {voucher} updated.", "success")
    return redirect(url_for('cassiterite.dashboard'))

@role_required("accountant")
@cassiterite_bp.route('/dashboard')
def dashboard():
    """Cassiterite dashboard"""
    from cassiterite.models import CassiteriteOutput
    
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 20
    stocks_pagination = CassiteriteStock.query.order_by(CassiteriteStock.date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    stocks = stocks_pagination.items
    outputs = CassiteriteOutput.query.order_by(CassiteriteOutput.date.desc()).all()

    total_input = sum(s.input_kg for s in CassiteriteStock.query.all())
    total_output = sum(o.output_kg for o in outputs)
    total_debt = sum(o.debt_remaining for o in outputs)
    total_sales = sum((o.output_amount or 0) for o in outputs)
    total_supplier_obligation = sum((s.balance_to_pay or 0) for s in CassiteriteStock.query.all())
    gross_profit = total_sales - total_supplier_obligation

    # Debts
    supplier_debt = sum((s.remaining_to_pay() or 0) for s in CassiteriteStock.query.all())
    customer_debt = total_debt

    # Cash position indicator for cassiterite
    cash_position = gross_profit - customer_debt + supplier_debt

    user_notifications = []
    if getattr(current_user, "is_authenticated", False):
        # Show all unread notifications and up to 10 already-read notifications
        unread = (
            Notification.query
            .filter_by(user_id=current_user.id, read_at=None)
            .order_by(Notification.created_at.desc())
            .all()
        )
        read = (
            Notification.query
            .filter(Notification.user_id == current_user.id, Notification.read_at != None)
            .order_by(Notification.created_at.desc())
            .limit(10)
            .all()
        )
        user_notifications = unread + read

    # Cassiterite moyenne is stored on each stock; compute global moyenne like copper
    remaining_stocks = [s for s in stocks if (s.local_balance or 0) > 0]
    remaining_stocks_count = CassiteriteStock.query.filter((CassiteriteStock.local_balance > 0) | (CassiteriteStock.local_balance == None)).count()
    if remaining_stocks:
        total_unit_percent = sum(s.unit_percent or 0 for s in remaining_stocks)
        total_remaining_balance = sum(s.local_balance or 0 for s in remaining_stocks)
        moyenne = total_unit_percent / total_remaining_balance if total_remaining_balance > 0 else 0
    else:
        moyenne = 0

    return render_template(
        'cassiterite/dashboard.html',
        stocks=stocks,
        remaining_stocks=remaining_stocks,
        outputs=outputs,
        total_input=total_input,
        total_output=total_output,
        total_debt=total_debt,
        total_sales=total_sales,
        total_supplier_obligation=total_supplier_obligation,
        gross_profit=gross_profit,
        supplier_debt=supplier_debt,
        customer_debt=customer_debt,
        cash_position=cash_position,
        notifications=user_notifications,
        unread_notifications_count=sum(1 for n in user_notifications if n.read_at is None),
        moyenne=moyenne,
        remaining_stocks_count=remaining_stocks_count,
        stocks_pagination=stocks_pagination,
        page=page,
        per_page=per_page,
    )

@role_required("accountant")
@cassiterite_bp.route('/api/filter_stocks', methods=['POST'])
def cassiterite_filter_stocks():
    """Filter cassiterite stocks by date range (and optional lot/voucher) and return JSON with metrics and outputs."""
    from cassiterite.models import CassiteriteOutput

    data = request.get_json() or {}
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    lot_no = data.get('lot_no') or None

    # Base queries
    stocks_query = CassiteriteStock.query.order_by(CassiteriteStock.date.desc())
    outputs_query = CassiteriteOutput.query.order_by(CassiteriteOutput.date.desc())

    from datetime import datetime as _dt

    if start_date:
        start = _dt.strptime(start_date, '%Y-%m-%d').date()
        stocks_query = stocks_query.filter(CassiteriteStock.date >= start)
        outputs_query = outputs_query.filter(CassiteriteOutput.date >= start)

    if end_date:
        end = _dt.strptime(end_date, '%Y-%m-%d').date()
        stocks_query = stocks_query.filter(CassiteriteStock.date <= end)
        outputs_query = outputs_query.filter(CassiteriteOutput.date <= end)

    if lot_no:
        stocks_query = stocks_query.filter(CassiteriteStock.voucher_no == lot_no)

    filtered_stocks = stocks_query.all()
    filtered_outputs = outputs_query.all()

    total_input = sum(s.input_kg or 0 for s in filtered_stocks)
    total_output = sum(o.output_kg or 0 for o in filtered_outputs)
    total_debt = sum(o.debt_remaining or 0 for o in filtered_outputs)
    total_stocks = len(filtered_stocks)

    remaining_stocks = [s for s in filtered_stocks if (s.local_balance or 0) > 0]
    if remaining_stocks:
        total_unit_percent = sum(s.unit_percent or 0 for s in remaining_stocks)
        total_remaining_balance = sum(s.local_balance or 0 for s in remaining_stocks)
        moyenne = total_unit_percent / total_remaining_balance if total_remaining_balance > 0 else 0
    else:
        moyenne = 0

    # Serialize stocks
    stocks_data = []
    for s in filtered_stocks:
        stocks_data.append({
            'id': s.id,
            'date': s.date.strftime('%Y-%m-%d'),
            'voucher_no': s.voucher_no,
            'supplier': s.supplier,
            'input_kg': round(s.input_kg or 0, 2),
            'percentage': round(s.percentage or 0, 2),
            'unit_percent': round(s.unit_percent or 0, 4),
            't_unity': round(s.t_unity or 0, 2),
            'moyenne': round(s.moyenne or 0, 4),
            'lme': round(s.lme or 0, 2),
            'm_lme': round(s.m_lme or 0, 2),
            'exchange': round(s.exchange or 0, 2),
            'sec': round(s.sec or 0, 2),
            'tc': round(s.tc or 0, 2),
            'u_price': round(s.u_price or 0, 2),
            'amount': round(s.amount or 0, 2),
            'amount_with_taxes': round(s.amount_with_taxes or 0, 2),
            'transport_tag': round(s.transport_tag or 0, 2),
            'tot_amount_tag': round(s.tot_amount_tag or 0, 2),
            'rma': round(s.rma or 0, 2),
            'inkomane': round(s.inkomane or 0, 2),
            'rra_3_percent': round(s.rra_3_percent or 0, 2),
            'local_balance': round(s.local_balance or 0, 2),
            'balance_to_pay': round(s.balance_to_pay or 0, 2),
            'total_balance': round(s.total_balance or 0, 2),
            'remaining': round(s.remaining_stock() or 0, 2),
        })

    # Serialize outputs for chart
    outputs_data = []
    for o in filtered_outputs:
        outputs_data.append({
            'date': o.date.strftime('%Y-%m-%d'),
            'output_kg': round(o.output_kg or 0, 2)
        })

    return jsonify({
        'stocks': stocks_data,
        'outputs': outputs_data,
        'total_input': round(total_input, 2),
        'total_output': round(total_output, 2),
        'total_debt': round(total_debt, 2),
        'total_stocks': total_stocks,
        'moyenne': round(moyenne, 4)
    })
