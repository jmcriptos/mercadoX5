import os
import logging
from datetime import datetime
from flask import Flask, json, render_template, request, redirect, url_for, jsonify, send_from_directory, make_response
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError, DatabaseError
from flask_migrate import Migrate
from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, SubmitField, StringField, DateField
from wtforms.validators import DataRequired
from sqlalchemy import and_, func
# Configuración de logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'caracas'

ENV = 'prod'  

if ENV == 'dev':
   app.debug = True
   app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Casco2021*@localhost:5433/postgres'
else:
   app.debug = False
   db_url = os.environ.get('DATABASE_URL', 'postgresql://nwavnxlfbdwjdx:fa6a36e03575d55940f7ac96531308af8b74203dba33b366436e8c5c02150b3c@ec2-52-205-108-73.compute-1.amazonaws.com:5432/d8hjbhhroo063e')
   db_url = db_url.replace('postgres://', 'postgresql://')
   
   if not db_url.endswith('?sslmode=require'):
       db_url += '?sslmode=require'
   
   app.config['SQLALCHEMY_DATABASE_URI'] = db_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)


# ----------------------------------------------------------------
# MODELOS
# ----------------------------------------------------------------
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


# ----------------------------------------------------------------
# FORMULARIOS
# ----------------------------------------------------------------
class PriceForm(FlaskForm):
    product = SelectField('Product', coerce=int, validators=[DataRequired()])
    presentation = StringField('Presentación', validators=[DataRequired()])
    store = SelectField('Store', coerce=int, validators=[DataRequired()])
    price = DecimalField('Price', validators=[DataRequired()])
    submit = SubmitField('Submit')
    date = DateField('Fecha', format='%Y-%m-%d', validators=[DataRequired()])
    brand = SelectField('Brand', coerce=str)


# ----------------------------------------------------------------
# RUTAS
# ----------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

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
        presentation = request.form['presentation']
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
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'id')
    page = request.args.get('page', 1, type=int)
    
    products = Product.query
    
    if search:
        products = products.filter(Product.name.ilike(f'%{search}%') | 
                                   Product.brand.ilike(f'%{search}%') |
                                   Product.presentation.ilike(f'%{search}%') |
                                   Product.distributor.ilike(f'%{search}%'))
    
    if sort == 'name':
        products = products.order_by(Product.name)
    elif sort == 'brand':
        products = products.order_by(Product.brand)
    elif sort == 'presentation':
        products = products.order_by(Product.presentation)
    elif sort == 'distributor':
        products = products.order_by(Product.distributor)
    else:
        products = products.order_by(Product.id)
    
    products = products.paginate(page=page, per_page=25)
    
    return render_template('products.html', products=products, search=search, sort=sort)

@app.route('/export_products')
def export_products():
    products = Product.query.all()
    
    csv_data = 'ID,Nombre,Marca,Presentación,Distribuidor\n'
    for product in products:
        csv_data += f'{product.id},{product.name},{product.brand},{product.presentation},{product.distributor}\n'
    
    response = make_response(csv_data)
    response.headers['Content-Disposition'] = 'attachment; filename=products.csv'
    response.mimetype = 'text/csv'
    
    return response

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

    # Si no es válido o es GET, renderizamos el formulario
    return render_template('add_price.html', form=form)

# Ruta para mostrar el formulario en caso de que lo necesites por separado (opcional):
@app.route('/add_price_form', methods=['GET'])
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
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'id')
    page = request.args.get('page', 1, type=int)

    prices = Price.query

    if search:
        prices = prices.filter(
            Price.product.has(Product.name.ilike(f'%{search}%')) |
            Price.store.has(Store.name.ilike(f'%{search}%')) |
            Price.presentation.ilike(f'%{search}%') |
            Price.brand.ilike(f'%{search}%')
        )

    if sort == 'product':
        prices = prices.order_by(Product.name)
    elif sort == 'store':
        prices = prices.order_by(Store.name)
    elif sort == 'presentation':
        prices = prices.order_by(Price.presentation)
    elif sort == 'brand':
        prices = prices.order_by(Price.brand)
    elif sort == 'price':
        prices = prices.order_by(Price.price)
    elif sort == 'date':
        prices = prices.order_by(Price.date)
    else:
        prices = prices.order_by(Price.id)

    prices = prices.paginate(page=page, per_page=25)

    return render_template('prices.html', prices=prices, search=search, sort=sort)

@app.route('/export_prices')
def export_prices():
    prices = Price.query.all()

    csv_data = 'ID,Producto,Marca,Tienda,Presentación,Precio,Fecha\n'
    for price in prices:
        csv_data += f'{price.id},{price.product.name},{price.brand},{price.store.name},{price.presentation},{price.price},{price.date.strftime("%Y-%m-%d")}\n'

    response = make_response(csv_data)
    response.headers['Content-Disposition'] = 'attachment; filename=prices.csv'
    response.mimetype = 'text/csv'

    return response

