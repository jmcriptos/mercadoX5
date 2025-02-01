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


# -------------------------------
#   RUTAS PARA GENERAR GRÁFICOS
# -------------------------------
@app.route('/generate_graph', methods=['GET'])
def show_generate_graph():
    try:
        products = Product.query.order_by(Product.name).all()
        stores = Store.query.order_by(Store.name).all()
        
        # Obtener TODAS las marcas distintas en la tabla Price
        all_brands = (
            db.session.query(Price.brand)
            .distinct()
            .filter(Price.brand.isnot(None))
            .all()
        )
        # Convertir de [(marca1,), (marca2,)] a [marca1, marca2]
        all_brands = [b[0] for b in all_brands]

        # Obtener TODAS las presentaciones distintas en la tabla Price
        all_presentations = (
            db.session.query(Price.presentation)
            .distinct()
            .filter(Price.presentation.isnot(None))
            .all()
        )
        all_presentations = [p[0] for p in all_presentations]

        # Fecha de hoy (por si quieres usarla en tu formulario)
        today = datetime.now().strftime('%Y-%m-%d')

        return render_template(
            'generate_graph.html',
            products=products,               # Lista de productos
            stores=stores,                   # Lista de tiendas
            all_brands=all_brands,           # Todas las marcas
            all_presentations=all_presentations,  # Todas las presentaciones
            today=today
        )
    except Exception as e:
        logger.error(f"Error in show_generate_graph: {str(e)}")
        return render_template('error.html', error="Error al cargar la página de gráficos")

@app.route('/graph', methods=['POST'])
def generate_graph():
    try:
        # Extraer datos del formulario
        form_data = {
            'start_date': request.form.get('start_date'),
            'end_date': request.form.get('end_date'),
            'product_name': request.form.get('product_name'),
            'brand': request.form.get('brand'),
            'store': request.form.get('store'),
            'presentation': request.form.get('presentation')
        }

        # Validar campos obligatorios (puedes ajustar a tus necesidades)
        required_fields = ['start_date', 'end_date']
        for field in required_fields:
            if not form_data[field]:
                raise ValueError(f"Campo requerido faltante: {field}")

        # Construir la consulta base
        query = (
            db.session.query(
                Price.date,
                Price.price,
                Store.name.label('store_name'),
                Price.brand,
                Product.name.label('product_name'),
                Price.presentation
            )
            .join(Product)
            .join(Store)
            .filter(
                Price.date.between(form_data['start_date'], form_data['end_date'])
            )
        )

        # Filtro por producto (solo si != 'all')
        if form_data['product_name'] and form_data['product_name'] != 'all':
            query = query.filter(Product.name == form_data['product_name'])

        # Filtro por marca (solo si != 'all')
        if form_data['brand'] and form_data['brand'] != 'all':
            query = query.filter(Price.brand == form_data['brand'])

        # Filtro por tienda (solo si != 'all')
        if form_data['store'] and form_data['store'] != 'all':
            query = query.filter(Store.id == form_data['store'])

        # Filtro por presentación (solo si != 'all')
        if form_data['presentation'] and form_data['presentation'] != 'all':
            query = query.filter(Price.presentation == form_data['presentation'])

        # Ordenar por fecha
        query = query.order_by(Price.date)
        results = query.all()

        if not results:
            return jsonify({'error': 'No se encontraron datos con estos filtros'}), 404

        # Agrupar resultados en un formato “series” para Plotly
        data_series = []
        grouped_data = {}

        for row in results:
            # Ejemplo de agrupación: si filtras marca => agrupar por tienda
            # sino, agrupar por “tienda - marca”
            # (usa la lógica que prefieras)
            if form_data['brand'] != 'all':
                key = row.store_name
                label = row.store_name
            else:
                key = f"{row.store_name}-{row.brand}"
                label = f"{row.store_name} - {row.brand}"

            if key not in grouped_data:
                grouped_data[key] = {
                    'dates': [],
                    'prices': [],
                    'label': label
                }

            grouped_data[key]['dates'].append(row.date.strftime('%Y-%m-%d'))
            grouped_data[key]['prices'].append(float(row.price))

        data_series = list(grouped_data.values())

        # Título final
        # Si el valor es 'all' lo interpretamos como "Todos/as"
        producto = form_data['product_name'] if form_data['product_name'] != 'all' else 'Todos los productos'
        marca = form_data['brand'] if form_data['brand'] != 'all' else 'Todas las marcas'
        presentacion = form_data['presentation'] if form_data['presentation'] != 'all' else 'Todas las presentaciones'

        titulo = (
            f"{producto} {marca} de {presentacion}"
        )

        plot_data = {
            'title': titulo,
            'data': data_series
        }
        return jsonify(plot_data)

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Error en /graph: {e}")
        return jsonify({'error': 'Error al generar el gráfico'}), 500



