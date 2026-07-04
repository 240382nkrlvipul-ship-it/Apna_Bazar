from flask import Blueprint, request, jsonify, g
from backend.database import db, Coupon
from backend.utils.auth_helper import admin_required, token_required, decode_token

coupons_bp = Blueprint('coupons', __name__)

@coupons_bp.route('', methods=['GET'])
def get_coupons():
    """Retrieve all coupons (Admin gets all, customers get only active ones)"""
    is_admin = False
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        token = auth_header.split(' ')[1]
        data = decode_token(token)
        if isinstance(data, dict) and data.get('role') in ['admin', 'superadmin', 'staff']:
            is_admin = True
            
    if is_admin:
        coupons = Coupon.query.order_by(Coupon.created_at.desc()).all()
    else:
        coupons = Coupon.query.filter_by(is_active=True).all()
        
    return jsonify([c.to_dict() for c in coupons]), 200

@coupons_bp.route('', methods=['POST'])
@admin_required
def create_coupon():
    """Create a new coupon (Admin only)"""
    data = request.get_json()
    if not data or not all(k in data for k in ('code', 'discount_type', 'discount_value')):
        return jsonify({'message': 'Missing required fields'}), 400
        
    code = data['code'].strip().upper()
    existing = Coupon.query.filter_by(code=code).first()
    if existing:
        return jsonify({'message': f'Coupon code "{code}" already exists'}), 400
        
    coupon = Coupon(
        code=code,
        discount_type=data['discount_type'],
        discount_value=float(data['discount_value']),
        min_cart_amount=float(data.get('min_cart_amount', 0.00)),
        max_discount_amount=float(data['max_discount_amount']) if data.get('max_discount_amount') else None,
        description_en=data.get('description_en', '').strip() or None,
        description_hi=data.get('description_hi', '').strip() or None,
        description_mr=data.get('description_mr', '').strip() or None,
        is_active=data.get('is_active', True)
    )
    db.session.add(coupon)
    db.session.commit()
    return jsonify({'message': 'Coupon created successfully', 'coupon': coupon.to_dict()}), 201

@coupons_bp.route('/<int:coupon_id>', methods=['PUT'])
@admin_required
def update_coupon(coupon_id):
    """Update coupon fields (Admin only)"""
    coupon = Coupon.query.get(coupon_id)
    if not coupon:
        return jsonify({'message': 'Coupon not found'}), 404
        
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No data provided'}), 400
        
    if 'code' in data:
        code = data['code'].strip().upper()
        if code != coupon.code:
            existing = Coupon.query.filter_by(code=code).first()
            if existing:
                return jsonify({'message': f'Coupon code "{code}" already exists'}), 400
            coupon.code = code
            
    if 'discount_type' in data:
        coupon.discount_type = data['discount_type']
    if 'discount_value' in data:
        coupon.discount_value = float(data['discount_value'])
    if 'min_cart_amount' in data:
        coupon.min_cart_amount = float(data['min_cart_amount'])
    if 'max_discount_amount' in data:
        coupon.max_discount_amount = float(data['max_discount_amount']) if data['max_discount_amount'] else None
    if 'description_en' in data:
        coupon.description_en = data['description_en'].strip() or None
    if 'description_hi' in data:
        coupon.description_hi = data['description_hi'].strip() or None
    if 'description_mr' in data:
        coupon.description_mr = data['description_mr'].strip() or None
    if 'is_active' in data:
        coupon.is_active = bool(data['is_active'])
        
    db.session.commit()
    return jsonify({'message': 'Coupon updated successfully', 'coupon': coupon.to_dict()}), 200

@coupons_bp.route('/<int:coupon_id>', methods=['DELETE'])
@admin_required
def delete_coupon(coupon_id):
    """Delete a coupon (Admin only)"""
    coupon = Coupon.query.get(coupon_id)
    if not coupon:
        return jsonify({'message': 'Coupon not found'}), 404
        
    db.session.delete(coupon)
    db.session.commit()
    return jsonify({'message': 'Coupon deleted successfully'}), 200

@coupons_bp.route('/validate', methods=['POST'])
@token_required
def validate_coupon():
    """Check coupon validation against cart total"""
    data = request.get_json()
    if not data or 'code' not in data or 'cart_amount' not in data:
        return jsonify({'message': 'Coupon code and cart amount are required'}), 400
        
    code = data['code'].strip().upper()
    cart_amount = float(data['cart_amount'])
    
    coupon = Coupon.query.filter_by(code=code, is_active=True).first()
    if not coupon:
        return jsonify({'valid': False, 'message': 'Invalid coupon code or coupon is expired.'}), 200
        
    if cart_amount < float(coupon.min_cart_amount):
        return jsonify({
            'valid': False,
            'message': f'Minimum order amount of ₹{float(coupon.min_cart_amount):.2f} required to apply this coupon.'
        }), 200
        
    # Calculate discount
    discount_amount = 0.0
    if coupon.discount_type == 'percentage':
        discount_amount = cart_amount * (float(coupon.discount_value) / 100.0)
        if coupon.max_discount_amount is not None:
            discount_amount = min(discount_amount, float(coupon.max_discount_amount))
    elif coupon.discount_type == 'flat':
        discount_amount = float(coupon.discount_value)
        
    discount_amount = min(discount_amount, cart_amount)
    
    return jsonify({
        'valid': True,
        'discount_amount': float(round(discount_amount, 2)),
        'coupon': coupon.to_dict()
    }), 200