@app.route('/generate_graph', methods=['GET'])
def show_generate_graph():
    try:
        # Obtener productos y tiendas ordenados por nombre
        products = Product.query.order_by(Product.name).all()
        stores = Store.query.order_by(Store.name).all()
        
        # Obtener marcas distintas de los precios
        brands = [brand[0] for brand in db.session.query(Price.brand).distinct().filter(Price.brand.isnot(None)).all()]
        
        # Obtener presentaciones distintas de los precios
        presentations = [pres[0] for pres in db.session.query(Price.presentation).distinct().filter(Price.presentation.isnot(None)).all()]
        
        # Obtener la fecha actual
        today = datetime.now().strftime('%Y-%m-%d')
        
        return render_template('generate_graph.html', 
                             products=products, 
                             stores=stores,
                             brands=brands,
                             presentations=presentations,
                             today=today)
    except Exception as e:
        logger.error(f"Error in show_generate_graph: {str(e)}")
        return render_template('error.html', error="Error al cargar la página de gráficos")@app.route('/generate_graph', methods=['GET'])
def show_generate_graph():
    products = Product.query.all()
    stores = Store.query.all()
    
    # Get distinct presentations from the Price table instead of Product
    presentations = db.session.query(Price.presentation).distinct().all()
    
    # Get brands from the Price table
    brands = [brand[0] for brand in db.session.query(Price.brand).distinct().all()]

    return render_template('generate_graph.html', products=products, stores=stores, presentations=presentations, brands=brands)

@app.route('/get_product_details/<string:product_name>')
def get_product_details(product_name):
    try:
        # Obtener las presentaciones y marcas directamente de la tabla Price
        presentations = db.session.query(Price.presentation)\
            .join(Product)\
            .filter(Product.name == product_name)\
            .group_by(Price.presentation)\
            .order_by(Price.presentation)\
            .all()
        
        brands = db.session.query(Price.brand)\
            .join(Product)\
            .filter(Product.name == product_name)\
            .group_by(Price.brand)\
            .order_by(Price.brand)\
            .all()

        # Limpiar y filtrar los resultados
        presentations = [p[0] for p in presentations if p[0] and p[0].strip()]
        brands = [b[0] for b in brands if b[0] and b[0].strip()]

        # Log para debugging
        app.logger.info(f"Product: {product_name}")
        app.logger.info(f"Presentations found: {presentations}")
        app.logger.info(f"Brands found: {brands}")

        return jsonify({
            'success': True,
            'presentations': presentations,
            'brands': brands
        })
    except Exception as e:
        app.logger.error(f"Error in get_product_details: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Error al obtener detalles del producto: {str(e)}'
        }), 500

@app.route('/graph', methods=['POST'])
def generate_graph():
    try:
        form_data = extract_form_data(request.form)
        base_query = build_base_query(form_data)
        legend_group, legend_key = determine_legend_grouping(form_data, base_query)
        data_series = build_data_series(base_query, legend_group, legend_key)
        
        # Título dinámico
        title_suffix = ''
        if form_data['brand_filter'] != "all":
            title_suffix = f'\nMarca: {form_data["brand_filter"]}'
        elif form_data['store_filter'] != "all":
            store = Store.query.filter_by(id=int(form_data['store_filter'])).first()
            if store:
                title_suffix = f'\nTienda: {store.name}'
        else:
            title_suffix = '\nMarca: Todas'

        plot_data = {
            'title': f'Precio de {form_data["product_name"]} ({form_data["presentation"]}){title_suffix}',
            'xAxisTitle': 'Fecha',
            'yAxisTitle': 'Precio',
            'data': data_series
        }

        return render_template('graph.html', data=plot_data)

    except Exception as e:
        app.logger.error(f"Error generating graph: {str(e)}")
        return render_template('graph.html', error="Error al generar el gráfico")

@app.route('/show_graph')
def show_graph():
    return render_template('graph.html')

# ----------------------------------------------------------------
# Funciones auxiliares para /graph
# ----------------------------------------------------------------
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
        prices_for_group = (query.filter_by(**{legend_key: key_value})
                            .group_by(func.date(Price.date))
                            .with_entities(func.date(Price.date), func.avg(Price.price))
                            .all())
        
        dates = [price[0].strftime('%Y-%m-%d') for price in prices_for_group]
        prices = [price[1] for price in prices_for_group]

        if legend_key == 'brand':
            label = key_value
        else:
            store = Store.query.filter_by(id=key_value).first()
            label = store.name if store else 'Desconocido'

        data_series.append({
            'label': label,
            'dates': dates,
            'prices': prices,
        })

    return data_series

# ----------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)
