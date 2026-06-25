import os
import sys

# Allow running this file directly from inside the backend folder by adding the parent folder to the import search path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from flask import Flask, send_from_directory, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash
import gzip
import io
from backend.utils.security import sanitize_data

from backend.config import Config
from backend.database import db, Admin, Village, Category, Product, InventoryLog, OTPStore
from backend.socket_service import socketio

# Import Blueprints
from backend.routes.auth import auth_bp
from backend.routes.categories import categories_bp
from backend.routes.products import products_bp
from backend.routes.villages import villages_bp
from backend.routes.orders import orders_bp
from backend.routes.reports import reports_bp
from backend.routes.delivery import delivery_bp

def create_app():
    app = Flask(__name__, static_folder='static')
    app.config.from_object(Config)
    
    # Enable Cross-Origin Resource Sharing
    # Always allow Capacitor APK origins + configured FRONTEND_URL + local dev
    frontend_url = Config.FRONTEND_URL
    allowed_origins = [
        frontend_url,            # production web/APK domain from env
        "capacitor://localhost", # Capacitor Android APK origin
        "https://localhost",     # Capacitor iOS APK origin
        "http://localhost",      # Capacitor dev fallback
        "http://localhost:5173", # Vite local dev
        "http://localhost:5174", # Vite local dev (alternate port)
    ]
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

    # XSS Sanitization global filter hook
    @app.before_request
    def sanitize_inputs():
        if request.is_json:
            try:
                json_data = request.get_json(silent=True)
                if json_data:
                    sanitized = sanitize_data(json_data)
                    request._cached_json = (sanitized, sanitized)
            except Exception:
                pass

    # GZIP Response Compression hook
    @app.after_request
    def compress_response(response):
        # Support GZIP encoding compression
        accept_encoding = request.headers.get('Accept-Encoding', '')
        if 'gzip' not in accept_encoding.lower():
            return response
        if response.status_code < 200 or response.status_code >= 300:
            return response
        if response.direct_passthrough:
            return response
        
        content_type = response.content_type or ''
        if 'json' not in content_type and 'text' not in content_type and 'javascript' not in content_type:
            return response
            
        gzip_buffer = io.BytesIO()
        gzip_file = gzip.GzipFile(mode='wb', fileobj=gzip_buffer)
        gzip_file.write(response.get_data())
        gzip_file.close()
        
        response.set_data(gzip_buffer.getvalue())
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = len(response.get_data())
        return response
    
    # Initialize database
    db.init_app(app)
    
    # Initialize SocketIO
    socketio.init_app(app, cors_allowed_origins=allowed_origins)
    
    # Register Blueprints
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(categories_bp, url_prefix='/api/categories')
    app.register_blueprint(products_bp, url_prefix='/api/products')
    app.register_blueprint(villages_bp, url_prefix='/api/villages')
    app.register_blueprint(orders_bp, url_prefix='/api')  # Contains both /cart and /orders
    app.register_blueprint(reports_bp, url_prefix='/api/reports')
    app.register_blueprint(delivery_bp, url_prefix='/api/delivery')

    
    # Route for serving uploaded images
    @app.route('/static/uploads/<filename>')
    def serve_uploaded_file(filename):
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
        
    # Health check route
    @app.route('/api/health', methods=['GET'])
    def health_check():
        return jsonify({
            'status': 'healthy',
            'database': app.config['SQLALCHEMY_DATABASE_URI'].split('@')[-1] if '@' in app.config['SQLALCHEMY_DATABASE_URI'] else 'sqlite_or_local',
            'languages': ['en', 'hi', 'mr']
        }), 200
        
    # Auto-seed database inside app context
    with app.app_context():
        db.create_all()
        
        # Automatic DB migration check: alter VARCHAR(255) to TEXT for base64 images
        try:
            engine = db.engine
            dialect = engine.dialect.name
            if dialect in ('postgresql', 'mysql'):
                from sqlalchemy import text
                with engine.begin() as conn:
                    if dialect == 'postgresql':
                        conn.execute(text("ALTER TABLE categories ALTER COLUMN image_url TYPE TEXT"))
                        conn.execute(text("ALTER TABLE products ALTER COLUMN image_url TYPE TEXT"))
                        conn.execute(text("ALTER TABLE product_images ALTER COLUMN image_url TYPE TEXT"))
                    elif dialect == 'mysql':
                        conn.execute(text("ALTER TABLE categories MODIFY COLUMN image_url TEXT"))
                        conn.execute(text("ALTER TABLE products MODIFY COLUMN image_url TEXT"))
                        conn.execute(text("ALTER TABLE product_images MODIFY COLUMN image_url TEXT"))
                print("Database columns migrated to TEXT successfully.")
        except Exception as e:
            print(f"DB columns check/migration warning: {e}")
            
        seed_data()
        
    return app

