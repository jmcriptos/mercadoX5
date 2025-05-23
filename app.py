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
import io
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

@app.template_filter('format_number')
def format_number(value):
    try:
        valor_int = round(float(value))
        formateado = "{:,}".format(valor_int)
        return formateado.replace(",", ".")
    except Exception:
        return value
@app.template_filter('strftime')
def strftime_filter(value, date_format="%Y-%m-%d"):
    """
    Convierte un objeto datetime (o date) a cadena según el formato especificado.
    Por defecto, %Y-%m-%d => '2025-02-16'
    """
    try:
        return value.strftime(date_format)
    except Exception:
        # En caso de que 'value' no sea una fecha válida
        return value
# ----------------------------------------------------------------
# CONFIGURACIÓN DE FLASK-LOGIN
# ----------------------------------------------------------------
login = LoginManager(app)
login.login_view = 'auth'

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


@app.route('/admin/upload_prices', methods=['GET', 'POST'])
@login_required
@admin_required
def upload_prices():
    if request.method == 'POST':
        file = request.files.get('file')
        if not file:
            flash('No se ha seleccionado ningún archivo.', 'danger')
            return redirect(url_for('upload_prices'))
        try:
            # Leer el contenido del archivo CSV
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_input = csv.DictReader(stream)
            count = 0  # Contador de registros insertados

            for row in csv_input:
                # Extraer y limpiar los datos de cada fila
                product_name = row.get("nombre", "").strip()
                brand = row.get("marca", "").strip()
                store_name = row.get("tienda", "").strip()
                presentation = row.get("presentacion", "").strip()
                price_value = row.get("precio", "").strip()
                date_str = row.get("ultima_actualizacion", "").strip()

                # Verificar que todos los campos requeridos estén presentes
                if not all([product_name, brand, store_name, presentation, price_value, date_str]):
                    app.logger.error(f"Campos incompletos en la fila: {row}")
                    continue

                # Buscar el producto en la base de datos (ignorar mayúsculas/minúsculas)
                product = Product.query.filter(func.lower(Product.name) == product_name.lower()).first()
                if not product:
                    # Si el producto no existe, crearlo
                    product = Product(name=product_name, brand=brand, presentation=presentation)
                    db.session.add(product)
                    try:
                        db.session.commit()  # Confirmar para obtener el ID del nuevo producto
                    except Exception as e:
                        app.logger.error(f"Error al crear producto '{product_name}': {e}")
                        db.session.rollback()
                        continue

                # Buscar la tienda en la base de datos
                store = Store.query.filter(func.lower(Store.name) == store_name.lower()).first()
                if not store:
                    app.logger.error(f"Tienda no encontrada: '{store_name}'")
                    continue

                try:
                    # Convertir el precio a float y la fecha al formato datetime
                    price_value = float(price_value)
                    date_value = datetime.strptime(date_str, '%d %b %Y')
                except Exception as e:
                    app.logger.error(f"Error al convertir datos en la fila {row}: {e}")
                    continue

                # Crear el registro de Price
                new_price = Price(
                    product_id=product.id,
                    brand=brand,
                    store_id=store.id,
                    presentation=presentation,
                    price=price_value,
                    date=date_value
                )
                db.session.add(new_price)
                count += 1

            db.session.commit()
            flash(f'Precios subidos exitosamente. Total de registros insertados: {count}', 'success')
            # Redirigir al dashboard
            return redirect(url_for('index'))

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error al procesar el CSV: {e}")
            flash(f'Error al procesar el archivo: {str(e)}', 'danger')
            return redirect(url_for('upload_prices'))

    # GET: Renderizar el formulario para subir el archivo CSV
    return render_template('admin/upload_prices.html')




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
@app.route('/auth', methods=['GET', 'POST'])
def auth():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    # Instanciamos ambos formularios con prefijos para diferenciarlos
    login_form = LoginForm(prefix="login")
    register_form = RegistrationForm(prefix="register")
    
    if request.method == "POST":
        # Procesamos el formulario de inicio de sesión
        if login_form.submit.data and login_form.validate_on_submit():
            user = User.query.filter_by(username=login_form.username.data).first()
            if user is None or not user.check_password(login_form.password.data):
                flash("Nombre de usuario o contraseña incorrectos.", "danger")
            else:
                login_user(user, remember=login_form.remember_me.data)
                flash("Has iniciado sesión correctamente.", "success")
                return redirect(url_for('index'))
        
        # Procesamos el formulario de registro
        elif register_form.submit.data and register_form.validate_on_submit():
            existing_user = User.query.filter(
                (User.username == register_form.username.data) | 
                (User.email == register_form.email.data)
            ).first()
            if existing_user:
                if existing_user.username == register_form.username.data:
                    flash("El nombre de usuario ya está en uso.", "danger")
                else:
                    flash("El correo electrónico ya está en uso.", "danger")
            else:
                new_user = User(
                    username=register_form.username.data,
                    email=register_form.email.data,
                    role=UserRole.CONSULTA.value
                )
                new_user.set_password(register_form.password.data)
                db.session.add(new_user)
                db.session.commit()
                flash("Te has registrado exitosamente. Ahora puedes iniciar sesión.", "success")
                # Opcional: redirigir al login o mantener la pestaña de registro
                return redirect(url_for('auth'))
    
    return render_template('auth.html', login_form=login_form, register_form=register_form)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión.')
    return redirect(url_for('auth'))


