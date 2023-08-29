from flask import Flask, render_template, request, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError, DatabaseError
from flask_migrate import Migrate
from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, SubmitField, StringField
from wtforms.validators import DataRequired
from wtforms import DateField
from sqlalchemy import and_

import os



app = Flask(__name__)
app.config['SECRET_KEY'] = 'caracas'

ENV = 'prod'

if ENV == 'dev':
    app.debug = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Casco2021*@localhost:5433/postgres'
else:
    app.debug = False
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://hkjjcfppgooxip:af8df1993d28685eef7c91d8acff63ccf76909c367c888b7e20455cacf6755a4@ec2-3-217-146-37.compute-1.amazonaws.com:5432/d4mormil7q10tn'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)



class PriceForm(FlaskForm):
    product = SelectField('Product', coerce=int, validators=[DataRequired()])
    presentation = StringField('Presentación', validators=[DataRequired()])
    store = SelectField('Store', coerce=int, validators=[DataRequired()])
    price = DecimalField('Price', validators=[DataRequired()])
    submit = SubmitField('Submit')
    date = DateField('Fecha', format='%Y-%m-%d', validators=[DataRequired()])
    brand = SelectField('Brand', coerce=str)




class Store(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    address = db.Column(db.String(100), nullable=False)


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100))
    presentation = db.Column(db.String(100))
    distributor = db.Column(db.String(100))



