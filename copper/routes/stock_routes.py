"""
Stock Routes
Handles copper stock entry and export functionality
"""
from datetime import datetime
from io import BytesIO
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
import openpyxl
import pandas as pd

from config import db
from copper.models import CopperStock, CopperOutput
from copper import copper_bp
from core.models import Notification, create_notification, User
from flask_login import current_user


def _parse_date(s):
    """Helper to parse date strings"""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except:
        return None


@copper_bp.route("/stock/<int:stock_id>/delete", methods=["POST"])
def delete_stock(stock_id):
    """Delete a copper stock and its related outputs/payments, then redirect to dashboard."""
    stock = CopperStock.query.get_or_404(stock_id)
    voucher = stock.voucher_no
    db.session.delete(stock)
    db.session.commit()

    # Notify all bosses
    bosses = User.query.filter_by(role="boss", is_active=True).all()
    for boss in bosses:
        create_notification(
            user_id=boss.id,
            type_="stock_delete",
            message=f"Accountant {getattr(current_user, 'username', 'unknown')} deleted copper stock {voucher}.",
            related_type="copper_stock",
            related_id=stock_id
        )
    db.session.commit()

    flash(f"Copper stock {voucher} deleted.", "success")
    return redirect(url_for("copper.dashboard"))


@copper_bp.route("/stock/<int:stock_id>/edit", methods=["POST"])
def edit_stock(stock_id):
    """Basic in-place edit for core copper stock fields, recalculating dependent values."""
    stock = CopperStock.query.get_or_404(stock_id)

    # Parse incoming fields
    date = _parse_date(request.form.get("date")) or stock.date
    voucher = request.form.get("voucher_no") or stock.voucher_no
    supplier = request.form.get("supplier") or stock.supplier
    input_kg = float(request.form.get("input_kg") or stock.input_kg or 0)
    percentage = float(request.form.get("percentage") or stock.percentage or 0)
    nb = float(request.form.get("nb") or stock.nb or 0)
    u_price = float(request.form.get("u_price") or stock.u_price or 0)
    exchange = float(request.form.get("exchange") or stock.exchange or 0)
    transport_tag = float(request.form.get("transport_tag") or stock.transport_tag or 0)

    # Keep same per-kg RMA/Inkomane rates as before (if any)
    old_input = stock.input_kg or 0
    per_rma = (stock.rma or 0) / old_input if old_input else 125
    per_inkomane = (stock.inkomane or 0) / old_input if old_input else 40

    # Duplicate voucher check if changed
    if voucher != stock.voucher_no:
        existing = CopperStock.query.filter_by(voucher_no=voucher).first()
        if existing:
            flash(f"Voucher number {voucher} already exists.", "error")
            return redirect(url_for("copper.dashboard"))

    # Update base fields
    stock.date = date
    stock.voucher_no = voucher
    stock.supplier = supplier
    stock.input_kg = input_kg
    stock.percentage = percentage
    stock.nb = nb
    stock.u_price = u_price
    stock.exchange = exchange
    stock.transport_tag = transport_tag

    # Recompute derived values following add_stock logic
    stock.u = nb * input_kg
    stock.rma = per_rma * input_kg
    stock.inkomane = per_inkomane * input_kg
    stock.amount = percentage * input_kg * exchange * u_price
    stock.tot_amount_tag = transport_tag * input_kg
    stock.rra_3_percent = (1.95 * exchange * percentage * input_kg) * 3 / 100

    # Build previous stocks list (all stocks dated before this one)
    previous_stocks = (
        CopperStock.query
        .filter(CopperStock.id != stock.id, CopperStock.date <= stock.date)
        .order_by(CopperStock.date)
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
            message=f"Accountant {getattr(current_user, 'username', 'unknown')} edited copper stock {voucher}.",
            related_type="copper_stock",
            related_id=stock_id
        )
    db.session.commit()

    flash(f"Copper stock {voucher} updated.", "success")
    return redirect(url_for("copper.dashboard"))


