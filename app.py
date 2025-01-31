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
from sqlalchemy import func

# Configuración de logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'caracas'

ENV = 'prod'  # O cámbialo a 'dev' según tu entorno

if ENV == 'dev':
    app.debug = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Casco2021*@localhost:5433/postgres'
else:
    app.debug = False
    db_url = os.environ.get('DATABASE_URL', 'postgresql://...')
    # Ajuste para evitar problemas con 'postgres://'
    db_url = db_url.replace('postgres://', 'postgresql://')
    
    # Forzar sslmode
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
    __tablename__ = 'store'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    address = db.Column(db.String(100), nullable=False)

class Product(db.Model):
    __tablename__ = 'product'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100))
    presentation = db.Column(db.String(100))
    distributor = db.Column(db.String(100))

class Price(db.Model):
    __tablename__ = 'price'
    id = db.Column(db.Integer, primary_key=True)
    price = db.Column(db.Float, nullable=False)
    date = db.Column(db.DateTime, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey('store.id'), nullable=False)
    presentation = db.Column(db.String(100))
    brand = db.Column(db.String(100))

    # Relaciones
    product = db.relationship('Product', backref='prices')
    store = db.relationship('Store', backref='prices')


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
# RUTAS PRINCIPALES
# ----------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static'),
        'favicon.ico',
        mimetype='image/vnd.microsoft.icon'
    )

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
    stores_data = Store.query.order_by(Store.id).all()
    return render_template('stores.html', stores=stores_data)

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

    query = Product.query

    if search:
        query = query.filter(
            Product.name.ilike(f'%{search}%') |
            Product.brand.ilike(f'%{search}%') |
            Product.presentation.ilike(f'%{search}%') |
            Product.distributor.ilike(f'%{search}%')
        )

    if sort == 'name':
        query = query.order_by(Product.name)
    elif sort == 'brand':
        query = query.order_by(Product.brand)
    elif sort == 'presentation':
        query = query.order_by(Product.presentation)
    elif sort == 'distributor':
        query = query.order_by(Product.distributor)
    else:
        query = query.order_by(Product.id)

    products_pag = query.paginate(page=page, per_page=25)
    return render_template('products.html', products=products_pag, search=search, sort=sort)

@app.route('/export_products')
def export_products():
    products_data = Product.query.all()

    csv_data = 'ID,Nombre,Marca,Presentación,Distribuidor\n'
    for product in products_data:
        csv_data += (
            f"{product.id},"
            f"{product.name},"
            f"{product.brand},"
            f"{product.presentation},"
            f"{product.distributor}\n"
        )

    response = make_response(csv_data)
    response.headers['Content-Disposition'] = 'attachment; filename=products.csv'
    response.mimetype = 'text/csv'
    return response


# ----------------------------------------------------------------
# PRECIOS
# ----------------------------------------------------------------
@app.route('/add_price', methods=['GET', 'POST'])
def add_price():
    form = PriceForm()

    # Rellenar las opciones
    form.product.choices = [(prod.id, prod.name) for prod in Product.query.all()]
    form.store.choices = [(st.id, st.name) for st in Store.query.all()]

    brands = db.session.query(Product.brand).distinct().all()
    brand_choices = [(b[0], b[0]) for b in brands if b[0]]
    form.brand.choices = brand_choices

    if form.validate_on_submit():
        product_id = form.product.data
        brand = form.brand.data
        store_id = form.store.data
        presentation = form.presentation.data
        price_value = form.price.data
        date_value = form.date.data

        new_price = Price(
            product_id=product_id,
            brand=brand,
            store_id=store_id,
            presentation=presentation,
            price=price_value,
            date=date_value
        )

        db.session.add(new_price)

        try:
            db.session.commit()
            return redirect(url_for('prices'))
        except DatabaseError as e:
            db.session.rollback()
            logger.error(str(e))
            error_message = "Ocurrió un error al intentar agregar el precio."
            return render_template('add_price.html', form=form, error_message=error_message)

    return render_template('add_price.html', form=form)

@app.route('/add_price_form', methods=['GET'])
def show_add_price_form():
    form = PriceForm()
    form.product.choices = [(prod.id, prod.name) for prod in Product.query.all()]
    form.store.choices = [(st.id, st.name) for st in Store.query.all()]
    brands = db.session.query(Product.brand).distinct().all()
    brand_choices = [(b[0], b[0]) for b in brands if b[0]]
    form.brand.choices = brand_choices

    return render_template('add_price.html', form=form)

@app.route('/prices', methods=['GET', 'POST'])
def prices():
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'id')
    page = request.args.get('page', 1, type=int)

    query = Price.query

    if search:
        query = query.filter(
            Price.product.has(Product.name.ilike(f'%{search}%')) |
            Price.store.has(Store.name.ilike(f'%{search}%')) |
            Price.presentation.ilike(f'%{search}%') |
            Price.brand.ilike(f'%{search}%')
        )

    if sort == 'product':
        query = query.join(Product).order_by(Product.name)
    elif sort == 'store':
        query = query.join(Store).order_by(Store.name)
    elif sort == 'presentation':
        query = query.order_by(Price.presentation)
    elif sort == 'brand':
        query = query.order_by(Price.brand)
    elif sort == 'price':
        query = query.order_by(Price.price)
    elif sort == 'date':
        query = query.order_by(Price.date)
    else:
        query = query.order_by(Price.id)

    prices_pag = query.paginate(page=page, per_page=25)
    return render_template('prices.html', prices=prices_pag, search=search, sort=sort)

