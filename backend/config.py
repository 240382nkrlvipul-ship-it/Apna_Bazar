import os

# Load .env file for local development (python-dotenv is optional but helpful)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed; rely on actual environment variables

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'village-grocery-secret-key-987654')
    JWT_SECRET = os.environ.get('JWT_SECRET', 'village-grocery-jwt-secret-key-123456')
    
    # Database config: defaults to SQLite for local development but supports MySQL via DATABASE_URL env var
    # E.g. DATABASE_URL=mysql+pymysql://username:password@localhost/grocery_db
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///grocery.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload configurations
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    UPLOAD_FOLDER = os.environ.get('UPLOAD_FOLDER', os.path.join(BASE_DIR, 'static', 'uploads'))
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10 MB limit
    
    # Port setup
    PORT = int(os.environ.get('PORT', 5000))

    # Frontend URL — used for CORS and SMS tracking links
    FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:5173')

    # Shop Location Configurations for Distance Radius Validation
    SHOP_LATITUDE = float(os.environ.get('SHOP_LATITUDE', 19.4553))
    SHOP_LONGITUDE = float(os.environ.get('SHOP_LONGITUDE', 72.8120))
    DELIVERY_RADIUS_KM = float(os.environ.get('DELIVERY_RADIUS_KM', 15.0))
