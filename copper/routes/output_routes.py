"""
Output Routes
Handles copper output/sales recording
"""
from datetime import datetime
from flask import render_template, request, redirect, url_for, flash

from config import db
from copper.models import CopperStock, CopperOutput
from copper import copper_bp
from core.auth import role_required
from utils import calculate_unit_percentage
from flask import request


@copper_bp.route("/outputs", methods=["GET", "POST"])
@role_required("accountant")
def record_output():
        """Record copper output"""
        from copper.forms import CopperOutputForm
        
        form = CopperOutputForm()
        # Populate stock choices for the dropdown
        form.stock_id.choices = [
            (s.id, f"{s.voucher_no} ({s.local_balance})  ({s.supplier})")
            for s in CopperStock.query.order_by(CopperStock.date.desc()).all() if s.local_balance > 0
        ]

        if request.method == "POST":
            stock_id = int(request.form.get("stock_id"))
            stock = CopperStock.query.get_or_404(stock_id)
            date = datetime.strptime(request.form.get("date"), "%Y-%m-%d").date() if request.form.get("date") else datetime.utcnow().date()
            output_kg = float(request.form.get("output_kg") or 0)
            customer = request.form.get("customer")
            output_amount = float(request.form.get('output_amount') or 0)
            amount_paid = float(request.form.get('amount_paid') or 0)
            note = request.form.get("note")

            stock1 = CopperStock.query.get(stock_id)
            available_balance = stock1.local_balance or 0

            if output_kg > available_balance:
                flash(f"❌ Error: You cannot output {output_kg} kg. Only {available_balance} kg available.", "danger")
                return redirect(url_for('copper.record_output'))

            # Create new output record
            out = CopperOutput(
                stock_id=stock.id,
                date=date,
                output_kg=output_kg,
                output_amount=output_amount,
                amount_paid=amount_paid,
                customer=customer,
                note=note
            )

            out.update_debt()
            db.session.add(out)

            db.session.commit()

            # --- IN-APP NOTIFICATION TO STOREKEEPER ---
            from core.models import create_notification, User
            storekeeper_user = User.query.filter_by(role='store_keeper').first()
            if storekeeper_user:
                create_notification(
                    user_id=storekeeper_user.id,
                    type_='OUTPUT_CREATED',
                    message=f"Stock output of {output_kg} kg for {stock.voucher_no} requires your processing.",
                    related_type='output',
                    related_id=out.id
                )

            # Persist notification before attempting email
            db.session.commit()

            # --- EMAIL NOTIFICATION TO STOREKEEPER ---
            from flask_mail import Message
            from flask import current_app
            from flask_login import current_user
            from app import mail
            from utils import send_email
            storekeeper_email = [storekeeper_user.email] if storekeeper_user and storekeeper_user.email else ["storekeeper@example.com"]
            output_details = f"Stock: {stock.voucher_no}, Supplier: {stock.supplier}, Output: {output_kg} kg, Customer: {customer}, Note: {note}"
            msg = Message(
                subject="Stock Output Request",
                sender=current_app.config['MAIL_USERNAME'],
                recipients=storekeeper_email
            )
            msg.body = f"""
Dear Storekeeper,\n\nAccountant {getattr(current_user, 'name', 'Unknown')} ({getattr(current_user, 'email', 'Unknown')}) yasabye gusohora izi stock zikurikira:\n\n{output_details}\n\nPlease process this request.\n\nRegards,\nSmart Account Manager System
            """
            try:
                send_email(mail, msg)
            except Exception:
                import logging
                logging.exception("Failed to enqueue copper output email")
                flash("Email notification failed; in-app notification saved.", "warning")
            


            flash(f"Output recorded ({output_kg} kg) for {stock.voucher_no}. Moyenne and Moyenne NB updated.", "success")
            return redirect(url_for("copper.record_output"))

        # Server-side filters (via GET): customer, from, to
        customer_filter = request.args.get('customer') or ''
        date_from = request.args.get('from') or ''
        date_to = request.args.get('to') or ''

        q = CopperOutput.query
        if customer_filter:
            q = q.filter(CopperOutput.customer == customer_filter)
        # parse dates (YYYY-MM-DD) defensively
        from datetime import datetime
        try:
            if date_from:
                d1 = datetime.strptime(date_from, '%Y-%m-%d').date()
                q = q.filter(CopperOutput.date >= d1)
            if date_to:
                d2 = datetime.strptime(date_to, '%Y-%m-%d').date()
                q = q.filter(CopperOutput.date <= d2)
        except Exception:
            # ignore parse errors and show unfiltered results
            pass

        outputs = q.order_by(CopperOutput.date.desc()).limit(60).all()
        return render_template("copper/outputs.html", outputs=outputs, form=form,
                               customer_filter=customer_filter, date_from=date_from, date_to=date_to)