class Price(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    price = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    product = db.relationship('Product', backref='prices')
    store = db.relationship('Store', backref='prices')
    presentation = db.Column(db.String(100))
    brand = db.Column(db.String(100))




@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add_store', methods=['GET', 'POST'])
def add_store():
    if request.method == 'POST':
        name = request.form['name']
        address = request.form['address']

        existing_store = Store.query.filter_by(name=name).first()
        if existing_store:
            error_message = "La tienda con ese nombre ya existe."
            return render_template('add_store.html', error_message=error_message)

        new_store = Store(name=name, address=address)
        db.session.add(new_store)
        
        try:
            db.session.commit()
            return redirect(url_for('stores'))
        except IntegrityError:
            db.session.rollback()
            error_message = "Ocurrió un error al intentar agregar la tienda."
            return render_template('add_store.html', error_message=error_message)
        
    return render_template('add_store.html')


@app.route('/stores', methods=['GET', 'POST'])
def stores():
    stores = Store.query.order_by(Store.id).all()
    return render_template('stores.html', stores=stores)


@app.route('/add_product', methods=['GET', 'POST'])
def add_product():
    if request.method == 'POST':
        name = request.form['name']
        brand = request.form['brand']
        presentation = request.form['presentation']  # Directamente toma el valor como texto
        distributor = request.form['distributor']

        existing_product = Product.query.filter_by(name=name, brand=brand).first()
        if existing_product:
            error_message = "El producto con ese nombre y marca ya existe."
            products = Product.query.all()
            return render_template('add_product.html', products=products, error_message=error_message)

        new_product = Product(name=name, brand=brand, presentation=presentation, distributor=distributor)
        db.session.add(new_product)

        try:
            db.session.commit()
            return redirect(url_for('products'))
        except IntegrityError:
            db.session.rollback()
            error_message = "Ocurrió un error al intentar agregar el producto."
            products = Product.query.all()
            return render_template('add_product.html', products=products, error_message=error_message)
        
    products = Product.query.all()
    return render_template('add_product.html', products=products)



@app.route('/products', methods=['GET', 'POST'])
def products():
    products = Product.query.all()
    return render_template('products.html', products=products)

# ... otros códigos ...

@app.route('/add_price', methods=['GET', 'POST'])
def add_price():
    form = PriceForm()
    
    # Rellenar los choices para los campos product, store y brand
    form.product.choices = [(product.id, product.name) for product in Product.query.all()]
    form.store.choices = [(store.id, store.name) for store in Store.query.all()]
    
    brands = db.session.query(Product.brand).distinct().all()
    brand_choices = [(brand[0], brand[0]) for brand in brands]
    form.brand.choices = brand_choices

    if form.validate_on_submit():
        product_id = form.product.data
        brand = form.brand.data
        store_id = form.store.data
        presentation = form.presentation.data
        price_value = form.price.data
        date = form.date.data

        new_price = Price(
            product_id=product_id,
            brand=brand, 
            store_id=store_id,
            presentation=presentation,
            price=price_value,
            date=date
        )

        db.session.add(new_price)

        try:
            db.session.commit()
            return redirect(url_for('prices'))
        except DatabaseError as e:
            db.session.rollback()
            print(str(e))
            error_message = "Ocurrió un error al intentar agregar el precio."
            return render_template('add_price.html', form=form, error_message=error_message)

    # Handle form submission errors by re-rendering the form
    return render_template('add_price.html', form=form)



# Add a default case for the GET request
@app.route('/add_price', methods=['GET'])
def show_add_price_form():
    form = PriceForm()
    form.product.choices = [(product.id, product.name) for product in Product.query.all()]
    form.store.choices = [(store.id, store.name) for store in Store.query.all()]
    brands = db.session.query(Product.brand).distinct().all()
    brand_choices = [(brand[0], brand[0]) for brand in brands]
    form.brand.choices = brand_choices
    return render_template('add_price.html', form=form)

@app.route('/prices', methods=['GET', 'POST'])
def prices():
    prices = Price.query.all()
    return render_template('prices.html', prices=prices)


@app.route('/generate_graph', methods=['GET'])
def show_generate_graph():
    products = Product.query.all()
    stores = Store.query.all()
    presentations = db.session.query(Product.presentation).distinct().all()
    brands = [brand[0] for brand in db.session.query(Price.brand).distinct().all()]

    return render_template('generate_graph.html', products=products, stores=stores, presentations=presentations, brands=brands)

@app.route('/graph', methods=['POST'])
def generate_graph():
    form_data = extract_form_data(request.form)
    
    base_query = build_base_query(form_data)

    legend_group, legend_key = determine_legend_grouping(form_data, base_query)
    
    data_series = build_data_series(base_query, legend_group, legend_key)

    plotly_data = {
        'title': f'Precio de {form_data["product_name"]} ({form_data["presentation"]})',
        'xAxisTitle': 'Fecha',
        'yAxisTitle': 'Precio',
        'data': data_series
    }

    return jsonify(plotly_data)

def extract_form_data(form):
    return {
        "start_date": form.get('start_date'),
        "end_date": form.get('end_date'),
        "product_name": form.get('product_name'),
        "presentation": form.get('presentation'),
        "store_filter": form.get('store'),
        "brand_filter": form.get('brand')
    }

def build_base_query(form_data):
    product = Product.query.filter_by(name=form_data['product_name']).first()
    if not product:
        return jsonify({"error": "Producto no encontrado."}), 404

    query = Price.query.filter(
        Price.product_id == product.id,
        Price.presentation == form_data['presentation'],
        Price.date.between(form_data['start_date'], form_data['end_date'])
    )

    if form_data['store_filter'] != "all":
        store_id = int(form_data['store_filter'])
        query = query.filter(Price.store_id == store_id)

    if form_data['brand_filter'] != "all":
        query = query.filter(Price.brand == form_data['brand_filter'])

    return query

def determine_legend_grouping(form_data, query):
    if form_data['store_filter'] == "all" and form_data['brand_filter'] == "all":
        return query.with_entities(Price.brand).distinct().all(), 'brand'
    elif form_data['brand_filter'] != "all":
        return query.with_entities(Price.store_id).distinct().all(), 'store_id'
    else:
        return query.with_entities(Price.brand).distinct().all(), 'brand'

def build_data_series(query, legend_group, legend_key):
    data_series = []
    
    for item in legend_group:
        key_value = getattr(item, legend_key)
        
        prices_for_group = query.filter_by(**{legend_key: key_value}).all()

        dates = [price.date.strftime('%Y-%m-%d') for price in prices_for_group]
        prices = [price.price for price in prices_for_group]

        if legend_key == 'brand':
            label = key_value
        else:
            store = Store.query.filter_by(id=key_value).first()
            label = store.name if store else 'Desconocido'

        print(f"Label: {label}, Legend Key: {legend_key}, Key Value: {key_value}")  # Logging

        data_series.append({
            'label': label,
            'dates': dates,
            'prices': prices,
        })

    return data_series





if __name__ == '__main__':
    app.run(debug=True)