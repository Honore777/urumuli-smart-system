
from flask import render_template, redirect, abort, request
from flask_login import current_user

from cassiterite.models.workers_payment import CassiteriteWorkerPayment
from cassiterite.forms import CassiteriteWorkerPaymentForm
from cassiterite.models.payment import CassiteriteSupplierPayment
from cassiterite.routes import cassiterite_bp
from core.auth import role_required
from flask import url_for, flash
from config import db

@cassiterite_bp.route("/pay_worker", methods=["GET", "POST"])
@role_required("accountant")
def pay_worker():
	"""Record internal worker payments/expenses for cassiterite."""
	form = CassiteriteWorkerPaymentForm()

	if form.validate_on_submit():
		try:

			payment = CassiteriteWorkerPayment(
				worker_name=form.worker_name.data,
				amount=form.amount.data,
				method=form.method.data,
				reference=form.reference.data,
				note=form.note.data
			)
			db.session.add(payment)
			db.session.commit()

			# --- Create PaymentReview for worker payment (no mineral_type) ---
			from flask_login import current_user
			from core.models import PaymentReview
			review = PaymentReview(
				type='Umukozi',
				customer=form.worker_name.data,
				amount=form.amount.data,
				currency='RWF',
				payment_id=payment.id,
				created_by_id=getattr(current_user, 'id', None)
			)
			db.session.add(review)
			db.session.commit()

			# --- IN-APP NOTIFICATION TO BOSS ---
			from core.models import create_notification, User
			boss_user = User.query.filter_by(role='boss').first()
			if boss_user:
				create_notification(
					user_id=boss_user.id,
					type_='kwishyura umukozi',
					message=f"Hasabwe kwemeza: Kwishyura umukozi  - {form.worker_name.data}, Amafaranga: {form.amount.data} RWF.",
					related_type='kwishyura umukozi',
					related_id=payment.id
				)

			# Persist in-app notification before attempting email
			db.session.commit()

			# --- EMAIL NOTIFICATION TO BOSS ---
			from flask_mail import Message
			from flask import current_app
			from app import mail
			boss_email = [boss_user.email] if boss_user and boss_user.email else ["boss@example.com"]
			payment_details = (
				f"Umukozi: {form.worker_name.data}, Amafaranga: {form.amount.data} RWF, Uburyo: {form.method.data}, "
				f"Reference: {form.reference.data}, Impamvu: {form.note.data}"
			)
			msg = Message(
				subject="Gusaba Kwemeza Igikorwa: Kwishyura Umukozi",
				sender=current_app.config['MAIL_USERNAME'],
				recipients=boss_email
			)
			msg.body = f"""
Nyakubahwa Muyobozi,

Umucungamutungo {getattr(current_user, 'username', 'Unknown')} ({getattr(current_user, 'email', 'Unknown')}) yasabye kwemeza ubwishyu bukurikira :

{payment_details}

 Musuzume kandi mwemeze.

Mujye Muri Sisiteme kwemeza iki gikorwa.

Murakoze,
Urumuli Smart System
			"""
			try:
				mail.send(msg)
			except Exception as e:
				import logging
				logging.exception("Failed to send worker payment email notification")
				flash("Email notification failed; in-app notification saved.", "warning")

			flash(f"Payment of {form.amount.data} RWF recorded for {form.worker_name.data}.", "success")
			return redirect(url_for('cassiterite.pay_worker'))
		except Exception as e:
			db.session.rollback()
			flash(f"Error saving payment: {e}", "danger")

	# Optionally, show recent worker payments
	recent_payments = CassiteriteWorkerPayment.query.order_by(CassiteriteWorkerPayment.paid_at.desc()).limit(10).all()
	return render_template('cassiterite/pay_worker.html', form=form, recent_payments=recent_payments)
"""Cassiterite supplier-related routes.

Provides endpoints to record supplier payments and view supplier ledgers
for cassiterite stocks. Mirrors the copper supplier payment workflow.
"""

from flask import render_template, redirect, url_for, flash

from config import db
from . import cassiterite_bp
from cassiterite.models import CassiteriteStock, CassiteriteSupplierPayment
from core.auth import role_required