@app.route('/show_graph')
def show_graph():
    """
    Genera un gráfico sin formulario, tomando valores de ejemplo (hardcodeados).
    Luego renderiza el template graph.html con los datos 'plot_data'.
    """
    # 1. Campos de ejemplo (en vez de brand_filter, store_filter)
    form_data = {
        "start_date": "2023-01-01",
        "end_date": "2025-01-31",
        "product_name": "Deviled Ham",
        "brand": "Underwood",    # Se unifica el nombre con la ruta /graph
        "store": "all",
        "presentation": "120 g"
    }

    # 2. Usar funciones auxiliares para construir la data
    base_query = build_base_query(form_data)
    legend_group, legend_key = determine_legend_grouping(form_data, base_query)
    data_series = build_data_series(base_query, legend_group, legend_key)

    # 3. Armar título
    title_suffix = ""
    if form_data["brand"] != "all":
        title_suffix = f"\nMarca: {form_data['brand']}"
    elif form_data["store"] != "all":
        store_obj = Store.query.get(int(form_data["store"]))
        if store_obj:
            title_suffix = f"\nTienda: {store_obj.name}"
    else:
        title_suffix = "\nMarca: Todas"

    plot_data = {
        "title": f"Precio de {form_data['product_name']} ({form_data['presentation']}){title_suffix}",
        "data": data_series
    }

    return render_template('graph.html', data=plot_data)




# ----------------------------------------------------------------
# FUNCIONES AUXILIARES (versión corregida)
# ----------------------------------------------------------------
def extract_form_data(form):
    """
    Extrae los valores del formulario bajo nombres consistentes:
    'brand' y 'store' en lugar de 'brand_filter' y 'store_filter'.
    """
    return {
        "start_date": form.get('start_date'),
        "end_date": form.get('end_date'),
        "product_name": form.get('product_name'),
        "presentation": form.get('presentation'),
        "store": form.get('store'),      # Antes era store_filter
        "brand": form.get('brand')       # Antes era brand_filter
    }

def build_base_query(form_data):
    """
    Construye una consulta base a la tabla Price en función de:
      - producto (product_name),
      - fechas (start_date y end_date),
      - presentación (presentation),
      - tienda (store),
      - marca (brand).
    """
    product = Product.query.filter_by(name=form_data['product_name']).first()
    if not product:
        # Retorna un JSON de error si no se encuentra el producto
        return jsonify({"error": "Producto no encontrado."}), 404

    # Consulta base filtrada por producto y fechas
    query = Price.query.filter(
        Price.product_id == product.id,
        Price.date.between(form_data['start_date'], form_data['end_date'])
    )

    # Filtra por presentación (si la selección no es 'all')
    if form_data['presentation'] != 'all':
        query = query.filter(Price.presentation == form_data['presentation'])

    # Filtra por tienda (si la selección no es 'all')
    if form_data['store'] != "all":
        store_id = int(form_data['store'])
        query = query.filter(Price.store_id == store_id)

    # Filtra por marca (si la selección no es 'all')
    if form_data['brand'] != "all":
        query = query.filter(Price.brand == form_data['brand'])

    return query

def determine_legend_grouping(form_data, query):
    """
    Determina si el gráfico se agrupa por 'brand' o por 'store_id',
    en función de los filtros seleccionados.
    """
    # Caso 1: No filtras por tienda ni marca => agrupar por brand
    if form_data['store'] == "all" and form_data['brand'] == "all":
        distinct_brands = query.with_entities(Price.brand).distinct().all()
        return distinct_brands, 'brand'

    # Caso 2: Filtras una marca => agrupar por tienda
    elif form_data['brand'] != "all":
        distinct_stores = query.with_entities(Price.store_id).distinct().all()
        return distinct_stores, 'store_id'

    # Caso 3: Filtras tienda, pero marca == 'all' => agrupar por brand
    else:
        distinct_brands = query.with_entities(Price.brand).distinct().all()
        return distinct_brands, 'brand'

def build_data_series(query, legend_group, legend_key):
    """
    Construye la estructura 'data_series' para Plotly.
    Cada elemento en legend_group es un brand o un store_id
    (según legend_key). Calculamos las fechas y promedios de precio.
    """
    data_series = []

    for item in legend_group:
        key_value = getattr(item, legend_key)  # Puede ser brand o store_id

        # Consulta para obtener promedio de precio agrupado por fecha
        prices_for_group = (
            query.filter_by(**{legend_key: key_value})
            .group_by(func.date(Price.date))
            .with_entities(
                func.date(Price.date),
                func.avg(Price.price)
            )
            .all()
        )

        # Extraemos fechas y promedios para Plotly
        dates = [pf[0].strftime('%Y-%m-%d') for pf in prices_for_group]
        prices = [pf[1] for pf in prices_for_group]

        # Si estamos agrupando por brand, la etiqueta es la marca;
        # si agrupamos por store_id, es el nombre de la tienda.
        if legend_key == 'brand':
            label = key_value
        else:
            store = Store.query.get(key_value)
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