@app.route('/export_prices')
def export_prices():
    prices_data = Price.query.all()

    csv_data = 'ID,Producto,Marca,Tienda,Presentación,Precio,Fecha\n'
    for p in prices_data:
        csv_data += (
            f"{p.id},"
            f"{p.product.name},"
            f"{p.brand},"
            f"{p.store.name},"
            f"{p.presentation},"
            f"{p.price},"
            f"{p.date.strftime('%Y-%m-%d')}\n"
        )

    response = make_response(csv_data)
    response.headers['Content-Disposition'] = 'attachment; filename=prices.csv'
    response.mimetype = 'text/csv'
    return response


# ----------------------------------------------------------------
# GENERACIÓN DE GRÁFICOS
# ----------------------------------------------------------------
@app.route('/generate_graph', methods=['GET'])
def show_generate_graph():
    try:
        # Obtener productos y tiendas ordenados por nombre
        products = Product.query.order_by(Product.name).all()
        stores = Store.query.order_by(Store.name).all()

        # Obtener todas las marcas (distinct) de la tabla Price
        all_brands = (
            db.session.query(Price.brand)
            .distinct()
            .filter(Price.brand.isnot(None))
            .all()
        )
        # Convertir la lista de tuplas [(marca1,), (marca2,)] en [marca1, marca2]
        all_brands = [b[0] for b in all_brands]

        # Obtener todas las presentaciones (distinct) de la tabla Price
        all_presentations = (
            db.session.query(Price.presentation)
            .distinct()
            .filter(Price.presentation.isnot(None))
            .all()
        )
        all_presentations = [p[0] for p in all_presentations]

        # Obtener la fecha actual
        today = datetime.now().strftime('%Y-%m-%d')

        return render_template(
            'generate_graph.html',
            products=products,
            stores=stores,
            all_brands=all_brands,
            all_presentations=all_presentations,
            today=today
        )
    except Exception as e:
        logger.error(f"Error in show_generate_graph: {str(e)}")
        return render_template('error.html', error="Error al cargar la página de gráficos")

@app.route('/get_product_details/<string:product_name>')
def get_product_details(product_name):
    try:
        # Trae presentaciones y marcas de Price, unidas con Product para filtrar por nombre
        presentations = (
            db.session.query(Price.presentation)
            .join(Product)
            .filter(Product.name == product_name)
            .group_by(Price.presentation)
            .order_by(Price.presentation)
            .all()
        )

        brands = (
            db.session.query(Price.brand)
            .join(Product)
            .filter(Product.name == product_name)
            .group_by(Price.brand)
            .order_by(Price.brand)
            .all()
        )

        # Filtrar valores vacíos
        presentations = [p[0] for p in presentations if p[0] and p[0].strip()]
        brands = [b[0] for b in brands if b[0] and b[0].strip()]

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
            title_suffix = f"\nMarca: {form_data['brand_filter']}"
        elif form_data['store_filter'] != "all":
            store = Store.query.filter_by(id=int(form_data['store_filter'])).first()
            if store:
                title_suffix = f"\nTienda: {store.name}"
        else:
            title_suffix = "\nMarca: Todas"

        plot_data = {
            'title': f"Precio de {form_data['product_name']} ({form_data['presentation']}){title_suffix}",
            'xAxisTitle': 'Fecha',
            'yAxisTitle': 'Precio',
            'data': data_series
        }

        return jsonify(plot_data)
    except Exception as e:
        app.logger.error(f"Error generating graph: {str(e)}")
        return jsonify({'error': 'Error al generar el gráfico'}), 500

@app.route('/show_graph')
def show_graph():
    return render_template('graph.html')


# ----------------------------------------------------------------
# FUNCIONES AUXILIARES
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
        Price.date.between(form_data['start_date'], form_data['end_date'])
    )

    # Filtrar por presentación solo si != 'all'
    if form_data['presentation'] != 'all':
        query = query.filter(Price.presentation == form_data['presentation'])

    # Filtrar por tienda solo si != 'all'
    if form_data['store_filter'] != "all":
        store_id = int(form_data['store_filter'])
        query = query.filter(Price.store_id == store_id)

    # Filtrar por marca solo si != 'all'
    if form_data['brand_filter'] != "all":
        query = query.filter(Price.brand == form_data['brand_filter'])

    return query

def determine_legend_grouping(form_data, query):
    # Caso: no filtras por tienda ni marca => agrupar por brand
    if form_data['store_filter'] == "all" and form_data['brand_filter'] == "all":
        return query.with_entities(Price.brand).distinct().all(), 'brand'
    # Caso: filtras una marca => agrupar por tienda
    elif form_data['brand_filter'] != "all":
        return query.with_entities(Price.store_id).distinct().all(), 'store_id'
    else:
        # tienda es 'all', marca no => agrupar por brand
        return query.with_entities(Price.brand).distinct().all(), 'brand'

def build_data_series(query, legend_group, legend_key):
    data_series = []

    for item in legend_group:
        key_value = getattr(item, legend_key)
        prices_for_group = (
            query.filter_by(**{legend_key: key_value})
            .group_by(func.date(Price.date))
            .with_entities(func.date(Price.date), func.avg(Price.price))
            .all()
        )

        dates = [pf[0].strftime('%Y-%m-%d') for pf in prices_for_group]
        prices = [pf[1] for pf in prices_for_group]

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