@cassiterite_bp.route("/pay_supplier", methods=["GET", "POST"])
@role_required("accountant")
def pay_supplier():
	"""Record supplier payments for cassiterite stocks."""
	from cassiterite.forms import CassiteriteSupplierPaymentForm

	form = CassiteriteSupplierPaymentForm()

	# Populate stock choices with stocks that still have balance to pay
	stocks = (
		CassiteriteStock.query
		.filter(CassiteriteStock.balance_to_pay > 0)
		.all()
	)
	form.stock_id.choices = [
		(stock.id, f"{stock.voucher_no} - {stock.supplier}") for stock in stocks
	]

	if form.validate_on_submit():
		stock = CassiteriteStock.query.get_or_404(form.stock_id.data)
		amount = form.amount.data

		if amount > stock.remaining_to_pay():
			flash(
				f"Payment exceeds remaining balance ({stock.remaining_to_pay()} RWF).",
				"danger",
			)
			return redirect(url_for("cassiterite.pay_supplier"))

		
			try:
					payment = CassiteriteSupplierPayment(
						stock_id=stock.id,
						amount=amount,
						method=form.method.data,
						reference=form.reference.data,
						note=form.note.data,
					)
					db.session.add(payment)
					db.session.commit()

					# --- Create PaymentReview for supplier payment (cassiterite) ---
					from flask_login import current_user
					from core.models import PaymentReview
					review = PaymentReview(
						mineral_type='cassiterite',
						type='Utanga ibicuruzwa',
						customer=stock.supplier,
						amount=amount,
						currency='RWF',
						payment_id=payment.id,
						created_by_id=getattr(current_user, 'id', None)
					)
					db.session.add(review)
					db.session.commit()

					# --- IN-APP NOTIFICATION TO BOSS ---
					from core.models import create_notification, User
					boss_user = User.query.filter_by(role='boss').first()
					if boss_user:
						create_notification(
							user_id=boss_user.id,
							type_='Kwishyura utanga ibicuruzwa',
							message=f"Hasabwe kwemeza: Kwishyura utanga ibicuruzwa kuri Gasegereti - {stock.supplier}, Amafaranga: {amount} RWF.",
							related_type='Kwishyura utanga ibicuruzwa(gasegereti)',
							related_id=payment.id
						)

					# Persist in-app notification before attempting email
					db.session.commit()

					# --- EMAIL NOTIFICATION TO BOSS ---
					from flask_mail import Message
					from flask import current_app
					from app import mail
					boss_email = [boss_user.email] if boss_user and boss_user.email else ["boss@example.com"]
					payment_details = (
						f"Utanga amabuye: {stock.supplier}, Amafaranga: {amount} RWF, Uburyo: {form.method.data}, "
						f"Reference: {form.reference.data}, Impamvu: {form.note.data}"
					)
					msg = Message(
						subject="Gusaba kwemeza igikorwa: Kwishyura utanga Amabuye (Gasegereti)",
						sender=current_app.config['MAIL_USERNAME'],
						recipients=boss_email
					)
					msg.body = f"""
		Nyakubahwa Muyobozi,

		Umucungamutungo {getattr(current_user, 'username', 'Unknown')} ({getattr(current_user, 'email', 'Unknown')}) yasabye kwemeza ubwishyu bukurikira kuri Gasegereti:

		{payment_details}

		Nyamuneka musuzume kandi mwemeze.
		Mujye Muri Sisiteme kwemeza iki gikorwa.

		Murakoze,
		Urumuli Smart  System
					"""
					try:
						mail.send(msg)
					except Exception as e:
						import logging
						logging.exception("Failed to send cassiterite supplier payment email notification")
						flash("Email notification failed; in-app notification saved.", "warning")

					flash(
						f"Payment of {amount} RWF recorded for {stock.supplier}.",
						"success",
					)
					return redirect(url_for("cassiterite.pay_supplier"))
			except Exception as e:  # pragma: no cover - defensive
					db.session.rollback()
	supplier_summaries = []

	for stock in stocks:
		total_paid = sum(p.amount for p in stock.supplier_payments)
		remaining = (stock.balance_to_pay or 0) - total_paid

		if remaining <= 0:
			continue

		supplier_summaries.append(
			{
				"stock_id": stock.id,
				"supplier": stock.supplier,
				"voucher_no": stock.voucher_no,
				"owed": float(stock.balance_to_pay or 0),
				"paid": float(total_paid),
				"remaining": float(remaining),
			}
		)

	return render_template(
		"cassiterite/pay_supplier.html",
		form=form,
		supplier_summaries=supplier_summaries,
	)



