import os
import logging
from datetime import datetime, timedelta
from enum import Enum
from flask import Flask, json, render_template, request, redirect, url_for, jsonify, send_from_directory, make_response, flash, abort, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError, DatabaseError
from flask_migrate import Migrate
from flask_wtf import FlaskForm
from wtforms import SelectField, DecimalField, SubmitField, StringField, DateField, PasswordField, BooleanField
from wtforms.validators import DataRequired, Email, EqualTo
from sqlalchemy import func
from functools import wraps
import csv
from io import StringIO


# Importaciones para manejo de usuarios
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Configuración de logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Definición de roles de usuario
class UserRole(Enum):
    ADMIN = 'admin'
    REGISTRO = 'registro'
    CONSULTA = 'consulta'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'caracas'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=120)

ENV = 'prod'
if ENV == 'dev':
    app.debug = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://postgres:Casco2021*@localhost:5432/postgres'
else:
    app.debug = False
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("No database URL configured. Set DATABASE_URL environment variable.")
    db_url = db_url.replace('postgres://', 'postgresql://')
    if not db_url.endswith('?sslmode=require'):
        db_url += '?sslmode=require'
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

# Decoradores para control de acceso
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def registro_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_registro:
            flash('No tienes permisos para acceder a esta sección.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ----------------------------------------------------------------
# CONFIGURACIÓN DE FLASK-LOGIN
# ----------------------------------------------------------------
login = LoginManager(app)
login.login_view = 'login'

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

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.String(20), nullable=False, default=UserRole.CONSULTA.value)
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    @property
    def is_admin(self):
        return self.role == UserRole.ADMIN.value
    @property
    def is_registro(self):
        return self.role in [UserRole.ADMIN.value, UserRole.REGISTRO.value]
    def __repr__(self):
        return f'<User {self.username} (role: {self.role})>'

@login.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ----------------------------------------------------------------
# FORMULARIOS
# ----------------------------------------------------------------
class PriceForm(FlaskForm):
    product = StringField('Producto', validators=[DataRequired()])
    store = SelectField('Tienda', coerce=int, validators=[DataRequired()])
    price = DecimalField('Precio', validators=[DataRequired()])
    date = DateField('Fecha', format='%Y-%m-%d', default=datetime.today, validators=[DataRequired()])
    brand = SelectField('Marca', choices=[('', 'Seleccione una marca')], validators=[DataRequired()])
    submit = SubmitField('Enviar')

