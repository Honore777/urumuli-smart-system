"""Smart Account Manager - Mining Company System

Main Flask application factory. This file wires together:
- Flask app + database
- Blueprints for minerals and core management
- Authentication (login/logout) using Flask-Login
"""

from flask import Flask, render_template, jsonify, request, redirect, url_for, flash
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_mail import Mail

from config import Config, db
from core.models import User

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)
migrate = Migrate(app, db)

mail=Mail(app)

# ------------------------------------------------------------
# Authentication setup (Flask-Login)
# ------------------------------------------------------------

login_manager = LoginManager(app)
login_manager.login_view = "login"  # endpoint name below


@login_manager.user_loader
def load_user(user_id: str):  # pragma: no cover - tiny glue helper
    """Tell Flask-Login how to load a user from a stored ID."""

    try:
        return User.query.get(int(user_id))
    except (TypeError, ValueError):
        return None


# Import and register blueprints after app/db/login are ready
from copper import copper_bp  # noqa: E402
from cassiterite import cassiterite_bp  # noqa: E402
from core.routes import core_bp  # noqa: E402

app.register_blueprint(copper_bp)
app.register_blueprint(cassiterite_bp)
app.register_blueprint(core_bp)

# Template filters: translate stored review `type` and `mineral_type` into Kinyarwanda
def translate_review_type(type_value):
    if not type_value:
        return 'N/A'
    mapping = {
        'worker': 'Kwishyura Umukozi',
        'supplier': 'Kwishyura Utanga ibicuruzwa',
        'customer': 'Kwishyura Umukiriya',
        'other': 'Ibindi',
    }
    return mapping.get(type_value, type_value)

def translate_mineral(mineral_value):
    if not mineral_value:
        return ''
    mapping = {
        'cassiterite': 'Gasegereti',
        'coltan': 'Coltan',
        'copper': 'Coltan',
    }
    return mapping.get(mineral_value, mineral_value)

app.add_template_filter(translate_review_type, name='translate_review_type')
app.add_template_filter(translate_mineral, name='translate_mineral')

# ============================================================
# ROUTES
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    """Simple username/password login page.

    For now we authenticate by `User.username` and `User.check_password`.
    Only `is_active` users can log in.
    """


    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()

        user = User.query.filter_by(username=username).first()

        if not user or not user.check_password(password):
            flash("Invalid username or password.", "danger")
            return render_template("auth/login.html")

        if not user.is_active:
            flash("This account is inactive. Please contact an administrator.", "warning")
            return render_template("auth/login.html")

        login_user(user)

        # Support ?next=/some/url redirects from login-required pages
        next_url = request.args.get("next")
        if next_url:
            return redirect(next_url)

        # Role-based default landing pages
        if user.role == "admin":
            return redirect(url_for("core.admin_users"))
        if user.role == "boss":
            return redirect(url_for("core.boss_dashboard"))
        if user.role == "store_keeper":
            return redirect(url_for("core.store_dashboard"))
        if user.role == "accountant":
            # Accountants mainly work on operations; send to copper dashboard
            return redirect(url_for("copper.dashboard"))

        # Fallback: generic entry selector
        return redirect(url_for("entry_point"))

    # GET
    return render_template("auth/login.html")


@app.route("/logout")
@login_required
def logout():
    """Log the current user out and return to login screen."""

    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


@app.route("/")
@login_required
def entry_point():
    """Main application entry once logged in.

    Shows the module chooser (Copper / Cassiterite / Boss dashboard).
    """

    # Template lives directly under `templates/entry_point.html`
    return render_template("entry_point.html")







@app.route("/api/dashboard_data")
def api_dashboard_data():
    """API endpoint for dashboard data"""
    from copper.models import CopperStock, CopperOutput
    
    stocks = CopperStock.query.all()
    outputs = CopperOutput.query.all()
    
    return jsonify({
        'total_input': sum(s.input_kg for s in stocks),
        'total_output': sum(o.output_kg for o in outputs),
        'total_debt': sum(o.debt_remaining for o in outputs),
        'stock_count': len(stocks),
        'output_count': len(outputs)
    })


@app.route('/supplier/<supplier>/ledger')
def supplier_ledger(supplier):
    """View supplier transaction ledger"""
    from copper.models import CopperStock, SupplierPayment
    
    stocks = CopperStock.query.filter_by(supplier=supplier).order_by(CopperStock.date).all()
    
    ledger = []
    running_balance = 0
    
    for stock in stocks:
        running_balance += (stock.net_balance or 0)
        ledger.append({
            'date': stock.date,
            'description': f"Stock {stock.voucher_no}",
            'debit': stock.net_balance,
            'credit': 0,
            'balance': running_balance
        })
        
        for payment in stock.supplier_payments:
            running_balance -= payment.amount
            ledger.append({
                'date': payment.paid_at,
                'description': f"Payment (Ref: {payment.reference})",
                'debit': 0,
                'credit': payment.amount,
                'balance': running_balance
            })
    
        # Totals for the ledger
        total_owed = sum((row.get('debit') or 0) for row in ledger)
        total_paid = sum((row.get('credit') or 0) for row in ledger)
        balance = ledger[-1]['balance'] if ledger else 0

        return render_template(
            'copper/supplier_ledger.html',
            supplier=supplier,
            ledger=ledger,
            total_owed=total_owed,
            total_paid=total_paid,
            balance=balance,
            user_role=getattr(current_user, 'role', None),
        )


# ============================================================
# ERROR HANDLERS
# ============================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    return render_template('copper/404.html'), 404


@app.errorhandler(500)
def server_error(error):
    """Handle 500 errors"""
    return render_template('copper/500.html'), 500

@app.errorhandler(403)

def forbidden(error):
    """Handle 403 errors"""
    return render_template('403.html'), 403


# ============================================================
# CONTEXT PROCESSORS
# ============================================================

@app.context_processor
def inject_config():
    """Inject config into templates"""
    return dict(app_name="Urumuli Smart System")


# ============================================================
# CLI COMMANDS
# ============================================================

@app.cli.command()
def init_db():
    """Initialize the database"""
    db.create_all()
    print("Database initialized!")


@app.cli.command()
def seed_db():
    """Seed database with sample data (optional)"""
    print("Database seeding complete!")


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)