@cassiterite_bp.route('/supplier/payment/<int:payment_id>/receipt')
@role_required('accountant')
def supplier_receipt(payment_id):
    """
    Shows a printable receipt for a supplier payment.
    """
    payment = CassiteriteSupplierPayment.query.get(payment_id)
    if not payment:
        return render_template('404.html'), 404
    return render_template('receipts/supplier_receipt.html', payment=payment)


@cassiterite_bp.route('/worker/payment/<int:payment_id>/receipt')
@role_required('accountant')
def worker_receipt(payment_id):
	"""
	Shows a printable receipt for a worker payment.
	"""
	payment = CassiteriteWorkerPayment.query.get(payment_id)
	if not payment:
		return render_template('404.html'), 404
	return render_template('receipts/worker_receipt.html', payment=payment)


@cassiterite_bp.route('/supplier/payment/<int:payment_id>/edit', methods=['GET', 'POST'])
@role_required('accountant')
def edit_supplier_payment(payment_id):
	from cassiterite.forms import CassiteriteSupplierPaymentForm
	from cassiterite.models.payment import CassiteriteSupplierPayment
	from cassiterite.models.stock import CassiteriteStock
	from core.models import PaymentReview

	payment = CassiteriteSupplierPayment.query.get_or_404(payment_id)
	form = CassiteriteSupplierPaymentForm()

	# populate choices
	stocks = CassiteriteStock.query.order_by(CassiteriteStock.date.desc()).all()
	form.stock_id.choices = [(s.id, f"{s.voucher_no} - {s.supplier}") for s in stocks]

	if form.validate_on_submit():
		# require a reason for edits
		if not (form.change_reason.data and form.change_reason.data.strip()):
			flash('Change reason is required when editing a payment.', 'danger')
			return render_template('cassiterite/edit_supplier_payment.html', form=form, payment=payment)

		try:
			stock = CassiteriteStock.query.get(form.stock_id.data)
			payment.stock_id = stock.id
			payment.amount = form.amount.data
			payment.method = form.method.data
			payment.reference = form.reference.data
			payment.note = form.note.data
			db.session.add(payment)
			db.session.commit()

			# Create a new PaymentReview for boss to review this change (do not overwrite existing reviews)
			from flask_login import current_user as _current_user
			from core.models import create_notification, User
			review = PaymentReview(
				mineral_type='cassiterite',
				type='Utanga amabuye',
				customer=stock.supplier,
				amount=payment.amount,
				currency='RWF',
				payment_id=payment.id,
				created_by_id=getattr(_current_user, 'id', None),
				boss_comment=(f"Edit requested: {form.change_reason.data.strip()}"),
			)
			db.session.add(review)
			boss_user = User.query.filter_by(role='boss').first()
			if boss_user:
				create_notification(
					user_id=boss_user.id,
					type_='Ihindurwa ku  kwishyura utanga ibicuruzwa',
					message=f"Hasabwe gusuzuma: Impinduka ku kwishyura utanga ibicuruzwa - {stock.supplier}, Amafaranga: {payment.amount} RWF. Impamvu: {form.change_reason.data.strip()}",
					related_type='cassiterite_supplier_payment',
					related_id=payment.id,
				)
			db.session.commit()

			# best-effort email to boss
			try:
				from flask import current_app
				from flask_mail import Message
				from app import mail
				boss_email = [boss_user.email] if boss_user and boss_user.email else ["boss@example.com"]
				msg = Message(
					subject="Saba Kwemezwa: Impinduka kuri Kwishyura utanga Ibicuruzwa (Gasegereti)",
					sender=current_app.config.get('MAIL_USERNAME'),
					recipients=boss_email,
				)
				msg.body = (
					f"Nyakubahwa Muyobozi,\n\nUmucungamutungo {getattr(_current_user,'username','Unknown')} "
					f"yasabye ko musuzuma impinduka zikurikira kuri kwishyura utanga ibicuruzwa kuri Gasegereti:\n\n"
					f"Umutanga: {stock.supplier}\nAmafaranga (byahinduwe): {payment.amount} RWF\nImpamvu: {form.change_reason.data.strip()}\n\n"
					"Murakoze,\nMujye muri system kwemeza iki gikorwa.\n Urumuli Smart System"
				)
				try:
					mail.send(msg)
				except Exception:
					import logging
					logging.exception("Failed to send supplier edit email")
					flash("Email notification failed; in-app notification saved.", "warning")
			except Exception:
				pass

			flash('Supplier payment updated; boss has been notified to review the change.', 'success')
			return redirect(url_for('cassiterite.cassiterite_supplier_ledger', supplier=stock.supplier))
		except Exception as e:
			db.session.rollback()
			flash(f'Error updating payment: {e}', 'danger')

	# pre-fill form
	if not form.is_submitted():
		form.stock_id.data = payment.stock_id
		form.amount.data = payment.amount
		form.method.data = payment.method
		form.reference.data = payment.reference
		form.note.data = payment.note

	return render_template('cassiterite/edit_supplier_payment.html', form=form, payment=payment)


