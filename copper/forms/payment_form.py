"""
Supplier Payment Form
For recording supplier payments
"""
from flask_wtf import FlaskForm
from wtforms import SelectField, FloatField, StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, InputRequired, NumberRange, Optional


class SupplierPaymentForm(FlaskForm):
    """Form for recording supplier payments"""
    stock_id = SelectField(
        'Select Supplier Obligation',
        coerce=int,
        validators=[DataRequired()]
    )
    amount = FloatField(
        'Payment amount (RWF)',
        validators=[InputRequired(), NumberRange(min=0.01)]
    )
    method = SelectField(
        'Payment Method',
        choices=[
            ('cash', 'Cash'),
            ('bank', 'Bank Transfer'),
            ('momo', 'Mobile Money')
        ],
        validators=[DataRequired()]
    )
    reference = StringField(
        'Payment Reference',
        validators=[Optional()]
    )
    note = TextAreaField(
        'Note / Reason',
        validators=[Optional()]
    )
    # When editing or deleting an existing payment, the accountant must
    # provide a short reason explaining the change. Routes will enforce
    # that this is present for edit/delete operations.
    change_reason = TextAreaField(
        'Change reason (required when editing/deleting)',
        validators=[Optional()]
    )
    submit = SubmitField('Record Payment')
