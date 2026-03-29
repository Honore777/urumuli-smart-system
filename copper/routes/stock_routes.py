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
from sqlalchemy.orm import joinedload, selectinload
from flask_login import current_user
from sqlalchemy import func
import logging
from utils import trace_time

logger = logging.getLogger(__name__)


def _parse_date(s):
    """Helper to parse date strings"""
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except:
        return None


@copper_bp.route("/stock/<int:stock_id>/delete", methods=["POST"])
@trace_time
def delete_stock(stock_id):
    """Delete a copper stock and its related outputs/payments, then redirect to dashboard."""
    try:
        logger.info("delete_stock: start id=%s user=%s", stock_id, getattr(current_user, "username", None))
        stock = CopperStock.query.get_or_404(stock_id)
        voucher = stock.voucher_no
        try:
            db.session.delete(stock)

            # Notify all bosses (fetch ids only to avoid hydrating full User objects)
            boss_rows = db.session.query(User.id).filter_by(role="boss", is_active=True).all()
            for (boss_id,) in boss_rows:
                create_notification(
                    user_id=boss_id,
                    type_="stock_delete",
                    message=f"Accountant {getattr(current_user, 'username', 'unknown')} deleted copper stock {voucher}.",
                    related_type="copper_stock",
                    related_id=stock_id
                )

            db.session.commit()
            logger.info("delete_stock: completed id=%s voucher=%s", stock_id, voucher)
            flash(f"Copper stock {voucher} deleted.", "success")
            return redirect(url_for("copper.dashboard"))
        except Exception:
            logger.exception("delete_stock failed id=%s; rolling back", stock_id)
            try:
                db.session.rollback()
            except Exception:
                pass
            raise
    except Exception:
        logger.exception("delete_stock failed id=%s", stock_id)
        raise


@copper_bp.route("/stock/<int:stock_id>/edit", methods=["POST"])
@trace_time
def edit_stock(stock_id):
    """Basic in-place edit for core copper stock fields, recalculating dependent values."""
    try:
        logger.info("edit_stock: start id=%s user=%s", stock_id, getattr(current_user, "username", None))
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
                logger.warning("edit_stock: duplicate voucher %s attempted by %s", voucher, getattr(current_user, "username", None))
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
        stock.rra_3_percent = (rra_3_percent_default * exchange * percentage * input_kg) * 3 / 100

        try:
            stock.update_calculations()

            # Notify all bosses (fetch ids only to avoid hydrating full User objects)
            boss_rows = db.session.query(User.id).filter_by(role="boss", is_active=True).all()
            for (boss_id,) in boss_rows:
                create_notification(
                    user_id=boss_id,
                    type_="stock_edit",
                    message=f"Accountant {getattr(current_user, 'username', 'unknown')} edited copper stock {voucher}.",
                    related_type="copper_stock",
                    related_id=stock_id
                )

            db.session.commit()
            logger.info("edit_stock: completed id=%s voucher=%s", stock_id, voucher)
            flash(f"Copper stock {voucher} updated.", "success")
            return redirect(url_for("copper.dashboard"))
        except Exception:
            logger.exception("edit_stock failed id=%s; rolling back", stock_id)
            try:
                db.session.rollback()
            except Exception:
                pass
            raise
    except Exception:
        logger.exception("edit_stock failed id=%s", stock_id)
        raise


@copper_bp.route("/add_stock", methods=["GET", "POST"])
@trace_time
def add_stock():
    """Add new copper stock entry"""
    from copper.forms import CopperStockForm

    form = CopperStockForm()
    if request.method == "POST":
        try:
            logger.info("add_stock: start user=%s", getattr(current_user, 'username', None))

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
            rra_3_percent_default = float(request.form.get("rra_3_percent_default") or 50)

            # Calculate derived fields
            u = nb * input_kg
            rma = rma_default * input_kg
            inkomane = inkomane_default * input_kg
            amount = percentage * input_kg * exchange * u_price
            tot_amount_tag = transport_tag * input_kg
            rra_3_percent = (rra_3_percent_default * exchange * percentage * input_kg) * 3 / 100
            net_balance = (amount or 0) - (tot_amount_tag or 0) - (rma or 0) - (inkomane or 0) - (rra_3_percent or 0)

            # Compute rolling total using a SQL aggregate (faster than pulling all rows into Python)
            previous_total_balance = db.session.query(
                func.coalesce(func.sum(CopperStock.net_balance), 0)
            ).filter(CopperStock.date <= date).scalar()
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

            try:
                db.session.add(s)
                db.session.flush()

                s.update_calculations()

                db.session.commit()
                logger.info("add_stock: completed voucher=%s", voucher)
                flash("Copper stock added successfully!", "success")
                return redirect(url_for("copper.dashboard"))
            except Exception:
                logger.exception("add_stock failed voucher=%s; rolling back", voucher)
                try:
                    db.session.rollback()
                except Exception:
                    pass
                raise
        except Exception:
            logger.exception("add_stock outer failure")
            raise

    return render_template("copper/add_stock.html", form=form)


