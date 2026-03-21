"""
Copper Output Form
For recording copper sales/outputs
"""
from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, SubmitField, DateField, SelectField, TextAreaField
from wtforms.validators import DataRequired, InputRequired, Optional


class CopperOutputForm(FlaskForm):
    """Form for recording copper output"""
    stock_id = SelectField('Select Stock', coerce=int, validators=[DataRequired()])
    date = DateField('Date', format='%Y-%m-%d', validators=[DataRequired()])
    customer = StringField('Customer Name', validators=[Optional()])
    output_kg = FloatField('Output (Kg)', validators=[InputRequired()])
    output_amount = FloatField('Sales Amount', validators=[InputRequired()])
    amount_paid = FloatField('Cash paid', validators=[InputRequired()])
    note = TextAreaField('Note', validators=[Optional()])
    submit = SubmitField('Record Output')