def seed_data():
    """Seeds default values (Admins, Villages, Categories, Products) if database is empty"""
    if Admin.query.first() is not None:
        return # Database is already populated
        
    print("Seeding database with default mock data...")
    
    # 1. Seed Admin Accounts
    admin_user = Admin(
        username="admin",
        password_hash=generate_password_hash("admin123"),
        role="superadmin"
    )
    db.session.add(admin_user)
    
    # 2. Seed Allowed Villages
    villages = [
        Village(name_en="Palghar", name_hi="पालघर", name_mr="पालघर", is_allowed=True, delivery_charge=20.00),
        Village(name_en="Manor", name_hi="मनोर", name_mr="मनोर", is_allowed=True, delivery_charge=40.00),
        Village(name_en="Shirgaon", name_hi="शिरगाव", name_mr="शिरगाव", is_allowed=True, delivery_charge=15.00),
        Village(name_en="Kelva", name_hi="केळवे", name_mr="केळवे", is_allowed=True, delivery_charge=30.00),
        Village(name_en="Boisar", name_hi="बोईसर", name_mr="बोईसर", is_allowed=False, delivery_charge=50.00), # Blocked village
    ]
    for v in villages:
        db.session.add(v)
    db.session.commit() # Save villages to refer during products or categories creation
    
    # 3. Seed Categories
    categories = {
        'dairy': Category(name_en="Dairy Products", name_hi="डेअरी उत्पादने", name_mr="डेअरी उत्पादने", is_active=True),
        'vegetables': Category(name_en="Vegetables", name_hi="भाज्या", name_mr="भाज्या", is_active=True),
        'fruits': Category(name_en="Fruits", name_hi="फळे", name_mr="फळे", is_active=True),
        'rice_grains': Category(name_en="Rice & Grains", name_hi="चावल और अनाज", name_mr="तांदूळ आणि धान्य", is_active=True),
        'snacks': Category(name_en="Snacks", name_hi="नाश्ता", name_mr="स्नॅक्स", is_active=True),
        'beverages': Category(name_en="Beverages", name_hi="पेय", name_mr="पेये", is_active=True),
        'bakery': Category(name_en="Bakery", name_hi="बेकरी", name_mr="बेकरी", is_active=True),
        'grocery': Category(name_en="Grocery Staples", name_hi="किराना सामान", name_mr="किराणा माल", is_active=True)
    }
    
    for c in categories.values():
        db.session.add(c)
    db.session.commit()
    
    # 4. Seed Products
    products = [
        # Dairy
        Product(
            category_id=categories['dairy'].id,
            name_en="Fresh Buffalo Milk", name_hi="ताजा भैंस का दूध", name_mr="ताजे म्हशीचे दूध",
            description_en="100% pure organic dairy buffalo milk.",
            description_hi="100% शुद्ध जैविक भैंस का दूध।",
            description_mr="100% शुद्ध म्हशीचे दूध.",
            price=65.00, discount_price=60.00, stock_quantity=40.00, unit="litre", is_visible=True
        ),
        Product(
            category_id=categories['dairy'].id,
            name_en="Amul Paneer", name_hi="अमुल पनीर", name_mr="अमुल पनीर",
            description_en="Fresh cottage cheese 200g pack.",
            description_hi="ताजा पनीर 200 ग्राम पैक।",
            description_mr="ताजे पनीर 200 ग्रॅम पॅक.",
            price=90.00, discount_price=85.00, stock_quantity=15.00, unit="packet", is_visible=True
        ),
        
        # Vegetables
        Product(
            category_id=categories['vegetables'].id,
            name_en="Organic Tomatoes", name_hi="जैविक टमाटर", name_mr="सेंद्रिय टोमॅटो",
            description_en="Fresh farm-picked red tomatoes.",
            description_hi="खेत से चुने गए ताजा लाल टमाटर।",
            description_mr="शेतकऱ्यांकडून आणलेले ताजे लाल टोमॅटो.",
            price=45.00, discount_price=38.00, stock_quantity=50.00, unit="kg", is_visible=True
        ),
        Product(
            category_id=categories['vegetables'].id,
            name_en="Potatoes", name_hi="आलू", name_mr="बटाटे",
            description_en="Premium local potatoes for everyday cooking.",
            description_hi="रोजाना पकाने के लिए प्रीमियम स्थानीय आलू।",
            description_mr="रोजच्या जेवणासाठी लागणारे बटाटे.",
            price=30.00, discount_price=26.00, stock_quantity=80.00, unit="kg", is_visible=True
        ),
        Product(
            category_id=categories['vegetables'].id,
            name_en="Fresh Spinach", name_hi="ताजा पालक", name_mr="ताजी पालक भाजी",
            description_en="Green organic spinach leafy vegetable.",
            description_hi="हरी जैविक पालक की पत्तियां।",
            description_mr="हिरवा सेंद्रिय ताजा पालक.",
            price=20.00, discount_price=18.00, stock_quantity=25.00, unit="piece", is_visible=True
        ),
        
        # Fruits
        Product(
            category_id=categories['fruits'].id,
            name_en="Shimla Apples", name_hi="शिमला सेब", name_mr="शिमला सफरचंद",
            description_en="Crispy, sweet, and juicy red apples from Shimla.",
            description_hi="शिमला से कुरकुरे, मीठे और रसीले लाल सेब।",
            description_mr="शिमला येथील ताजी आणि गोड सफरचंद.",
            price=160.00, discount_price=140.00, stock_quantity=30.00, unit="kg", is_visible=True
        ),
        Product(
            category_id=categories['fruits'].id,
            name_en="Bananas (Dozen)", name_hi="केले (दर्जन)", name_mr="केळी (डझन)",
            description_en="Sweet and ripe local bananas, set of 12.",
            description_hi="मीठे और पके हुए स्थानीय केले, 12 का समूह।",
            description_mr="पिकलेली आणि गोड केळी, 12 नग.",
            price=60.00, discount_price=50.00, stock_quantity=15.00, unit="piece", is_visible=True
        ),
        
        # Rice & Grains
        Product(
            category_id=categories['rice_grains'].id,
            name_en="Basmati Rice Premium", name_hi="बासमती चावल प्रीमियम", name_mr="बासमती तांदूळ प्रीमियम",
            description_en="Long grain fragrant basmati rice.",
            description_hi="लंबे दानेदार खुशबूदार बासमती चावल।",
            description_mr="सुवासिक लांब दाण्याचे बासमती तांदूळ.",
            price=120.00, discount_price=110.00, stock_quantity=100.00, unit="kg", is_visible=True
        ),
        Product(
            category_id=categories['rice_grains'].id,
            name_en="Wheat Flour (Atta) 5kg", name_hi="गेंहू का आटा 5 किलो", name_mr="गव्हाचे पीठ ५ किलो",
            description_en="100% whole wheat stone ground flour.",
            description_hi="100% चोकरयुक्त गेंहू का आटा।",
            description_mr="१००% गव्हाचे दळलेले पीठ.",
            price=240.00, discount_price=225.00, stock_quantity=20.00, unit="packet", is_visible=True
        ),
        
        # Snacks
        Product(
            category_id=categories['snacks'].id,
            name_en="Aloo Bhujia", name_hi="आलू भुजिया", name_mr="आलू भुजिया शेव",
            description_en="Crispy potato noodles snack with spices.",
            description_hi="मसालों के साथ कुरकुरा आलू नूडल नमकीन।",
            description_mr="मसालेदार बटाटा शेव.",
            price=40.00, discount_price=38.00, stock_quantity=45.00, unit="packet", is_visible=True
        )
    ]
    
    for p in products:
        db.session.add(p)
    db.session.commit()
    
    # Log initial inventory logs for all seeded products
    for p in products:
        log = InventoryLog(
            product_id=p.id,
            quantity_changed=p.stock_quantity,
            change_type='Admin Restock',
            notes='Auto-seeded initial stock load'
        )
        db.session.add(log)
    db.session.commit()
    
    print("Database seeding completed successfully!")

# -------------------------------------------------------
# Gunicorn/WSGI entry point (used by Render and other hosts)
# -------------------------------------------------------
application = create_app()

if __name__ == '__main__':
    app = application
    # Runs backend Flask server locally
    socketio.run(app, host='0.0.0.0', port=Config.PORT, debug=True, allow_unsafe_werkzeug=True)