@cassiterite_bp.route('/supplier/payment/<int:payment_id>/delete', methods=['POST'])
@role_required('accountant')
def delete_supplier_payment(payment_id):
	from cassiterite.models.payment import CassiteriteSupplierPayment
	from cassiterite.models.stock import CassiteriteStock
	from core.models import PaymentReview

	payment = CassiteriteSupplierPayment.query.get_or_404(payment_id)
	stock = CassiteriteStock.query.get(payment.stock_id)
	supplier = stock.supplier if stock else None
	# require a reason for deletion (submitted via hidden input)
	reason = request.form.get('change_reason', '')
	if not reason or not reason.strip():
		flash('Delete reason is required.', 'danger')
		return redirect(url_for('cassiterite.cassiterite_supplier_ledger', supplier=supplier) if supplier else url_for('cassiterite.pay_supplier'))

	try:
		from flask_login import current_user as _current_user
		from core.models import create_notification, User
		# create a PaymentReview representing the delete request
		review = PaymentReview(
			mineral_type='cassiterite',
			type='supplier',
			customer=supplier,
			amount=payment.amount,
			currency='RWF',
			payment_id=payment.id,
			created_by_id=getattr(_current_user, 'id', None),
			boss_comment=(f"Delete requested: {reason.strip()}"),
		)
		db.session.add(review)
		boss_user = User.query.filter_by(role='boss').first()
		if boss_user:
			create_notification(
				user_id=boss_user.id,
				type_='Gusaba Gusiba igikorwa',
				message=f"Hasabwe gusuzuma: Gusiba kwishyura utanga amabuye  (Gasegereti) - {supplier}, Amafaranga: {payment.amount} RWF. Icyitonderwa: {reason.strip()}",
				related_type='cassiterite_supplier_payment',
				related_id=payment.id,
			)
		db.session.commit()
		flash('Delete request submitted for boss review; payment was not deleted until approval.', 'success')
	except Exception as e:
		db.session.rollback()
		flash(f'Error submitting delete request: {e}', 'danger')

	if supplier:
		return redirect(url_for('cassiterite.cassiterite_supplier_ledger', supplier=supplier))
	return redirect(url_for('cassiterite.pay_supplier'))


@cassiterite_bp.route('/worker/payment/<int:payment_id>/edit', methods=['GET', 'POST'])
@role_required('accountant')
def edit_worker_payment(payment_id):
	from cassiterite.forms import CassiteriteWorkerPaymentForm
	from cassiterite.models.workers_payment import CassiteriteWorkerPayment
	from core.models import PaymentReview

	payment = CassiteriteWorkerPayment.query.get_or_404(payment_id)
	form = CassiteriteWorkerPaymentForm()

	if form.validate_on_submit():
		# require reason for edits
		if not (form.change_reason.data and form.change_reason.data.strip()):
			flash('Change reason is required when editing a payment.', 'danger')
			return render_template('cassiterite/edit_worker_payment.html', form=form, payment=payment)

		try:
			payment.worker_name = form.worker_name.data
			payment.amount = form.amount.data
			payment.method = form.method.data
			payment.reference = form.reference.data
			payment.note = form.note.data
			db.session.add(payment)
			db.session.commit()

			# create a PENDING review for the boss to inspect this edit
			from flask_login import current_user as _current_user
			from core.models import create_notification, User
			review = PaymentReview(
				mineral_type=None,
				type='worker',
				customer=payment.worker_name,
				amount=payment.amount,
				currency='RWF',
				payment_id=payment.id,
				created_by_id=getattr(_current_user, 'id', None),
				boss_comment=(f"Edit requested: {form.change_reason.data.strip()}"),
			)
			db.session.add(review)
			boss_user = User.query.filter_by(role='boss').first()
			if boss_user:
				create_notification(
					user_id=boss_user.id,
					type_='PAYMENT_EDIT_REQUEST',
					message=f"Hasabwe gusuzuma: Impinduka ku kwishyura umukozi - {payment.worker_name}, Amafaranga: {payment.amount} RWF. Icyitonderwa: {form.change_reason.data.strip()}",
					related_type='cassiterite_worker_payment',
					related_id=payment.id,
				)
			db.session.commit()

			flash('Worker payment updated; boss has been notified to review the change.', 'success')
			return redirect(url_for('cassiterite.pay_worker'))
		except Exception as e:
			db.session.rollback()
			flash(f'Error updating payment: {e}', 'danger')

	if not form.is_submitted():
		form.worker_name.data = payment.worker_name
		form.amount.data = payment.amount
		form.method.data = payment.method
		form.reference.data = payment.reference
		form.note.data = payment.note

	return render_template('cassiterite/edit_worker_payment.html', form=form, payment=payment)


