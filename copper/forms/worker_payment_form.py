"""
Form for recording internal worker payments/expenses
"""
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SelectField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, InputRequired, NumberRange, Optional

class WorkerPaymentForm(FlaskForm):
    worker_name = StringField(
        'Worker Name',
        validators=[DataRequired()]
    )
    amount = FloatField(
        'Payment Amount (RWF)',
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
    # For edits/deletes: capture why the change is being made.
    change_reason = TextAreaField(
        'Change reason (required when editing/deleting)',
        validators=[Optional()]
    )
    submit = SubmitField('Record Payment')