# ----------------------------------------------------------------
# RUTAS PROTEGIDAS
# ----------------------------------------------------------------
# Ruta para listar y editar precios (opción "Editar Precio")
@app.route('/admin/delete_prices', methods=['GET'])
@admin_required
def delete_price_list():
    page = request.args.get('page', 1, type=int)
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str   = request.args.get('end_date', '').strip()
    product_name   = request.args.get('product', '').strip()
    brand_name     = request.args.get('brand', '').strip()

    # Construimos la query base
    query = Price.query.join(Product).join(Store)

    # Filtro de fechas
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(Price.date >= start_date)
        except ValueError:
            pass
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            end_date = end_date.replace(hour=23, minute=59, second=59)
            query = query.filter(Price.date <= end_date)
        except ValueError:
            pass

    # Filtro de producto
    if product_name:
        query = query.filter(Product.name.ilike(f'%{product_name}%'))

    # Filtro de marca
    if brand_name:
        query = query.filter(Price.brand.ilike(f'%{brand_name}%'))

    # Ordenar por fecha descendente (o como gustes)
    query = query.order_by(Price.date.desc())

    # Paginación
    prices_pag = query.paginate(page=page, per_page=10)

    # Para Awesomplete: listas de productos y marcas
    all_products = db.session.query(Product.name).distinct().order_by(Product.name).all()
    product_names = sorted({p[0] for p in all_products if p[0]})
    all_brands = db.session.query(Price.brand).distinct().order_by(Price.brand).all()
    brand_names = sorted({b[0] for b in all_brands if b[0]})

    return render_template(
        'admin/delete_price_list.html',
        prices=prices_pag,
        product_names=product_names,
        brand_names=brand_names
    )


@app.route('/admin/delete_price/<int:price_id>', methods=['POST'])
@admin_required
def delete_price_item(price_id):
    """Elimina un precio específico."""
    price = Price.query.get_or_404(price_id)
    db.session.delete(price)
    db.session.commit()
    flash('Precio eliminado exitosamente.', 'success')
    return redirect(url_for('delete_price_list'))

@app.route('/admin/delete_products', methods=['GET'])
@admin_required
def delete_product_list():
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    query = Product.query
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    products_pag = query.order_by(Product.name).paginate(page=page, per_page=10)
    # product_names para Awesomplete (eliminando duplicados)
    product_names_raw = [p.name for p in Product.query.order_by(Product.name).all()]
    product_names = sorted(set(product_names_raw))
    return render_template('admin/delete_product_list.html', products=products_pag, product_names=product_names)