@copper_bp.route("/dashboard")
def dashboard():
    """Copper dashboard"""
    # Pagination parameters
    page = request.args.get('page', 1, type=int)
    per_page = 20
    stocks_pagination = CopperStock.query.options(selectinload(CopperStock.supplier_payments)).order_by(CopperStock.date.desc()).paginate(page=page, per_page=per_page, error_out=False)
    stocks = stocks_pagination.items
    outputs = CopperOutput.query.order_by(CopperOutput.date.desc()).limit(10).all()

    total_input = db.session.query(func.coalesce(func.sum(CopperStock.input_kg), 0)).scalar()
    total_output = db.session.query(func.coalesce(func.sum(CopperOutput.output_kg), 0)).scalar()
    total_debt = db.session.query(func.coalesce(func.sum(CopperOutput.debt_remaining), 0)).scalar()
    total_sales = db.session.query(func.coalesce(func.sum(CopperOutput.output_amount), 0)).scalar()
    total_supplier_obligation = db.session.query(func.coalesce(func.sum(CopperStock.net_balance), 0)).scalar()
    gross_profit = total_sales - total_supplier_obligation

    supplier_debt = total_supplier_obligation
    customer_debt = total_debt

    cash_position = gross_profit - customer_debt + supplier_debt

    user_notifications = []
    if getattr(current_user, "is_authenticated", False):
        # Show all unread notifications and up to 10 already-read notifications
        unread = (
            Notification.query.options(joinedload(Notification.user))
            .filter_by(user_id=current_user.id, read_at=None)
            .order_by(Notification.created_at.desc())
            .all()
        )
        read = (
            Notification.query.options(joinedload(Notification.user))
            .filter(Notification.user_id == current_user.id, Notification.read_at != None)
            .order_by(Notification.created_at.desc())
            .limit(10)
            .all()
        )
        user_notifications = unread + read

    # Remaining stocks and aggregates (compute regardless of authentication)
    remaining_stocks = CopperStock.query.filter(CopperStock.local_balance > 0).order_by(CopperStock.date.desc()).all()
    remaining_stocks_count = CopperStock.query.filter(CopperStock.local_balance > 0).count()
    total_unit_percent = db.session.query(func.coalesce(func.sum(CopperStock.unit_percent), 0)).filter(CopperStock.local_balance > 0).scalar() or 0
    total_remaining_balance = db.session.query(func.coalesce(func.sum(CopperStock.local_balance), 0)).filter(CopperStock.local_balance > 0).scalar() or 0
    moyenne = (total_unit_percent / total_remaining_balance) if total_remaining_balance else 0
    total_t_unity = db.session.query(func.coalesce(func.sum(CopperStock.t_unity), 0)).filter(CopperStock.local_balance > 0).scalar() or 0
    moyenne_nb = (total_t_unity / total_remaining_balance) if total_remaining_balance else 0

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
        unread_notifications_count=Notification.query.filter_by(user_id=current_user.id, read_at=None).count(),
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
@trace_time
def filter_stocks():
    """Filter stocks by date range (and optional voucher) and return JSON with all recalculated metrics"""
    from flask import request, jsonify
    from datetime import datetime
    try:
        data = request.get_json()
        logger.info("filter_stocks: start user=%s data=%s", getattr(current_user, 'username', None), data)
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
        
        # Cap returned rows to avoid very large payloads when filtering
        filtered_stocks = stocks_query.limit(1000).all()
    
    # Filter outputs by same date range (voucher filter does not apply here)
        outputs_query = CopperOutput.query.order_by(CopperOutput.date.desc())
        
        if start_date:
            start = datetime.strptime(start_date, '%Y-%m-%d').date()
            outputs_query = outputs_query.filter(CopperOutput.date >= start)
        
        if end_date:
            end = datetime.strptime(end_date, '%Y-%m-%d').date()
            outputs_query = outputs_query.filter(CopperOutput.date <= end)
        
        filtered_outputs = outputs_query.limit(1000).all()
    
    # Aggregates from DB (avoid loading large lists into Python)
        stock_filters = []
        if start_date:
            stock_filters.append(CopperStock.date >= start)
        if end_date:
            stock_filters.append(CopperStock.date <= end)
        if voucher_no:
            stock_filters.append(CopperStock.voucher_no == voucher_no)

        total_input = db.session.query(func.coalesce(func.sum(CopperStock.input_kg), 0)).filter(*stock_filters).scalar() or 0
        total_stocks = db.session.query(func.coalesce(func.count(CopperStock.id), 0)).filter(*stock_filters).scalar() or 0

        output_filters = []
        if start_date:
            output_filters.append(CopperOutput.date >= start)
        if end_date:
            output_filters.append(CopperOutput.date <= end)

        total_output = db.session.query(func.coalesce(func.sum(CopperOutput.output_kg), 0)).filter(*output_filters).scalar() or 0
        total_debt = db.session.query(func.coalesce(func.sum(CopperOutput.debt_remaining), 0)).filter(*output_filters).scalar() or 0

        # Remaining stocks aggregates (only local_balance > 0)
        remaining_filters = list(stock_filters) + [CopperStock.local_balance > 0]
        total_unit_percent = db.session.query(func.coalesce(func.sum(CopperStock.unit_percent), 0)).filter(*remaining_filters).scalar() or 0
        total_remaining_balance = db.session.query(func.coalesce(func.sum(CopperStock.local_balance), 0)).filter(*remaining_filters).scalar() or 0
        moyenne = (total_unit_percent / total_remaining_balance) if total_remaining_balance else 0
        total_t_unity = db.session.query(func.coalesce(func.sum(CopperStock.t_unity), 0)).filter(*remaining_filters).scalar() or 0
        moyenne_nb = (total_t_unity / total_remaining_balance) if total_remaining_balance else 0
        
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

        logger.info("filter_stocks: completed stocks=%d outputs=%d", len(filtered_stocks), len(filtered_outputs))
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
    except Exception:
        logger.exception("filter_stocks failed")
        return jsonify({'error': 'internal server error'}), 500
