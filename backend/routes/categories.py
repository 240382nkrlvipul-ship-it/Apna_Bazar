from flask import Blueprint, request, jsonify
from backend.database import db, Category
from backend.utils.auth_helper import admin_required
from backend.socket_service import socketio
from backend.utils.cache import cache

categories_bp = Blueprint('categories', __name__)

@categories_bp.route('', methods=['GET'])
def get_categories():
    """Get all categories. Admin gets all, customers only active ones"""
    show_all = request.args.get('all', 'false').lower() == 'true'
    cache_key = "categories:all" if show_all else "categories:active"
    
    cached = cache.get(cache_key)
    if cached is not None:
        return jsonify(cached), 200
        
    if show_all:
        categories = Category.query.all()
    else:
        categories = Category.query.filter_by(is_active=True).all()
        
    res_list = [cat.to_dict() for cat in categories]
    cache.set(cache_key, res_list, timeout=600)
    return jsonify(res_list), 200

@categories_bp.route('', methods=['POST'])
@admin_required
def create_category():
    """Create a new category (Admin only)"""
    data = request.get_json()
    if not data or not all(k in data for k in ('name_en', 'name_hi', 'name_mr')):
        return jsonify({'message': 'Category names in English, Hindi, and Marathi are required'}), 400
        
    name_en = data['name_en'].strip()
    name_hi = data['name_hi'].strip()
    name_mr = data['name_mr'].strip()
    image_url = data.get('image_url', '').strip()
    is_active = data.get('is_active', True)
    
    # Check for duplicate name
    existing = Category.query.filter_by(name_en=name_en).first()
    if existing:
        return jsonify({'message': f'Category with name "{name_en}" already exists'}), 400
        
    category = Category(
        name_en=name_en,
        name_hi=name_hi,
        name_mr=name_mr,
        image_url=image_url if image_url else None,
        is_active=is_active
    )
    db.session.add(category)
    db.session.commit()
    
    # Invalidate Cache
    cache.clear_pattern("categories:*")
    cache.clear_pattern("products:*")
    
    try:
        socketio.emit('product_updated', {'category_id': category.id, 'category': category.to_dict()})
    except Exception as se:
        print(f"Socket emit failed: {se}")
    
    return jsonify({
        'message': 'Category created successfully',
        'category': category.to_dict()
    }), 201

@categories_bp.route('/<int:category_id>', methods=['PUT'])
@admin_required
def update_category(category_id):
    """Update an existing category (Admin only)"""
    category = Category.query.get(category_id)
    if not category:
        return jsonify({'message': 'Category not found'}), 404
        
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No data provided'}), 400
        
    if 'name_en' in data:
        name_en = data['name_en'].strip()
        if name_en != category.name_en:
            existing = Category.query.filter_by(name_en=name_en).first()
            if existing:
                return jsonify({'message': f'Category with name "{name_en}" already exists'}), 400
            category.name_en = name_en
            
    if 'name_hi' in data:
        category.name_hi = data['name_hi'].strip()
    if 'name_mr' in data:
        category.name_mr = data['name_mr'].strip()
    if 'image_url' in data:
        category.image_url = data['image_url'].strip() if data['image_url'] else None
    if 'is_active' in data:
        category.is_active = bool(data['is_active'])
        
    db.session.commit()
    # Invalidate Cache
    cache.clear_pattern("categories:*")
    cache.clear_pattern("products:*")
    
    try:
        socketio.emit('product_updated', {'category_id': category.id, 'category': category.to_dict()})
    except Exception as se:
        print(f"Socket emit failed: {se}")
    return jsonify({
        'message': 'Category updated successfully',
        'category': category.to_dict()
    }), 200

@categories_bp.route('/<int:category_id>', methods=['DELETE'])
@admin_required
def delete_category(category_id):
    """Delete a category (Admin only)"""
    category = Category.query.get(category_id)
    if not category:
        return jsonify({'message': 'Category not found'}), 404
        
    db.session.delete(category)
    db.session.commit()
    # Invalidate Cache
    cache.clear_pattern("categories:*")
    cache.clear_pattern("products:*")
    
    try:
        socketio.emit('product_updated', {'category_id': category_id, 'category_deleted': True})
    except Exception as se:
        print(f"Socket emit failed: {se}")
    return jsonify({'message': 'Category deleted successfully'}), 200