@copper_bp.route("/add_stock", methods=["GET", "POST"])
def add_stock():
        """Add new copper stock entry"""
        from copper.forms import CopperStockForm
        
        form = CopperStockForm()
        if request.method == "POST":
            date = _parse_date(request.form.get("date")) or datetime.utcnow().date()
            voucher = request.form.get("voucher_no")
            supplier = request.form.get("supplier")
            input_kg = float(request.form.get("input_kg") or 0)
            percentage = float(request.form.get("percentage") or 0)
            nb = float(request.form.get("nb") or 0)
            rma_default = float(request.form.get("rma_default") or 150)
            inkomane_default = float(request.form.get("inkomane_default") or 40)
            u_price = float(request.form.get("u_price") or 0)
            exchange = float(request.form.get("exchange") or 0)
            transport_tag = float(request.form.get("transport_tag") or 0)

            # Fetch previous stocks first
            previous_stocks = CopperStock.query.order_by(CopperStock.date).all()

            # Calculate derived fields
            u = nb * input_kg
            rma = rma_default * input_kg
            inkomane = inkomane_default * input_kg
            amount = percentage * input_kg * exchange * u_price
            tot_amount_tag = transport_tag * input_kg
            rra_3_percent = (1.95 * exchange * percentage * input_kg) * 3 / 100
            net_balance = (amount or 0) - (tot_amount_tag or 0) - (rma or 0) - (inkomane or 0) - (rra_3_percent or 0)

            # Compute rolling total
            previous_total_balance = sum((s.net_balance or 0) for s in previous_stocks)
            total_balance = previous_total_balance + net_balance

            # Check for duplicate voucher
            existing = CopperStock.query.filter_by(voucher_no=voucher).first()
            if existing:
                return jsonify({"error": f"Voucher number {voucher} already exists."}), 400

            # Create stock object
            s = CopperStock(
                date=date,
                voucher_no=voucher,
                supplier=supplier,
                input_kg=input_kg,
                percentage=percentage,
                nb=nb,
                u=u,
                u_price=u_price,
                exchange=exchange,
                transport_tag=transport_tag,
                tot_amount_tag=tot_amount_tag,
                rma=rma,
                inkomane=inkomane,
                amount=amount,
                rra_3_percent=rra_3_percent,
                net_balance=net_balance,
                total_balance=total_balance
            )

            db.session.add(s)
            db.session.flush()

            # Recalculate average and balance fields
            s.update_calculations(previous_stocks)

            db.session.commit()
            flash("Copper stock added successfully!", "success")
            return redirect(url_for("copper.dashboard"))

        return render_template("copper/add_stock.html", form=form)


