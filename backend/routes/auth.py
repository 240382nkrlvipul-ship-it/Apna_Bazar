import random
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from backend.database import db, Customer, Admin, Cart, DeliveryAgent
from backend.utils.auth_helper import encode_token, token_required, admin_required
from backend.utils.rate_limiter import rate_limit

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/otp/request', methods=['POST'])
@rate_limit(limit=5, period=60)
def request_otp():
    """Generates and logs a simulated OTP for customer mobile login"""
    data = request.get_json()
    if not data or 'mobile' not in data:
        return jsonify({'message': 'Mobile number is required'}), 400
        
    mobile = data['mobile'].strip()
    if len(mobile) < 10:
        return jsonify({'message': 'Invalid mobile number format'}), 400

    # Generate a simple 6-digit OTP
    otp = str(random.randint(100000, 999999))
    # For local test environment, let's also support a static/override OTP for simplicity
    if mobile == "9999999999":
        otp = "123456"
        
    otp_hash = generate_password_hash(otp)
    expiry = datetime.utcnow() + timedelta(minutes=5)
    
    customer = Customer.query.filter_by(mobile=mobile).first()
    if not customer:
        customer = Customer(mobile=mobile)
        db.session.add(customer)
        db.session.commit() # Create first to get ID
        
        # Auto-create empty cart for new customer
        cart = Cart(customer_id=customer.id)
        db.session.add(cart)
        
    customer.otp_hash = otp_hash
    customer.otp_expiry = expiry
    customer.is_verified = False
    db.session.commit()
    
    # Print the OTP clearly in the console to simulate sending a WhatsApp/SMS
    print("\n" + "="*50)
    print(f" SIMULATED OTP SENT TO {mobile}")
    print(f" Your Verification Code is: {otp}")
    print("="*50 + "\n")
    
    return jsonify({
        'message': 'OTP sent successfully (Simulated)',
        'otp': otp, # Returned in development mode so frontend can auto-fill or show it
        'mobile': mobile
    }), 200

@auth_bp.route('/otp/verify', methods=['POST'])
@rate_limit(limit=10, period=60)
def verify_otp():
    """Verifies simulated OTP and returns JWT token"""
    data = request.get_json()
    if not data or 'mobile' not in data or 'otp' not in data:
        return jsonify({'message': 'Mobile number and OTP are required'}), 400
        
    mobile = data['mobile'].strip()
    otp = data['otp'].strip()
    
    customer = Customer.query.filter_by(mobile=mobile).first()
    if not customer:
        return jsonify({'message': 'Customer not found'}), 404
        
    if not customer.otp_hash or not customer.otp_expiry:
        return jsonify({'message': 'OTP not requested or expired'}), 400
        
    if datetime.utcnow() > customer.otp_expiry:
        return jsonify({'message': 'OTP has expired'}), 400
        
    if not check_password_hash(customer.otp_hash, otp):
        return jsonify({'message': 'Incorrect OTP'}), 400
        
    # Mark customer as verified and clear OTP fields
    customer.is_verified = True
    customer.otp_hash = None
    customer.otp_expiry = None
    db.session.commit()
    
    # Create cart if it somehow doesn't exist
    if not customer.cart:
        cart = Cart(customer_id=customer.id)
        db.session.add(cart)
        db.session.commit()
        
    token = encode_token(customer.id, role='customer')
    return jsonify({
        'message': 'OTP verified successfully',
        'token': token,
        'user': customer.to_dict()
    }), 200

@auth_bp.route('/admin/login', methods=['POST'])
def admin_login():
    """Admin login endpoint"""
    data = request.get_json()
    if not data or 'username' not in data or 'password' not in data:
        return jsonify({'message': 'Username and password are required'}), 400
        
    username = data['username'].strip()
    password = data['password'].strip()
    
    admin = Admin.query.filter_by(username=username).first()
    if not admin or not check_password_hash(admin.password_hash, password):
        return jsonify({'message': 'Invalid username or password'}), 401
        
    token = encode_token(admin.id, role=admin.role)
    return jsonify({
        'message': 'Admin login successful',
        'token': token,
        'user': admin.to_dict()
    }), 200

@auth_bp.route('/agent/login', methods=['POST'])
def agent_login():
    """Delivery Agent login endpoint"""
    data = request.get_json()
    if not data or 'mobile' not in data or 'password' not in data:
        return jsonify({'message': 'Mobile number and password are required'}), 400
        
    mobile = data['mobile'].strip()
    password = data['password'].strip()
    
    agent = DeliveryAgent.query.filter_by(mobile=mobile).first()
    if not agent or not check_password_hash(agent.password_hash, password):
        return jsonify({'message': 'Invalid mobile number or password'}), 401
        
    if agent.status != 'Active':
        return jsonify({'message': 'Your account is deactivated. Please contact administrator.'}), 403
        
    token = encode_token(agent.id, role='agent')
    return jsonify({
        'message': 'Agent login successful',
        'token': token,
        'user': agent.to_dict()
    }), 200

@auth_bp.route('/profile', methods=['GET'])
@token_required
def get_profile():
    """Retrieve details of the currently logged-in user or admin"""
    if g.user_role in ['admin', 'superadmin', 'staff']:
        admin = Admin.query.get(g.user_id)
        if not admin:
            return jsonify({'message': 'Admin profile not found'}), 404
        return jsonify({
            'role': g.user_role,
            'user': admin.to_dict()
        }), 200
    elif g.user_role == 'agent':
        agent = DeliveryAgent.query.get(g.user_id)
        if not agent:
            return jsonify({'message': 'Agent profile not found'}), 404
        return jsonify({
            'role': 'agent',
            'user': agent.to_dict()
        }), 200
    else:
        customer = Customer.query.get(g.user_id)
        if not customer:
            return jsonify({'message': 'Customer profile not found'}), 404
        return jsonify({
            'role': 'customer',
            'user': customer.to_dict()
        }), 200

@auth_bp.route('/profile/update', methods=['POST'])
@token_required
def update_profile():
    """Updates user name"""
    if g.user_role in ['admin', 'superadmin']:
        return jsonify({'message': 'Profile updates for admins not supported'}), 400
        
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({'message': 'Name is required'}), 400
        
    customer = Customer.query.get(g.user_id)
    if not customer:
        return jsonify({'message': 'Customer not found'}), 404
        
    customer.name = data['name'].strip()
    db.session.commit()
    
    return jsonify({
        'message': 'Profile updated successfully',
        'user': customer.to_dict()
    }), 200

@auth_bp.route('/customers', methods=['GET'])
@admin_required
def get_customers():
    """List all customers with pagination (Admin only)"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    paginated = Customer.query.order_by(Customer.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'customers': [c.to_dict() for c in paginated.items],
        'total': paginated.total,
        'page': paginated.page,
        'pages': paginated.pages
    }), 200
