import random
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from backend.database import db, Customer, Admin, Cart, DeliveryAgent, OTPStore
from backend.utils.auth_helper import encode_token, token_required, admin_required
from backend.utils.rate_limiter import rate_limit

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/send-otp', methods=['POST'])
@rate_limit(limit=5, period=60)
def send_otp():
    """Generates and stores a 6-digit numeric OTP for development mode"""
    data = request.get_json()
    if not data or 'mobile' not in data:
        return jsonify({'success': False, 'message': 'Mobile number is required'}), 400
        
    mobile = data['mobile'].strip()
    if not mobile.isdigit() or len(mobile) != 10:
        return jsonify({'success': False, 'message': 'Invalid mobile number format (must be 10 digits)'}), 400

    # Generate a randomly generated 6 digit numeric OTP
    otp = str(random.randint(100000, 999999))
    
    # Expiry in 5 minutes
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    
    # Store OTP temporarily in database
    otp_entry = OTPStore(
        mobile_number=mobile,
        otp=otp,
        expires_at=expires_at,
        verified=False
    )
    db.session.add(otp_entry)
    db.session.commit()
    
    # Print the OTP in backend console clearly
    print("\n" + "="*50)
    print(f" [DEVELOPMENT MODE] OTP FOR {mobile}: {otp}")
    print("="*50 + "\n")
    
    return jsonify({
        'success': True,
        'otp': otp,
        'message': 'Development OTP generated'
    }), 200

@auth_bp.route('/verify-otp', methods=['POST'])
@rate_limit(limit=10, period=60)
def verify_otp():
    """Verifies OTP, logs in user, and returns JWT session token"""
    data = request.get_json()
    if not data or 'mobile' not in data or 'otp' not in data:
        return jsonify({'success': False, 'message': 'Mobile number and OTP are required'}), 400
        
    mobile = data['mobile'].strip()
    otp = data['otp'].strip()
    
    # Validate mobile format
    if not mobile.isdigit() or len(mobile) != 10:
        return jsonify({'success': False, 'message': 'Invalid mobile number format'}), 400
        
    # Get latest active unverified OTP for this number
    otp_record = OTPStore.query.filter_by(mobile_number=mobile, verified=False)\
                               .order_by(OTPStore.created_at.desc()).first()
                               
    if not otp_record:
        return jsonify({'success': False, 'message': 'OTP request not found or already verified'}), 400
        
    if datetime.utcnow() > otp_record.expires_at:
        return jsonify({'success': False, 'message': 'OTP has expired'}), 400
        
    if otp_record.otp != otp:
        return jsonify({'success': False, 'message': 'Incorrect OTP'}), 400
        
    # Mark OTP as verified (single-use logic)
    otp_record.verified = True
    db.session.commit()
    
    # Determine role based on mobile number
    if mobile == '8888199091':
        role = 'admin'
        # Seeded admin lookup/fallback creation
        admin = Admin.query.filter_by(username='admin').first()
        if not admin:
            admin = Admin(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                role='superadmin'
            )
            db.session.add(admin)
            db.session.commit()
        user_id = admin.id
        user_dict = admin.to_dict()
    else:
        role = 'customer'
        # Fetch or auto-register customer
        customer = Customer.query.filter_by(mobile=mobile).first()
        if not customer:
            customer = Customer(mobile=mobile, name="Customer")
            db.session.add(customer)
            db.session.commit() # Save first to generate customer ID
            
            # Create an empty cart for new customer
            cart = Cart(customer_id=customer.id)
            db.session.add(cart)
            db.session.commit()
        user_id = customer.id
        user_dict = customer.to_dict()
        
    # Generate JWT token storing user_id, role, mobile
    token = encode_token(user_id, role=role, mobile=mobile)
    
    return jsonify({
        'success': True,
        'message': 'Login successful',
        'token': token,
        'user': user_dict,
        'role': role
    }), 200

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
def verify_otp_old():
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