@copper_bp.route("/dashboard")
def dashboard():
    """Copper dashboard"""
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 20
    stocks_pagination = CopperStock.query.order_by(CopperStock.date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    stocks = stocks_pagination.items
    outputs = CopperOutput.query.order_by(CopperOutput.date.desc()).all()

    total_input = sum(s.input_kg for s in CopperStock.query.all())
    total_output = sum(o.output_kg for o in outputs)
    total_debt = sum(o.debt_remaining for o in outputs)
    total_sales = sum((o.output_amount or 0) for o in outputs)
    total_supplier_obligation = sum((s.net_balance or 0) for s in CopperStock.query.all())
    gross_profit = total_sales - total_supplier_obligation

    supplier_debt = sum((s.remaining_to_pay() or 0) for s in CopperStock.query.all())
    customer_debt = total_debt

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

    remaining_stocks = [s for s in stocks if (s.local_balance or 0) > 0]
    remaining_stocks_count = CopperStock.query.filter((CopperStock.local_balance > 0) | (CopperStock.local_balance == None)).count()

    if remaining_stocks:
        total_unit_percent = sum(s.unit_percent or 0 for s in remaining_stocks)
        total_remaining_balance = sum(s.local_balance or 0 for s in remaining_stocks)
        moyenne = total_unit_percent / total_remaining_balance if total_remaining_balance > 0 else 0
        total_t_unity = sum(s.t_unity or 0 for s in remaining_stocks)
        moyenne_nb = total_t_unity / total_remaining_balance if total_remaining_balance > 0 else 0
    else:
        moyenne = 0
        moyenne_nb = 0

    return render_template(
        'copper/dashboard.html',
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
        moyenne_nb=moyenne_nb,
        remaining_stocks_count=remaining_stocks_count,
        stocks_pagination=stocks_pagination,
        page=page,
        per_page=per_page,
    )


@copper_bp.route("/export_stocks")
def export_stocks():
        """Export all copper stocks to Excel"""
        stocks = CopperStock.query.order_by(CopperStock.date.desc()).all()
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Copper Stock"

        headers = [
            "Date", "Voucher", "Supplier", "Input (kg)", "Output (kg)", "Local Bal", "Total Local Bal",
            "%", "Moyenne", "NB", "Moyenne NB", "Net Balance", "Total Balance", "RMA", "Inkomane"
        ]
        ws.append(headers)
        for s in stocks:
            ws.append([
                s.date.strftime("%Y-%m-%d"),
                s.voucher_no,
                s.supplier,
                s.input_kg,
                s.local_balance,
                s.total_local_balance,
                s.percentage,
                s.moyenne,
                s.nb,
                s.moyenne_nb,
                s.net_balance,
                s.total_balance,
                s.rma,
                s.inkomane
            ])
        out = BytesIO()
        wb.save(out)
        out.seek(0)
        return send_file(out,
                         as_attachment=True,
                         download_name=f"copper_stock_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.xlsx",
                         mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@copper_bp.route("/export_filtered_stocks")
def export_filtered_stocks():
    """Export filtered copper stocks to Excel"""
    percentage_filter = request.args.get('percentage_filter')
    nb_filter = request.args.get('nb_filter')

    stock = CopperStock.query.order_by(CopperStock.date.desc()).first()
    moyenne = stock.moyenne if stock else 0
    moyenne_nb = stock.moyenne_nb if stock else 0

    all_stock = CopperStock.query.filter(CopperStock.local_balance > 0)

    if percentage_filter == 'above':
        all_stock = all_stock.filter(CopperStock.percentage >= moyenne)
    elif percentage_filter == 'below':
        all_stock = all_stock.filter(CopperStock.percentage <= moyenne)

    if nb_filter == 'above':
        all_stock = all_stock.filter(CopperStock.nb >= moyenne_nb)
    elif nb_filter == 'below':
        all_stock = all_stock.filter(CopperStock.nb <= moyenne_nb)

    filtered_stocks = all_stock.all()

    # Convert to Pandas DataFrame
    df = pd.DataFrame([{
        "Voucher": s.voucher_no,
        "Input_kg": s.input_kg,
        "U": s.u,
        "RMA": s.rma,
        "INKOMANE": s.inkomane,
        "Percentage": s.percentage,
        "Nb": s.nb,
        "Local_Balance": s.local_balance
    } for s in filtered_stocks])

    # Export to Excel in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Filtered Stocks')
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="filtered_copper_stocks.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )



@copper_bp.route('/api/filter_stocks', methods=['POST'])
def filter_stocks():
    """Filter stocks by date range (and optional voucher) and return JSON with all recalculated metrics"""
    from flask import request, jsonify
    from datetime import datetime
    
    data = request.get_json()
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    voucher_no = data.get('voucher_no') or None
    
    # Filter stocks
    stocks_query = CopperStock.query.order_by(CopperStock.date.desc())
    
    if start_date:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        stocks_query = stocks_query.filter(CopperStock.date >= start)
    
    if end_date:
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
        stocks_query = stocks_query.filter(CopperStock.date <= end)

    if voucher_no:
        stocks_query = stocks_query.filter(CopperStock.voucher_no == voucher_no)
    
    filtered_stocks = stocks_query.all()
    
    # Filter outputs by same date range (voucher filter does not apply here)
    outputs_query = CopperOutput.query.order_by(CopperOutput.date.desc())
    
    if start_date:
        start = datetime.strptime(start_date, '%Y-%m-%d').date()
        outputs_query = outputs_query.filter(CopperOutput.date >= start)
    
    if end_date:
        end = datetime.strptime(end_date, '%Y-%m-%d').date()
        outputs_query = outputs_query.filter(CopperOutput.date <= end)
    
    filtered_outputs = outputs_query.all()
    
    # Recalculate all metrics
    total_input = sum(s.input_kg for s in filtered_stocks)
    total_output = sum(o.output_kg for o in filtered_outputs)
    total_debt = sum(o.debt_remaining for o in filtered_outputs)
    total_stocks = len(filtered_stocks)
    
    # Recalculate moyenne and moyenne_nb from scratch using formulas
    remaining_stocks = [s for s in filtered_stocks if s.local_balance > 0]
    
    if remaining_stocks:
        # Average unit_percent / remaining_balance for remaining stocks
        total_unit_percent = sum(s.unit_percent or 0 for s in remaining_stocks)
        total_remaining_balance = sum(s.local_balance or 0 for s in remaining_stocks)
        moyenne = total_unit_percent / total_remaining_balance if total_remaining_balance > 0 else 0
        
        # Average t_unity / remaining_balance for remaining stocks
        total_t_unity = sum(s.t_unity or 0 for s in remaining_stocks)
        moyenne_nb = total_t_unity / total_remaining_balance if total_remaining_balance > 0 else 0
    else:
        moyenne = 0
        moyenne_nb = 0
    
    # Build stocks data for table
    stocks_data = []
    for stock in filtered_stocks:
        stocks_data.append({
            'id': stock.id,
            'date': stock.date.strftime('%Y-%m-%d'),
            'voucher_no': stock.voucher_no,
            'supplier': stock.supplier,
            'input_kg': round(stock.input_kg or 0, 2),
            'percentage': round(stock.percentage or 0, 2),
            'nb': round(stock.nb or 0, 2),
            'u_price': round(stock.u_price or 0, 2),
            'amount': round(stock.amount or 0, 2),
            'exchange': round(stock.exchange or 0, 2),
            'transport_tag': round(stock.transport_tag or 0, 2),
            'rma': round(stock.rma or 0, 2),
            'inkomane': round(stock.inkomane or 0, 2),
            'local_balance': round(stock.local_balance or 0, 2),
            'unit_percent': round(stock.unit_percent or 0, 4),
            't_unity': round(stock.t_unity or 0, 2),
            'net_balance': round(stock.net_balance or 0, 2),
            'total_balance': round(stock.total_balance or 0, 2),
            'remaining': round(stock.remaining_stock() or 0, 2),
            'moyenne': round(stock.moyenne or 0, 4),
            'moyenne_nb': round(stock.moyenne_nb or 0, 4)
        })

    # Build outputs data for charts (date vs output_kg)
    outputs_data = []
    for output in filtered_outputs:
        outputs_data.append({
            'date': output.date.strftime('%Y-%m-%d'),
            'output_kg': round(output.output_kg or 0, 2)
        })
    
    return jsonify({
        'stocks': stocks_data,
        'outputs': outputs_data,
        'total_input': round(total_input, 2),
        'total_output': round(total_output, 2),
        'total_debt': round(total_debt, 2),
        'total_stocks': total_stocks,
        'moyenne': round(moyenne, 4),
        'moyenne_nb': round(moyenne_nb, 4)
    })