@cassiterite_bp.route('/worker/payment/<int:payment_id>/delete', methods=['POST'])
@role_required('accountant')
def delete_worker_payment(payment_id):
	from cassiterite.models.workers_payment import CassiteriteWorkerPayment
	from core.models import PaymentReview

	payment = CassiteriteWorkerPayment.query.get_or_404(payment_id)
	reason = request.form.get('change_reason', '')
	if not reason or not reason.strip():
		flash('Delete reason is required.', 'danger')
		return redirect(url_for('cassiterite.pay_worker'))

	try:
		from flask_login import current_user as _current_user
		from core.models import create_notification, User
		review = PaymentReview(
			mineral_type=None,
			type='worker',
			customer=payment.worker_name,
			amount=payment.amount,
			currency='RWF',
			payment_id=payment.id,
			created_by_id=getattr(_current_user, 'id', None),
			boss_comment=(f"Delete requested: {reason.strip()}"),
		)
		db.session.add(review)
		boss_user = User.query.filter_by(role='boss').first()
		if boss_user:
			create_notification(
				user_id=boss_user.id,
				type_='PAYMENT_DELETE_REQUEST',
				message=f"Hasabwe gusuzuma: Gusiba kwishyura umukozi - {payment.worker_name}, Amafaranga: {payment.amount} RWF. Icyitonderwa: {reason.strip()}",
				related_type='cassiterite_worker_payment',
				related_id=payment.id,
			)
		db.session.commit()
		flash('Delete request submitted for boss review; payment was not deleted until approval.', 'success')
	except Exception as e:
		db.session.rollback()
		flash(f'Error submitting delete request: {e}', 'danger')

	return redirect(url_for('cassiterite.pay_worker'))


@cassiterite_bp.route("/supplier/<supplier>/ledger")
@role_required("accountant")
def cassiterite_supplier_ledger(supplier):
	"""Detailed ledger view for a single cassiterite supplier."""

	# All stocks and payments for this supplier
	stocks = CassiteriteStock.query.filter_by(supplier=supplier).order_by(CassiteriteStock.date).all()

	payments = (
		CassiteriteSupplierPayment.query
		.join(CassiteriteStock, CassiteriteStock.id == CassiteriteSupplierPayment.stock_id)
		.filter(CassiteriteStock.supplier == supplier)
		.order_by(CassiteriteSupplierPayment.paid_at)
		.all()
	)

	# Build combined ledger entries (purchases = debit, payments = credit)
	ledger_entries = []

	for stock in stocks:
		ledger_entries.append(
			{
				"date": stock.date,
				"description": f"Purchase {stock.voucher_no}",
				"debit": float(stock.balance_to_pay or 0),
				"credit": 0.0,
				"is_payment": False,
			}
		)

	for payment in payments:
		ledger_entries.append(
			{
				"date": payment.paid_at.date() if payment.paid_at else None,
				"description": f"Payment (ref: {payment.reference or 'N/A'})",
				"debit": 0.0,
				"credit": float(payment.amount or 0),
				"is_payment": True,
				"payment_id": payment.id,
			}
		)

	# Sort all entries by date
	ledger_entries.sort(key=lambda x: x["date"] or 0)

	# Compute running balance and totals
	balance = 0.0
	total_owed = 0.0
	total_paid = 0.0

	for entry in ledger_entries:
		balance += entry["debit"] - entry["credit"]
		entry["balance"] = balance
		total_owed += entry["debit"]
		total_paid += entry["credit"]

	return render_template(
		"cassiterite/supplier_ledger.html",
		supplier=supplier,
		ledger_entries=ledger_entries,
		total_owed=total_owed,
		total_paid=total_paid,
		balance=balance,
		user_role=getattr(current_user, 'role', None),
	)