@app.route('/admin/delete_product/<int:product_id>', methods=['POST'])
@admin_required
def admin_delete_product(product_id):
    try:
        product = Product.query.get_or_404(product_id)
        db.session.delete(product)
        db.session.commit()
        flash('Producto eliminado exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al eliminar producto: {str(e)}")
        flash('Error al eliminar el producto.', 'danger')
    return redirect(url_for('delete_product_list'))

@app.route('/admin/delete_stores', methods=['GET'])
@admin_required
def delete_store_list():
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    
    query = Store.query
    if search:
        query = query.filter(
            Store.name.ilike(f'%{search}%') |
            Store.address.ilike(f'%{search}%')
        )
    
    # Paginamos, por ejemplo 10 por página
    stores_pag = query.order_by(Store.id).paginate(page=page, per_page=10)
    
    # Para Awesomplete (si quieres autocompletado)
    store_names = [s.name for s in Store.query.order_by(Store.name).all()]
    
    return render_template(
        'admin/delete_store_list.html',
        stores=stores_pag,
        store_names=store_names
    )

@app.route('/admin/delete_store/<int:store_id>', methods=['POST'])
@admin_required
def admin_delete_store(store_id):
    try:
        store = Store.query.get_or_404(store_id)
        db.session.delete(store)
        db.session.commit()
        flash('Tienda eliminada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error al eliminar tienda: {str(e)}")
        flash('Error al eliminar la tienda.', 'danger')
    return redirect(url_for('delete_store_list'))


@app.errorhandler(403)
def forbidden_error(error):
    return render_template('403.html'), 403

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
        return 0, mean_y
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

    m, b = linear_regression([dt.toordinal() for dt in x_vals], y_vals)
    if m is None:
        return [points_trace]

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
    total_products = Product.query.count()
    total_stores = Store.query.count()
    total_prices = Price.query.count()

    start_date = datetime(2023, 1, 1)
    end_date = datetime.utcnow()

    product1_id = 1
    product1_obj = Product.query.get(product1_id)
    dataProducto1 = obtener_datos_grafico(product1_id, start_date, end_date)

    product2_id = 6
    product2_obj = Product.query.get(product2_id)
    dataProducto2 = obtener_datos_grafico(product2_id, start_date, end_date)

    def build_title(product_obj):
        if not product_obj:
            return "Producto sin datos"
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
    product_name = request.args.get('product', '').strip()
    if not product_name:
        return jsonify({"error": "Falta el parámetro 'product'"}), 400

    start_date = datetime(2023, 1, 1)
    end_date = datetime.utcnow()

    product = Product.query.filter_by(name=product_name).first()
    if not product:
        return jsonify({"error": f"No se encontró el producto {product_name}"}), 404

    prices = (
        db.session.query(Price.date, Price.price)
        .filter(Price.product_id == product.id)
        .filter(Price.date >= start_date, Price.date <= end_date)
        .order_by(Price.date)
        .all()
    )
    if not prices:
        return jsonify({"error": f"No hay precios para {product_name} en este rango de fechas."}), 404

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

@app.route('/stores', methods=['GET', 'POST'])
@login_required
@registro_required
def stores():
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
        # Redirect to the dashboard (index) after successful addition
        return redirect(url_for('index'))
    
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
            # Redirect to the dashboard (index) instead of the products list
            return redirect(url_for('index'))
        except ValueError as ve:
            flash(str(ve), 'danger')
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error al agregar producto: {str(e)}")
            flash('Error al agregar el producto', 'danger')
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
    
    # Obtener productos
    products_query = db.session.query(Product.name).distinct().order_by(Product.name).all()
    products = [row[0] for row in products_query]

    # Llenar choices de tiendas
    form.store.choices = [(st.id, st.name) for st in Store.query.order_by(Store.name).all()]

    if request.method == 'POST':
        # Si quieres ver qué datos llegan en el POST:
        # print("Form Data:", request.form)

        # Lógica para refrescar la lista de marcas si hay un producto
        product_name = request.form.get('product', '').strip()
        if product_name:
            product = Product.query.filter(func.lower(Product.name) == product_name.lower()).first()
            if product:
                distinct_brands = (
                    db.session.query(Price.brand)
                    .filter(Price.product_id == product.id, Price.brand.isnot(None))
                    .distinct()
                    .all()
                )
                brand_list = sorted([b[0] for b in distinct_brands])
                form.brand.choices = [('', 'Seleccione una marca')] + [(b, b) for b in brand_list]

        # Validar el formulario
        if not form.validate():
            flash('Error de validación. Por favor, verifique los campos.', 'danger')
            return render_template('add_price.html', form=form, products=products)

        try:
            product_name = form.product.data.strip()
            brand = form.brand.data.strip()
            store_id = form.store.data
            presentation = request.form.get('presentation', '').strip()
            price_value = form.price.data
            date_value = form.date.data

            if not all([product_name, brand, store_id, presentation, price_value, date_value]):
                flash('Todos los campos son requeridos.', 'warning')
                return render_template('add_price.html', form=form, products=products)

            # Verificar que el producto exista
            product = Product.query.filter(func.lower(Product.name) == product_name.lower()).first()
            if not product:
                flash('Producto no encontrado.', 'warning')
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

            # AQUÍ haces el flash y rediriges al Dashboard
            flash('Precio agregado exitosamente.', 'success')
            return redirect(url_for('index'))  # <--- Redirigir al Dashboard

        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error al agregar precio: {str(e)}")
            flash('Error al procesar el formulario. Por favor, intente nuevamente.', 'danger')
            return render_template('add_price.html', form=form, products=products)

    # GET: Renderizar el formulario vacío
    return render_template('add_price.html', form=form, products=products)



@app.route('/edit_price/<int:price_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_price(price_id):
    price = Price.query.get_or_404(price_id)
    form = PriceForm()
    form.product.choices = [(p.name, p.name) for p in Product.query.order_by(Product.name).distinct()]
    form.store.choices = [(st.id, st.name) for st in Store.query.order_by(Store.name).all()]
    form.brand.choices = [(price.brand, price.brand)]
    
    if request.method == 'GET':
        form.product.data = price.product.name
        form.store.data = price.store_id
        form.brand.data = price.brand
        form.price.data = price.price
        form.date.data = price.date

    if form.validate_on_submit():
        try:
            product = Product.query.filter_by(name=form.product.data).first()
            if not product:
                flash('Producto no encontrado')
                return redirect(url_for('prices'))
            price.product_id = product.id
            price.store_id = form.store.data
            price.brand = form.brand.data
            price.price = form.price.data
            price.date = form.date.data
            db.session.commit()
            flash('Precio actualizado exitosamente', 'success')
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

@app.route('/get_product_filters', methods=['GET'])
@login_required
def get_product_filters():
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

@app.route('/get_brands_for_product', methods=['GET'])
@login_required
def get_brands_for_product():
    """Obtiene las marcas vinculadas a un producto específico"""
    product_name = request.args.get('product_name', '').strip()
    if not product_name:
        return jsonify({"brands": []})
    
    # Buscar el producto
    product = Product.query.filter(func.lower(Product.name) == product_name.lower()).first()
    if not product:
        return jsonify({"brands": []})
    
    # Obtener marcas únicamente para este producto
    distinct_brands = (
        db.session.query(Price.brand)
        .filter(
            Price.product_id == product.id,
            Price.brand.isnot(None)
        )
        .distinct()
        .order_by(Price.brand)
        .all()
    )
    
    brand_list = sorted([b[0] for b in distinct_brands])
    return jsonify({"brands": brand_list})

@app.route('/get_presentations', methods=['GET'])
@login_required
def get_presentations():
    """Obtiene las presentaciones vinculadas a un producto y marca específicos"""
    product_name = request.args.get('product_name', '').strip()
    brand = request.args.get('brand', '').strip()
    
    if not product_name or not brand:
        return jsonify({"presentations": []})
    
    # Buscar el producto
    product = Product.query.filter(func.lower(Product.name) == product_name.lower()).first()
    if not product:
        return jsonify({"presentations": []})
    
    # Obtener presentaciones para este producto y marca específica
    distinct_presentations = (
        db.session.query(Price.presentation)
        .filter(
            Price.product_id == product.id,
            Price.brand == brand,
            Price.presentation.isnot(None)
        )
        .distinct()
        .order_by(Price.presentation)
        .all()
    )
    
    presentation_list = sorted([p[0] for p in distinct_presentations])
    return jsonify({"presentations": presentation_list})

@app.route('/search_products', methods=['GET'])
@login_required
def search_products():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify([])
    results = Product.query.filter(Product.name.ilike(f'%{q}%')).limit(10).all()
    product_names = [p.name for p in results]
    return jsonify(product_names)

@app.route('/generate_graph', methods=['GET', 'POST'])
@login_required
def generate_graph():
    """
    - GET: Renderiza la plantilla con el formulario (generate_graph.html).
    - POST: Aplica los filtros, obtiene datos, calcula estadísticas y devuelve JSON para Plotly.
    """
    if request.method == 'GET':
        # Listas para el formulario
        products = [p.name for p in Product.query.order_by(Product.name).distinct().all()]
        stores = Store.query.order_by(Store.name).all()
        all_brands = [
            b[0] for b in db.session.query(Price.brand)
                                    .distinct()
                                    .filter(Price.brand.isnot(None))
                                    .all()
        ]
        all_presentations = [
            p[0] for p in db.session.query(Price.presentation)
                                    .distinct()
                                    .filter(Price.presentation.isnot(None))
                                    .all()
        ]
        return render_template(
            'generate_graph.html',
            products=products,
            stores=stores,
            all_brands=all_brands,
            all_presentations=all_presentations
        )

    # Si el método es POST, procesamos los filtros
    try:
        form_data = {
            'start_date': request.form.get('start_date'),
            'end_date': request.form.get('end_date'),
            'product_name': request.form.get('product_name'),
            'brand': request.form.getlist('brand[]'),
            'store': request.form.getlist('store[]'),
            'presentation': request.form.get('presentation')
        }

        # Validación de fechas
        for field in ['start_date', 'end_date']:
            if not form_data[field]:
                raise ValueError(f"Falta el campo requerido: {field}")

        # Construimos la consulta
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

        # Filtros opcionales
        if form_data['product_name'] and form_data['product_name'] != 'all':
            query = query.filter(Product.name == form_data['product_name'])
        if form_data['brand'] and 'all' not in form_data['brand']:
            query = query.filter(Price.brand.in_(form_data['brand']))
        if form_data['store'] and 'all' not in form_data['store']:
            query = query.filter(Store.id.in_(form_data['store']))
        if form_data['presentation'] and form_data['presentation'] != 'all':
            query = query.filter(Price.presentation == form_data['presentation'])

        query = query.order_by(Price.date)
        results = query.all()

        if not results:
            return jsonify({'error': 'No se encontraron datos con estos filtros'}), 404

        # Agrupación de datos para las series (Plotly)
        grouped_data = {}
        for row in results:
            # Si se selecciona exactamente 1 marca distinta de 'all', agrupamos solo por tienda
            if len(form_data['brand']) == 1 and form_data['brand'][0] != 'all':
                key = row.store_name
                label = row.store_name
            else:
                # Agrupamos por tienda y marca
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

        # Para la regresión lineal y estadísticas globales
        all_date_nums = []
        all_prices = []

        # Variables para encontrar tienda con precio mínimo y máximo
        min_price_store = None
        max_price_store = None
        min_price_val = float('inf')
        max_price_val = float('-inf')

        # Recorremos todos los registros para recolectar datos
        for row in results:
            dt = row.date
            day_num = dt.toordinal()
            all_date_nums.append(day_num)
            all_prices.append(row.price)

            # Actualizamos mínimo y máximo global
            if row.price < min_price_val:
                min_price_val = row.price
                min_price_store = row.store_name
            if row.price > max_price_val:
                max_price_val = row.price
                max_price_store = row.store_name

        # Regresión lineal (función ya existente en tu código)
        m, b = linear_regression(all_date_nums, all_prices)
        if m is not None:
            min_day = min(all_date_nums)
            max_day = max(all_date_nums)
            num_points = 50
            step = max(1, (max_day - min_day) // num_points)
            regression_dates = []
            regression_prices = []
            for day in range(min_day, max_day + 1, step):
                regression_dates.append(datetime.fromordinal(day).strftime('%Y-%m-%d'))
                regression_prices.append(m * day + b)

            # Añadimos la serie de regresión
            regression_trace = {
                'label': 'Línea de Regresión',
                'dates': regression_dates,
                'prices': regression_prices,
                'mode': 'lines',
                'line': {
                    'color': 'red',
                    'dash': 'dot',
                    'width': 5
                }
            }
            data_series.append(regression_trace)

        # Cálculo de estadísticas globales
        count = len(all_prices)
        if count > 0:
            avg_price = sum(all_prices) / count
            variance = sum((x - avg_price) ** 2 for x in all_prices) / count
            std_dev = variance ** 0.5
        else:
            avg_price = 0
            std_dev = 0

        # Determinar tendencia y cambio mensual
        if m is not None and avg_price != 0:
            if m > 0:
                trend = "ascendente"
            elif m < 0:
                trend = "descendente"
            else:
                trend = "estable"
            daily_change_percentage = (m / avg_price) * 100
            monthly_change_percentage = daily_change_percentage * 30
        else:
            trend = "no definida"
            monthly_change_percentage = 0

        # Construimos un texto más elaborado para los insights
        producto = (form_data['product_name']
                    if form_data['product_name'] != 'all'
                    else 'Todos los productos')
        if form_data['brand'] and 'all' not in form_data['brand']:
            marca = ", ".join(form_data['brand'])
        else:
            marca = "todas las marcas"
        presentacion = (form_data['presentation']
                        if form_data['presentation'] != 'all'
                        else 'todas las presentaciones')

        # Texto final de insights
        # Sustituye \n por <br> en el frontend para conservar saltos de línea, o usa directamente <br> aquí.
        insights_text = (
            f"Entre el <strong>{form_data['start_date']}</strong> y el <strong>{form_data['end_date']}</strong>, "
            f"se analizaron <strong>{count}</strong> registros de precios para <strong>{producto}</strong> "
            f"(incluyendo <strong>{marca}</strong> y <strong>{presentacion}</strong>). "
            f"El precio promedio en este período fue de <strong>ƒ {avg_price:.2f}</strong>, "
            f"con una desviación estándar de <strong>ƒ {std_dev:.2f}</strong>. "
            f"El valor más bajo observado fue de <strong>ƒ {min_price_val:.2f}</strong> en la tienda <strong>{min_price_store}</strong>, "
            f"mientras que el precio más alto alcanzó los <strong>ƒ {max_price_val:.2f}</strong> en la tienda <strong>{max_price_store}</strong>. "
            f"En cuanto a la tendencia general, esta es <strong>{trend}</strong>, "
            f"con un cambio estimado de <strong>{monthly_change_percentage:.2f}%</strong> mensual. "
            f"Estos resultados sugieren un comportamiento de precios que puede "
            f"variar según la ubicación y la marca, ofreciendo oportunidades "
            f"para comparar y optimizar decisiones de compra o venta."
        )

        # Título del gráfico
        titulo = f"{producto} | {marca} | {presentacion}"

        # Respuesta final
        plot_data = {
            'title': titulo,
            'data': data_series,
            'insights': insights_text
        }
        return jsonify(plot_data)

    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Error en /generate_graph: {e}")
        return jsonify({'error': 'Error al generar el gráfico'}), 500


@app.route('/api/filter_options', methods=['GET'])
@login_required
def get_filter_options():
    """Obtiene las opciones para los filtros del formulario."""
    try:
        product_name = request.args.get('product_name')
        
        # Query base
        brand_query = db.session.query(Price.brand).distinct()
        presentation_query = db.session.query(Price.presentation).distinct()

        # Filtrar por producto si se especifica
        if product_name:
            product = Product.query.filter(Product.name == product_name).first()
            if product:
                brand_query = brand_query.filter(Price.product_id == product.id)
                presentation_query = presentation_query.filter(Price.product_id == product.id)

        # Obtener resultados
        brands = [b[0] for b in brand_query.filter(Price.brand.isnot(None)).all()]
        presentations = [p[0] for p in presentation_query.filter(Price.presentation.isnot(None)).all()]

        return jsonify({
            'brands': sorted(brands),
            'presentations': sorted(presentations)
        })

    except Exception as e:
        logger.error(f"Error getting filter options: {str(e)}")
        return jsonify({'error': 'Error al obtener opciones de filtros'}), 500

@app.route('/api/product_suggestions', methods=['GET'])
@login_required
def get_product_suggestions():
    """Obtiene sugerencias de productos para el autocompletado."""
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return jsonify([])

        products = Product.query.filter(
            Product.name.ilike(f'%{query}%')
        ).distinct().limit(10).all()

        suggestions = [{'id': p.id, 'name': p.name} for p in products]
        return jsonify(suggestions)

    except Exception as e:
        logger.error(f"Error getting product suggestions: {str(e)}")
        return jsonify({'error': 'Error al obtener sugerencias'}), 500

@app.route('/api/store_options', methods=['GET'])
@login_required
def get_store_options():
    """Obtiene la lista de tiendas disponibles."""
    try:
        stores = Store.query.order_by(Store.name).all()
        return jsonify([{
            'id': store.id,
            'name': store.name
        } for store in stores])

    except Exception as e:
        logger.error(f"Error getting store options: {str(e)}")
        return jsonify({'error': 'Error al obtener tiendas'}), 500




@app.route('/reports')
@login_required
def reports_index():
    return render_template('reports_index.html')

@app.route('/reports/products')
@login_required
def reports_products():
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)
    query = Product.query

    # Filtro por búsqueda
    if search:
        query = query.filter(
            Product.name.ilike(f'%{search}%') |
            Product.brand.ilike(f'%{search}%') |
            Product.presentation.ilike(f'%{search}%') |
            Product.distributor.ilike(f'%{search}%')
        )

    products_pag = query.order_by(Product.id).paginate(page=page, per_page=10)

    # Convertir a set y luego a lista para eliminar duplicados
    product_names_raw = [p.name for p in Product.query.order_by(Product.name).all()]
    product_names = sorted(set(product_names_raw))

    return render_template(
        'report_products.html',
        products=products_pag,
        product_names=product_names
    )

@app.route('/reports/stores', methods=['GET'])
@login_required
def reports_stores():
    search = request.args.get('search', '')
    page = request.args.get('page', 1, type=int)

    query = Store.query
    if search:
        query = query.filter(
            Store.name.ilike(f'%{search}%') |
            Store.address.ilike(f'%{search}%')
        )

    # Paginación: 20 resultados por página (o el número que desees)
    stores_pag = query.order_by(Store.id).paginate(page=page, per_page=10)

    # Si quieres autocompletado (Awesomplete) para nombres de tiendas:
    store_names = [st.name for st in Store.query.order_by(Store.name).all()]

    return render_template(
        'report_stores.html',
        stores=stores_pag,
        store_names=store_names,
        search=search
    )


@app.route('/reports/prices', methods=['GET'])
@login_required
def reports_prices():
    page = request.args.get('page', 1, type=int)
    
    start_date_str = request.args.get('start_date', '').strip()
    end_date_str = request.args.get('end_date', '').strip()
    product_name = request.args.get('product', '').strip()
    brand_name = request.args.get('brand', '').strip()

    # Query base
    query = Price.query.join(Product).join(Store)
    
    # Filtros de fecha
    if start_date_str:
        try:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d')
            query = query.filter(Price.date >= start_date)
        except ValueError:
            pass  # Maneja error si quieres
    
    if end_date_str:
        try:
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d')
            # Ajusta para incluir todo el día
            end_date = end_date.replace(hour=23, minute=59, second=59)
            query = query.filter(Price.date <= end_date)
        except ValueError:
            pass

    # Filtro de producto
    if product_name:
        query = query.filter(Product.name.ilike(f'%{product_name}%'))
    
    # Filtro de marca
    if brand_name:
        query = query.filter(Price.brand.ilike(f'%{brand_name}%'))
    
    # Ordenar por fecha descendente (o como prefieras)
    query = query.order_by(Price.date.desc())

    # Paginación
    prices_pag = query.paginate(page=page, per_page=10)

    # Listas para Awesomplete (evita duplicados con set())
    # - Lista de nombres de producto
    all_products = db.session.query(Product.name).distinct().order_by(Product.name).all()
    product_names = sorted({p[0] for p in all_products if p[0]})
    # - Lista de marcas en Price
    all_brands = db.session.query(Price.brand).distinct().order_by(Price.brand).all()
    brand_names = sorted({b[0] for b in all_brands if b[0]})
    
    return render_template(
        'report_prices.html',
        prices=prices_pag,
        product_names=product_names,
        brand_names=brand_names
    )


@app.context_processor
def inject_current_year():
    return {'current_year': datetime.utcnow().year}

if __name__ == '__main__':
    app.run(debug=True)


