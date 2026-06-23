from flask import Blueprint, request, jsonify
from backend.database import db, Village
from backend.utils.auth_helper import admin_required

villages_bp = Blueprint('villages', __name__)

@villages_bp.route('', methods=['GET'])
def get_villages():
    """Get all villages. Admin gets all, customer gets only allowed/active ones"""
    show_all = request.args.get('all', 'false').lower() == 'true'
    
    if show_all:
        villages = Village.query.all()
    else:
        villages = Village.query.filter_by(is_allowed=True).all()
        
    return jsonify([v.to_dict() for v in villages]), 200

@villages_bp.route('', methods=['POST'])
@admin_required
def create_village():
    """Create a new approved village restriction (Admin only)"""
    data = request.get_json()
    if not data or not all(k in data for k in ('name_en', 'name_hi', 'name_mr')):
        return jsonify({'message': 'Village names in English, Hindi, and Marathi are required'}), 400
        
    name_en = data['name_en'].strip()
    name_hi = data['name_hi'].strip()
    name_mr = data['name_mr'].strip()
    is_allowed = data.get('is_allowed', True)
    
    try:
        delivery_charge = float(data.get('delivery_charge', 0.0))
    except ValueError:
        return jsonify({'message': 'Invalid delivery charge'}), 400
        
    # Check duplicate
    existing = Village.query.filter_by(name_en=name_en).first()
    if existing:
        return jsonify({'message': f'Village with name "{name_en}" already exists'}), 400
        
    village = Village(
        name_en=name_en,
        name_hi=name_hi,
        name_mr=name_mr,
        is_allowed=is_allowed,
        delivery_charge=delivery_charge
    )
    db.session.add(village)
    db.session.commit()
    
    return jsonify({
        'message': 'Village created successfully',
        'village': village.to_dict()
    }), 201

@villages_bp.route('/<int:village_id>', methods=['PUT'])
@admin_required
def update_village(village_id):
    """Update village status or delivery charge (Admin only)"""
    village = Village.query.get(village_id)
    if not village:
        return jsonify({'message': 'Village not found'}), 404
        
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No data provided'}), 400
        
    if 'name_en' in data:
        name_en = data['name_en'].strip()
        if name_en != village.name_en:
            existing = Village.query.filter_by(name_en=name_en).first()
            if existing:
                return jsonify({'message': f'Village with name "{name_en}" already exists'}), 400
            village.name_en = name_en
            
    if 'name_hi' in data:
        village.name_hi = data['name_hi'].strip()
    if 'name_mr' in data:
        village.name_mr = data['name_mr'].strip()
    if 'is_allowed' in data:
        village.is_allowed = bool(data['is_allowed'])
        
    if 'delivery_charge' in data:
        try:
            village.delivery_charge = float(data['delivery_charge'])
        except ValueError:
            return jsonify({'message': 'Invalid delivery charge'}), 400
            
    db.session.commit()
    return jsonify({
        'message': 'Village updated successfully',
        'village': village.to_dict()
    }), 200

@villages_bp.route('/<int:village_id>', methods=['DELETE'])
@admin_required
def delete_village(village_id):
    """Delete a village from approved list (Admin only)"""
    village = Village.query.get(village_id)
    if not village:
        return jsonify({'message': 'Village not found'}), 404
        
    db.session.delete(village)
    db.session.commit()
    return jsonify({'message': 'Village deleted successfully'}), 200