class RegistrationForm(FlaskForm):
    username = StringField('Nombre de usuario', validators=[DataRequired()])
    email = StringField('Correo electrónico', validators=[DataRequired(), Email()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    password2 = PasswordField('Confirmar contraseña', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Registrarse')

class LoginForm(FlaskForm):
    username = StringField('Nombre de usuario', validators=[DataRequired()])
    password = PasswordField('Contraseña', validators=[DataRequired()])
    remember_me = BooleanField('Recordarme')
    submit = SubmitField('Iniciar sesión')

class UserEditForm(FlaskForm):
    username = StringField('Nombre de usuario', validators=[DataRequired()])
    email = StringField('Correo electrónico', validators=[DataRequired(), Email()])
    role = SelectField('Rol', choices=[], validators=[DataRequired()])
    password = PasswordField('Nueva contraseña')
    password2 = PasswordField('Confirmar nueva contraseña', validators=[EqualTo('password')])
    submit = SubmitField('Guardar cambios')

# ----------------------------------------------------------------
# RUTAS DE ADMINISTRACIÓN
# ----------------------------------------------------------------
@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    return render_template('admin/panel.html')

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/user/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit_user(user_id):
    user = User.query.get_or_404(user_id)
    form = UserEditForm(obj=user)
    form.role.choices = [(role.value, role.name) for role in UserRole]
    if form.validate_on_submit():
        try:
            user.username = form.username.data
            user.email = form.email.data
            user.role = form.role.data
            if form.password.data:
                user.set_password(form.password.data)
            db.session.commit()
            flash('Usuario actualizado exitosamente', 'success')
            return redirect(url_for('admin_users'))
        except IntegrityError:
            db.session.rollback()
            flash('Error: El nombre de usuario o correo ya están en uso', 'danger')
    return render_template('admin/edit_user.html', form=form, user=user)

@app.route('/admin/user/delete/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def admin_delete_user(user_id):
    if current_user.id == user_id:
        flash('No puedes eliminar tu propio usuario', 'error')
        return redirect(url_for('admin_users'))
    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash('Usuario eliminado exitosamente', 'success')
    return redirect(url_for('admin_users'))

# ----------------------------------------------------------------
# RUTAS PÚBLICAS
# ----------------------------------------------------------------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'GET':
        session.pop('_flashes', None)
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            existing_user = User.query.filter(
                (User.username == form.username.data) | 
                (User.email == form.email.data)
            ).first()
            if existing_user:
                if existing_user.username == form.username.data:
                    flash('El nombre de usuario ya está en uso.')
                else:
                    flash('El correo electrónico ya está en uso.')
                return render_template('register.html', form=form)
            user = User(username=form.username.data, email=form.email.data, role=UserRole.CONSULTA.value)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash('Te has registrado exitosamente. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al registrar usuario: {str(e)}')
            return render_template('register.html', form=form)
    if form.errors:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'Error en {field}: {error}')
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is None or not user.check_password(form.password.data):
            flash('Nombre de usuario o contraseña incorrectos.')
            return redirect(url_for('login'))
        login_user(user, remember=form.remember_me.data)
        flash('Has iniciado sesión correctamente.')
        return redirect(url_for('index'))
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión.')
    return redirect(url_for('login'))

# ----------------------------------------------------------------
# RUTAS PROTEGIDAS
# ----------------------------------------------------------------
@app.errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403

def linear_regression(x_vals, y_vals):
    """
    Calcula la regresión lineal simple (y = m*x + b).
    Retorna (m, b). Si no se puede calcular, retorna (None, None).
    """
    n = len(x_vals)
    if n < 2:
        return None, None

    mean_x = sum(x_vals) / n
    mean_y = sum(y_vals) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, y_vals))
    den = sum((x - mean_x) ** 2 for x in x_vals)
    if den == 0:
        return None, None  # Evitar dividir por cero si x es constante

    m = num / den
    b = mean_y - m * mean_x
    return m, b

def obtener_datos_grafico(product_id, start_date, end_date):
    product = Product.query.get(product_id)
    product_name = product.name if product else f"Producto {product_id}"

    registros = (
        db.session.query(Price)
        .filter(Price.product_id == product_id)
        .filter(Price.date >= start_date, Price.date <= end_date)
        .order_by(Price.date)
        .all()
    )
    if not registros:
        return []

    x_vals = [r.date for r in registros]
    y_vals = [r.price for r in registros]

    # Convertir fechas a string para Plotly
    x_dates_str = [dt.strftime('%Y-%m-%d') for dt in x_vals]

    # Trace de puntos
    points_trace = {
        'x': x_dates_str,
        'y': y_vals,
        'mode': 'markers',
        'marker': {'color': 'blue'},
        'name': product_name
    }

    # Supongamos que tienes una función linear_regression(x_vals, y_vals)
    # que devuelve (m, b). 
    m, b = linear_regression([dt.toordinal() for dt in x_vals], y_vals)
    if m is None:
        # Sin regresión
        return [points_trace]

    # Construir la línea de regresión punteada en rojo
    min_day = min(x_vals).toordinal()
    max_day = max(x_vals).toordinal()
    step = max(1, (max_day - min_day) // 50)
    x_reg = list(range(min_day, max_day + 1, step))
    y_reg = [m * day + b for day in x_reg]
    x_reg_str = [datetime.fromordinal(day).strftime('%Y-%m-%d') for day in x_reg]

    regression_trace = {
        'x': x_reg_str,
        'y': y_reg,
        'mode': 'lines',
        'line': {'color': 'red', 'dash': 'dot'},
        'name': 'Línea de Regresión'
    }

    return [points_trace, regression_trace]




@app.route('/')
@login_required
def index():
    # Cantidades totales
    total_products = Product.query.count()
    total_stores = Store.query.count()
    total_prices = Price.query.count()

    # Fechas de inicio/fin para el gráfico
    start_date = datetime(2023, 1, 1)
    end_date = datetime.utcnow()

    # PRODUCTO 1 (ID=1)
    product1_id = 1
    product1_obj = Product.query.get(product1_id)
    dataProducto1 = obtener_datos_grafico(product1_id, start_date, end_date)

    # PRODUCTO 2 (ID=6)
    product2_id = 6
    product2_obj = Product.query.get(product2_id)
    dataProducto2 = obtener_datos_grafico(product2_id, start_date, end_date)

    # Construir títulos con marca y presentación
    def build_title(product_obj):
        if not product_obj:
            return "Producto sin datos"
        # Manejo simple si alguno de los campos es None o cadena vacía
        brand_part = product_obj.brand if product_obj.brand else "Sin marca"
        pres_part = product_obj.presentation if product_obj.presentation else "Sin presentación"
        return f"{product_obj.name} ({brand_part}, {pres_part})"

    product1_title = build_title(product1_obj)
    product2_title = build_title(product2_obj)

    return render_template(
        'index.html',
        total_products=total_products,
        total_stores=total_stores,
        total_prices=total_prices,
        dataProducto1=dataProducto1,
        dataProducto2=dataProducto2,
        product1_title=product1_title,
        product2_title=product2_title
    )






@app.route('/api/dashboard_chart_data')
@login_required
def dashboard_chart_data():
    """
    Endpoint opcional que devuelve datos de precios en JSON para un producto específico,
    entre 01/01/2023 y hoy. Se llama con ?product=NombreProducto.
    Ejemplo de uso: /api/dashboard_chart_data?product=Atun%20en%20Agua
    """
    product_name = request.args.get('product', '').strip()
    if not product_name:
        return jsonify({"error": "Falta el parámetro 'product'"}), 400

    start_date = datetime(2023, 1, 1)
    end_date = datetime.utcnow()

    # Buscamos el producto por nombre
    product = Product.query.filter_by(name=product_name).first()
    if not product:
        return jsonify({"error": f"No se encontró el producto {product_name}"}), 404

    # Obtenemos precios del producto en ese rango de fechas
    prices = (
        db.session.query(Price.date, Price.price)
        .filter(Price.product_id == product.id)
        .filter(Price.date >= start_date, Price.date <= end_date)
        .order_by(Price.date)
        .all()
    )
    if not prices:
        return jsonify({"error": f"No hay precios para {product_name} en este rango de fechas."}), 404

    # Convertimos a formato JSON: 
    dates = [row.date.strftime('%Y-%m-%d') for row in prices]
    values = [float(row.price) for row in prices]

    data_series = [{
        "label": product_name,
        "dates": dates,
        "prices": values
    }]

    return jsonify({
        "title": f"Evolución de precios: {product_name}",
        "data": data_series
    })


@app.template_filter('format_number')
def format_number(value):
    """
    Convierte el número en entero sin decimales y con '.' como separador de miles.
    Ej: 2084 => "2.084"
    """
    try:
        # Conviértelo a int redondeando si es necesario
        valor_int = round(float(value))
        # Usa formato con coma como separador de miles
        formateado = "{:,}".format(valor_int)
        # Reemplaza la coma por punto
        return formateado.replace(",", ".")
    except Exception:
        return value



@app.route('/stores', methods=['GET', 'POST'])
@login_required
@registro_required
def stores():
    """
    Muestra un formulario para agregar una nueva tienda.
    Si se envía POST, crea la tienda y redirige a la misma página
    (o donde quieras).
    """
    if request.method == 'POST':
        name = request.form['name'].strip()
        address = request.form['address'].strip()

        existing_store = Store.query.filter_by(name=name).first()
        if existing_store:
            flash('La tienda con ese nombre ya existe.', 'danger')
            return redirect(url_for('stores'))

        new_store = Store(name=name, address=address)
        db.session.add(new_store)
        try:
            db.session.commit()
            flash('Tienda agregada exitosamente.', 'success')
        except IntegrityError:
            db.session.rollback()
            flash('Ocurrió un error al intentar agregar la tienda.', 'danger')

        return redirect(url_for('stores'))  # recarga el formulario
    
    # GET: solo muestra el formulario (sin tabla)
    return render_template('add_store.html')



@app.route('/add_product', methods=['GET', 'POST'])
@login_required
@registro_required
def add_product():
    if request.method == 'POST':
        try:
            name = request.form['name'].strip()
            brand = request.form['brand'].strip()
            presentation = request.form['presentation'].strip()
            distributor = request.form['distributor'].strip()
            if not name or not brand or not presentation:
                raise ValueError("Todos los campos marcados son requeridos.")
            existing_product = Product.query.filter_by(name=name, brand=brand, presentation=presentation).first()
            if existing_product:
                raise ValueError(f"Ya existe un producto '{name}' con la marca '{brand}' y presentación '{presentation}'.")
            new_product = Product(name=name, brand=brand, presentation=presentation, distributor=distributor)
            db.session.add(new_product)
            db.session.commit()
            flash('Producto agregado exitosamente', 'success')
            return redirect(url_for('products'))
        except ValueError as ve:
            flash(str(ve), 'error')
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al agregar producto: {str(e)}")
            flash('Error al agregar el producto', 'error')
    products = Product.query.order_by(Product.name).all()
    return render_template('add_product.html', products=products)

@app.route('/products', methods=['GET', 'POST'])
@login_required
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
@login_required
def export_products():
    products_data = Product.query.all()
    csv_data = 'ID,Nombre,Marca,Presentación,Distribuidor\n'
    for product in products_data:
        csv_data += (f"{product.id},{product.name},{product.brand},{product.presentation},{product.distributor}\n")
    response = make_response(csv_data)
    response.headers['Content-Disposition'] = 'attachment; filename=products.csv'
    response.mimetype = 'text/csv'
    return response

@app.route('/add_price', methods=['GET', 'POST'])
@login_required
@registro_required
def add_price():
    form = PriceForm()
    # Obtenemos todos los productos para las sugerencias en el datalist
    products = Product.query.order_by(Product.name).all()
    # Configuramos las opciones para las tiendas
    form.store.choices = [(st.id, st.name) for st in Store.query.order_by(Store.name).all()]
    # Las marcas se dejan en blanco, a completar por el usuario
    form.brand.choices = [('', 'Seleccione una marca')]
    
    if form.validate_on_submit():
        try:
            product_name = form.product.data.strip()
            brand = form.brand.data.strip()
            store_id = form.store.data
            # Se obtiene el valor del campo presentación desde el formulario (campo extra en la plantilla)
            presentation = request.form.get('presentation', '').strip()
            price_value = form.price.data
            date_value = form.date.data  # Ya es un objeto date, con valor por defecto hoy

            # Validar que todos los campos tengan valor
            if not all([product_name, brand, store_id, presentation, price_value, date_value]):
                flash('Todos los campos son requeridos.')
                return render_template('add_price.html', form=form, products=products)
            
            # Buscamos el producto por nombre
            product = Product.query.filter_by(name=product_name).first()
            if not product:
                flash('Producto no encontrado.')
                return render_template('add_price.html', form=form, products=products)
            
            new_price = Price(
                product_id=product.id,
                brand=brand,
                store_id=int(store_id),
                presentation=presentation,
                price=float(price_value),
                date=date_value
            )
            db.session.add(new_price)
            db.session.commit()
            flash('Precio agregado exitosamente.')
            return redirect(url_for('prices'))
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al agregar precio: {str(e)}")
            flash('Error al agregar el precio. Por favor, intente nuevamente.')
            return render_template('add_price.html', form=form, products=products)
    
    return render_template('add_price.html', form=form, products=products)



@app.route('/admin/upload_prices', methods=['GET', 'POST'])
@login_required
@registro_required
def upload_prices():
    if request.method == 'POST':
        file = request.files.get('csv_file')
        if not file:
            flash('No se seleccionó ningún archivo.', 'error')
            return redirect(request.url)
        try:
            stream = StringIO(file.stream.read().decode('utf-8'))
            csv_reader = csv.DictReader(stream)
            count = 0
            errores = []
            BATCH_SIZE = 200
            for index, row in enumerate(csv_reader):
                nombre = row.get('nombre')
                marca = row.get('marca')
                presentacion = row.get('presentacion')
                tienda = row.get('tienda')
                precio_str = row.get('precio')
                fecha_str = row.get('ultima_actualizacion')
                if not all([nombre, marca, presentacion, tienda, precio_str, fecha_str]):
                    errores.append("Faltan datos en alguna fila.")
                    continue
                product = Product.query.filter(
                    func.lower(Product.name) == nombre.lower().strip(),
                    func.lower(Product.brand) == marca.lower().strip(),
                    func.lower(Product.presentation) == presentacion.lower().strip()
                ).first()
                if not product:
                    product = Product(name=nombre.strip(), brand=marca.strip(),
                                      presentation=presentacion.strip(), distributor="")
                    db.session.add(product)
                    db.session.flush()
                    flash(f"Producto creado: {nombre} - {marca} - {presentacion}", 'info')
                store = Store.query.filter(func.lower(Store.name) == tienda.lower().strip()).first()
                if not store:
                    store = Store(name=tienda.strip(), address="")
                    db.session.add(store)
                    db.session.flush()
                    flash(f"Tienda creada: {tienda}", 'info')
                try:
                    price_value = float(precio_str)
                except ValueError:
                    errores.append(f"Precio inválido para {nombre} en {tienda}: {precio_str}")
                    continue
                try:
                    date_value = datetime.strptime(fecha_str.strip(), '%d %b %Y')
                except ValueError:
                    errores.append(f"Fecha inválida para {nombre} en {tienda}: {fecha_str}")
                    continue
                new_price = Price(product_id=product.id, brand=marca.strip(), store_id=store.id,
                                  presentation=presentacion.strip(), price=price_value, date=date_value)
                db.session.add(new_price)
                count += 1
                if (index + 1) % BATCH_SIZE == 0:
                    db.session.commit()
                    db.session.expunge_all()
            db.session.commit()
            mensaje = f"Se han registrado {count} precios."
            if errores:
                mensaje += " Se presentaron algunos errores: " + "; ".join(errores)
                flash(mensaje, 'warning')
            else:
                flash(mensaje, 'success')
            return redirect(url_for('prices'))
        except Exception as e:
            db.session.rollback()
            flash(f"Error al procesar el archivo CSV: {str(e)}", 'error')
            return redirect(request.url)
    return render_template('admin/upload_prices.html')

@app.route('/get_product_details/<string:product_name>')
@login_required
def get_product_details(product_name):
    # Obtener marcas y presentaciones tanto de la tabla Product como de Price
    product_data = db.session.query(Product.brand, Product.presentation)\
        .filter(Product.name == product_name)\
        .distinct()\
        .all()
    
    price_data = db.session.query(Price.brand, Price.presentation)\
        .join(Product)\
        .filter(Product.name == product_name)\
        .distinct()\
        .all()
    
    # Combinar los datos en una estructura jerárquica
    brand_presentation_map = {}
    
    # Agregar datos de la tabla Product
    for brand, presentation in product_data:
        if brand and brand.strip():  # Verificar que la marca no esté vacía
            if brand not in brand_presentation_map:
                brand_presentation_map[brand] = set()
            if presentation and presentation.strip():
                brand_presentation_map[brand].add(presentation)
    
    # Agregar datos de la tabla Price
    for brand, presentation in price_data:
        if brand and brand.strip():
            if brand not in brand_presentation_map:
                brand_presentation_map[brand] = set()
            if presentation and presentation.strip():
                brand_presentation_map[brand].add(presentation)
    
    # Verificar si hay datos en el producto base
    product = Product.query.filter_by(name=product_name).first()
    if product and product.brand and product.brand.strip():
        if product.brand not in brand_presentation_map:
            brand_presentation_map[product.brand] = set()
        if product.presentation and product.presentation.strip():
            brand_presentation_map[product.brand].add(product.presentation)
    
    # Convertir a formato para JSON
    result = {
        'brands': sorted(brand_presentation_map.keys()),
        'presentationsByBrand': {
            brand: sorted(list(presentations))
            for brand, presentations in brand_presentation_map.items()
        }
    }
    
    # Agregar log para depuración
    app.logger.info(f"Product details for {product_name}: {result}")
    
    return jsonify(result)

@app.route('/add_price_form', methods=['GET'])
@login_required
@registro_required
def show_add_price_form():
    form = PriceForm()
    form.product.choices = [(prod.id, prod.name) for prod in Product.query.all()]
    form.store.choices = [(st.id, st.name) for st in Store.query.all()]
    brands = db.session.query(Product.brand).distinct().all()
    brand_choices = [(b[0], b[0]) for b in brands if b[0]]
    form.brand.choices = brand_choices
    return render_template('add_price.html', form=form)

@app.route('/prices', methods=['GET', 'POST'])
@login_required
@registro_required
def prices():
    if request.method == 'POST':
        try:
            # Recoger datos del formulario
            product_id = request.form['product_id']
            store_id = request.form['store_id']
            price_value = float(request.form['price'])
            date_value = request.form['date']

            new_price = Price(
                product_id=product_id,
                store_id=store_id,
                price=price_value,
                date=datetime.strptime(date_value, '%Y-%m-%d')
            )
            db.session.add(new_price)
            db.session.commit()
            flash('Precio agregado exitosamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error al agregar precio: {str(e)}', 'danger')
        return redirect(url_for('prices'))

    # GET: Mostrar solo el formulario para agregar precios
    products = Product.query.order_by(Product.name).all()
    stores = Store.query.order_by(Store.name).all()
    return render_template('add_price.html', products=products, stores=stores)


@app.route('/edit_price/<int:price_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_price(price_id):
    price = Price.query.get_or_404(price_id)
    form = PriceForm()

    # Configurar las opciones del formulario
    form.product.choices = [(p.name, p.name) for p in Product.query.order_by(Product.name).distinct()]
    form.store.choices = [(st.id, st.name) for st in Store.query.order_by(Store.name).all()]
    form.brand.choices = [(price.brand, price.brand)]  # Solo la marca actual
    
    # En el método GET, poblamos el formulario con los datos existentes
    if request.method == 'GET':
        form.product.data = price.product.name
        form.store.data = price.store_id
        form.brand.data = price.brand
        form.price.data = price.price
        form.date.data = price.date

    # En el método POST, procesamos la actualización
    if form.validate_on_submit():
        try:
            # Obtener el producto por nombre
            product = Product.query.filter_by(name=form.product.data).first()
            if not product:
                flash('Producto no encontrado')
                return redirect(url_for('prices'))

            # Actualizar los campos
            price.product_id = product.id
            price.store_id = form.store.data
            price.brand = form.brand.data
            price.price = form.price.data
            price.date = form.date.data
            # La presentación se mantiene sin cambios

            db.session.commit()
            flash('Precio actualizado exitosamente')
            return redirect(url_for('prices'))
            
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error al actualizar precio: {str(e)}")
            flash(f'Error al actualizar el precio: {str(e)}')
            return redirect(url_for('edit_price', price_id=price_id))

    return render_template('edit_price.html', form=form, price=price)

@app.route('/delete_price/<int:price_id>', methods=['POST'])
@login_required
@admin_required
def delete_price(price_id):
    try:
        price = Price.query.get_or_404(price_id)
        db.session.delete(price)
        db.session.commit()
        flash('Precio eliminado exitosamente', 'success')
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error al eliminar precio: {str(e)}")
        flash('Error al eliminar el precio', 'error')
    
    return redirect(url_for('prices'))

@app.route('/export_prices')
@login_required
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
# NUEVA IMPLEMENTACIÓN: Búsqueda dinámica de productos para autocompletar
# ----------------------------------------------------------------
@app.route('/get_product_filters', methods=['GET'])
@login_required
def get_product_filters():
    product_name = request.args.get('product_name', '').strip()
    if not product_name:
        return jsonify({"brands": [], "presentations": []})
    
    # Buscar el producto de forma insensible a mayúsculas
    product = Product.query.filter(func.lower(Product.name) == product_name.lower()).first()
    if not product:
        return jsonify({"brands": [], "presentations": []})
    
    # Filtrar las marcas y presentaciones asociadas al producto usando su ID
    distinct_brands = (
        db.session.query(Price.brand)
        .filter(Price.product_id == product.id, Price.brand.isnot(None))
        .distinct()
        .all()
    )
    distinct_presentations = (
        db.session.query(Price.presentation)
        .filter(Price.product_id == product.id, Price.presentation.isnot(None))
        .distinct()
        .all()
    )

    brand_list = [b[0] for b in distinct_brands]
    presentation_list = [p[0] for p in distinct_presentations]

    return jsonify({
        "brands": brand_list,
        "presentations": presentation_list
    })

@app.route('/search_products', methods=['GET'])
@login_required
def search_products():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    # Filtrar productos
    results = Product.query.filter(Product.name.ilike(f'%{q}%')).limit(10).all()
    product_names = [p.name for p in results]
    return jsonify(product_names)

def linear_regression(x_vals, y_vals):
    """
    Calcula la regresión lineal simple (y = m*x + b)
    a partir de listas de valores numéricos.
    """
    n = len(x_vals)
    if n == 0:
        return None, None
    mean_x = sum(x_vals) / n
    mean_y = sum(y_vals) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(x_vals, y_vals))
    den = sum((x - mean_x) ** 2 for x in x_vals)
    if den == 0:
        # Evita dividir por cero si todos los x son iguales
        return 0, mean_y
    m = num / den
    b = mean_y - m * mean_x
    return m, b

@app.route('/generate_graph', methods=['GET', 'POST'])
@login_required
def generate_graph():
    if request.method == 'GET':
        products = [p.name for p in Product.query.order_by(Product.name).distinct().all()]
        stores = Store.query.order_by(Store.name).all()
        all_brands = [b[0] for b in db.session.query(Price.brand)
                                     .distinct()
                                     .filter(Price.brand.isnot(None))
                                     .all()]
        all_presentations = [p[0] for p in db.session.query(Price.presentation)
                                         .distinct()
                                         .filter(Price.presentation.isnot(None))
                                         .all()]
        return render_template('generate_graph.html',
                               products=products,
                               stores=stores,
                               all_brands=all_brands,
                               all_presentations=all_presentations)

    try:
        # Recoger datos del formulario (marcas y tiendas como listas)
        form_data = {
            'start_date': request.form.get('start_date'),
            'end_date': request.form.get('end_date'),
            'product_name': request.form.get('product_name'),
            'brand': request.form.getlist('brand[]'),
            'store': request.form.getlist('store[]'),
            'presentation': request.form.get('presentation')
        }

        # Validar fechas requeridas
        for field in ['start_date', 'end_date']:
            if not form_data[field]:
                raise ValueError(f"Campo requerido faltante: {field}")

        # Construir la query base
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
            .filter(Price.date.between(form_data['start_date'], form_data['end_date']))
        )

        # Filtros
        if form_data['product_name'] and form_data['product_name'] != 'all':
            query = query.filter(Product.name == form_data['product_name'])
        if form_data['brand'] and 'all' not in form_data['brand']:
            query = query.filter(Price.brand.in_(form_data['brand']))
        if form_data['store'] and 'all' not in form_data['store']:
            query = query.filter(Store.id.in_(form_data['store']))
        if form_data['presentation'] and form_data['presentation'] != 'all':
            query = query.filter(Price.presentation == form_data['presentation'])

        # Ordenar y ejecutar
        query = query.order_by(Price.date)
        results = query.all()

        if not results:
            return jsonify({'error': 'No se encontraron datos con estos filtros'}), 404

        # Agrupar resultados en series
        grouped_data = {}
        for row in results:
            # Si hay una única marca distinta de "all", agrupamos solo por tienda.
            # De lo contrario, agrupamos por tienda + marca.
            if len(form_data['brand']) == 1 and form_data['brand'][0] != 'all':
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

        # --- Cálculo de la línea de regresión ---
        # Recopilar TODOS los puntos para la regresión
        all_date_nums = []
        all_prices = []
        for series in data_series:
            for d_str, price in zip(series['dates'], series['prices']):
                dt = datetime.strptime(d_str, '%Y-%m-%d')
                day_num = dt.toordinal()  # convierte fecha a un número de días
                all_date_nums.append(day_num)
                all_prices.append(price)

        m, b = linear_regression(all_date_nums, all_prices)
        if m is not None:
            # Generar puntos para la línea punteada
            min_day = min(all_date_nums)
            max_day = max(all_date_nums)
            num_points = 50  # para suavizar la línea
            step = max(1, (max_day - min_day) // num_points)
            regression_dates = []
            regression_prices = []
            for day in range(min_day, max_day + 1, step):
                regression_dates.append(datetime.fromordinal(day).strftime('%Y-%m-%d'))
                regression_prices.append(m * day + b)
            
            # Aquí indicamos las propiedades para que sea roja, punteada y de grosor 3
            regression_trace = {
                'label': 'Línea de regresión',
                'dates': regression_dates,
                'prices': regression_prices,
                'mode': 'lines',
                'line': {
                    'color': 'red',
                    'dash': 'dot',  # punteada
                    'width': 5
                }
            }
            data_series.append(regression_trace)
        # --- Fin línea de regresión ---

        # Título
        producto = form_data['product_name'] if form_data['product_name'] != 'all' else 'Todos los productos'
        if form_data['brand'] and 'all' not in form_data['brand']:
            marca = ", ".join(form_data['brand'])
        else:
            marca = "Todas las marcas"
        presentacion = form_data['presentation'] if form_data['presentation'] != 'all' else 'Todas las presentaciones'
        titulo = f"{producto} | {marca} | {presentacion}"

        plot_data = {'title': titulo, 'data': data_series}
        return jsonify(plot_data)

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Error en /generate_graph: {e}")
        return jsonify({'error': 'Error al generar el gráfico'}), 500




@app.route('/get_brands_for_product', methods=['GET'])
@login_required
def get_brands_for_product():
    product_name = request.args.get('product_name', '').strip()
    if not product_name:
        return jsonify({"brands": [], "presentations": []})
    product = Product.query.filter(func.lower(Product.name) == product_name.lower()).first()
    if not product:
        return jsonify({"brands": [], "presentations": []})
    distinct_brands = (
        db.session.query(Price.brand)
        .filter(Price.product_id == product.id, Price.brand.isnot(None))
        .distinct()
        .all()
    )
    distinct_presentations = (
        db.session.query(Price.presentation)
        .filter(Price.product_id == product.id, Price.presentation.isnot(None))
        .distinct()
        .all()
    )
    brand_list = sorted([b[0] for b in distinct_brands])
    presentation_list = sorted([p[0] for p in distinct_presentations])
    return jsonify({"brands": brand_list, "presentations": presentation_list})


@app.route('/get_presentations', methods=['GET'])
@login_required
def get_presentations():
    product_name = request.args.get('product_name', '').strip()
    # Para marcas, puede venir el parámetro 'brand' o 'brands'
    brand_param = request.args.get('brand', '').strip()
    brands_param = request.args.get('brands', '').strip()  # se espera una cadena separada por comas
    if not product_name:
        return jsonify({"presentations": []})
    product = Product.query.filter(func.lower(Product.name) == product_name.lower()).first()
    if not product:
        return jsonify({"presentations": []})
    # Si se reciben múltiples marcas, las separamos
    if brands_param:
        brands = [b.strip() for b in brands_param.split(',') if b.strip()]
        filter_condition = Price.brand.in_(brands)
    elif brand_param:
        filter_condition = (Price.brand == brand_param)
    else:
        filter_condition = True  # sin filtro por marca
    distinct_presentations = (
        db.session.query(Price.presentation)
        .filter(Price.product_id == product.id, filter_condition, Price.presentation.isnot(None))
        .distinct()
        .all()
    )
    presentation_list = sorted([p[0] for p in distinct_presentations])
    return jsonify({"presentations": presentation_list})



@app.route('/show_graph')
@login_required
def show_graph():
    form_data = {
        "start_date": "2023-01-01",
        "end_date": "2025-01-31",
        "product_name": "Deviled Ham",
        "brand": "Underwood",
        "store": "all",
        "presentation": "120 g"
    }
    base_query = build_base_query(form_data)
    legend_group, legend_key = determine_legend_grouping(form_data, base_query)
    data_series = build_data_series(base_query, legend_group, legend_key)
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

def build_base_query(form_data):
    product = Product.query.filter_by(name=form_data['product_name']).first()
    if not product:
        raise ValueError("Producto no encontrado.")
    query = Price.query.filter(
        Price.product_id == product.id,
        Price.date.between(form_data['start_date'], form_data['end_date'])
    )
    if form_data['presentation'] != 'all':
        query = query.filter(Price.presentation == form_data['presentation'])
    if form_data['store'] != "all":
        store_id = int(form_data['store'])
        query = query.filter(Price.store_id == store_id)
    if form_data['brand'] != "all":
        query = query.filter(Price.brand == form_data['brand'])
    return query

def determine_legend_grouping(form_data, query):
    if form_data['store'] == "all" and form_data['brand'] == "all":
        distinct_brands = query.with_entities(Price.brand).distinct().all()
        return distinct_brands, 'brand'
    elif form_data['brand'] != "all":
        distinct_stores = query.with_entities(Price.store_id).distinct().all()
        return distinct_stores, 'store_id'
    else:
        distinct_brands = query.with_entities(Price.brand).distinct().all()
        return distinct_brands, 'brand'

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
            store = Store.query.get(key_value)
            label = store.name if store else 'Desconocido'
        data_series.append({'label': label, 'dates': dates, 'prices': prices})
    return data_series

@app.route('/reports')
@login_required
def reports_index():
    """
    Muestra la página principal de reportes, con enlaces a cada reporte disponible.
    """
    return render_template('reports_index.html')

@app.route('/reports/products')
@login_required
def reports_products():
    products = Product.query.order_by(Product.id).all()
    return render_template('report_products.html', products=products)

@app.route('/reports/stores', methods=['GET'])
@login_required
def reports_stores():
    """
    Muestra la tabla con todas las tiendas (reporte).
    """
    stores_data = Store.query.order_by(Store.id).all()
    return render_template('report_stores.html', stores=stores_data)


@app.route('/reports/prices', methods=['GET'])
@login_required
def reports_prices():
    prices_list = Price.query.order_by(Price.date.desc()).all()
    return render_template('report_prices.html', prices=prices_list)





@app.context_processor
def inject_current_year():
    return {'current_year': datetime.utcnow().year}


if __name__ == '__main__':
    app.run(debug=True)

