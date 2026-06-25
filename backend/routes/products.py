import os
import uuid
from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
from backend.database import db, Product, Category, InventoryLog, ProductImage
from backend.utils.auth_helper import admin_required
from backend.socket_service import socketio
from backend.utils.cache import cache
from sqlalchemy.orm import joinedload

products_bp = Blueprint('products', __name__)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in current_app.config['ALLOWED_EXTENSIONS']

@products_bp.route('', methods=['GET'])
def get_products():
    """Get products with search, pagination, and category filtering"""
    category_id = request.args.get('category_id', type=int)
    search_query = request.args.get('search', '').strip()
    show_all = request.args.get('all', 'false').lower() == 'true'
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    cache_key = f"products:list:{category_id}:{search_query}:{show_all}:{page}:{per_page}"
    cached = cache.get(cache_key)
    if cached is not None:
        return jsonify(cached), 200
        
    query = Product.query.options(joinedload(Product.category))
    
    # Filter by category
    if category_id:
        query = query.filter_by(category_id=category_id)
        
    # Search in English, Hindi, and Marathi
    if search_query:
        search_filter = (
            Product.name_en.ilike(f'%{search_query}%') |
            Product.name_hi.ilike(f'%{search_query}%') |
            Product.name_mr.ilike(f'%{search_query}%') |
            Product.description_en.ilike(f'%{search_query}%') |
            Product.description_hi.ilike(f'%{search_query}%') |
            Product.description_mr.ilike(f'%{search_query}%')
        )
        query = query.filter(search_filter)
        
    # Visibility filter
    if not show_all:
        query = query.join(Category, Product.category_id == Category.id).filter(
            Product.is_visible == True,
            Category.is_active == True
        )
        
    paginated_products = query.paginate(page=page, per_page=per_page, error_out=False)
    
    res_dict = {
        'products': [p.to_dict() for p in paginated_products.items],
        'total': paginated_products.total,
        'page': paginated_products.page,
        'pages': paginated_products.pages,
        'per_page': paginated_products.per_page
    }
    
    cache.set(cache_key, res_dict, timeout=600)
    return jsonify(res_dict), 200

@products_bp.route('/<int:product_id>', methods=['GET'])
def get_product(product_id):
    """Fetch single product details"""
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'message': 'Product not found'}), 404
    return jsonify(product.to_dict()), 200

@products_bp.route('', methods=['POST'])
@admin_required
def create_product():
    """Create a new product (Admin only)"""
    data = request.get_json()
    if not data or not all(k in data for k in ('name_en', 'name_hi', 'name_mr', 'price', 'unit')):
        return jsonify({'message': 'Missing required fields'}), 400
        
    category_id = data.get('category_id')
    if category_id:
        category = Category.query.get(category_id)
        if not category:
            return jsonify({'message': 'Invalid category ID'}), 400
            
    try:
        price = float(data['price'])
        discount_price = float(data['discount_price']) if data.get('discount_price') else None
        stock = float(data.get('stock_quantity', 0))
    except ValueError:
        return jsonify({'message': 'Invalid price or stock values'}), 400
        
    product = Product(
        category_id=category_id,
        name_en=data['name_en'].strip(),
        name_hi=data['name_hi'].strip(),
        name_mr=data['name_mr'].strip(),
        description_en=data.get('description_en', '').strip(),
        description_hi=data.get('description_hi', '').strip(),
        description_mr=data.get('description_mr', '').strip(),
        price=price,
        discount_price=discount_price,
        stock_quantity=stock,
        unit=data['unit'].strip(),
        is_visible=data.get('is_visible', True),
        image_url=data.get('image_url', '').strip()
    )
    
    db.session.add(product)
    db.session.commit() # Save first to get ID
    
    # Clear cache
    cache.clear_pattern("products:*")
    
    # Log initial inventory
    if stock > 0:
        inv_log = InventoryLog(
            product_id=product.id,
            quantity_changed=stock,
            change_type='Admin Restock',
            notes='Initial stock load'
        )
        db.session.add(inv_log)
        db.session.commit()
        
    try:
        socketio.emit('product_updated', product.to_dict())
        if stock > 0:
            socketio.emit('inventory_updated', product.to_dict())
    except Exception as se:
        print(f"Socket emit failed: {se}")
        
    return jsonify({
        'message': 'Product created successfully',
        'product': product.to_dict()
    }), 201

@products_bp.route('/<int:product_id>', methods=['PUT'])
@admin_required
def update_product(product_id):
    """Update an existing product (Admin only)"""
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'message': 'Product not found'}), 404
        
    data = request.get_json()
    if not data:
        return jsonify({'message': 'No data provided'}), 400
        
    if 'category_id' in data:
        cat_id = data['category_id']
        if cat_id:
            category = Category.query.get(cat_id)
            if not category:
                return jsonify({'message': 'Invalid category ID'}), 400
        product.category_id = cat_id
        
    if 'name_en' in data:
        product.name_en = data['name_en'].strip()
    if 'name_hi' in data:
        product.name_hi = data['name_hi'].strip()
    if 'name_mr' in data:
        product.name_mr = data['name_mr'].strip()
    if 'description_en' in data:
        product.description_en = data['description_en'].strip()
    if 'description_hi' in data:
        product.description_hi = data['description_hi'].strip()
    if 'description_mr' in data:
        product.description_mr = data['description_mr'].strip()
        
    if 'price' in data:
        try:
            product.price = float(data['price'])
        except ValueError:
            return jsonify({'message': 'Invalid price'}), 400
            
    if 'discount_price' in data:
        try:
            product.discount_price = float(data['discount_price']) if data['discount_price'] else None
        except ValueError:
            return jsonify({'message': 'Invalid discount price'}), 400
            
    if 'unit' in data:
        product.unit = data['unit'].strip()
        
    if 'is_visible' in data:
        product.is_visible = bool(data['is_visible'])
        
    if 'image_url' in data:
        product.image_url = data['image_url'].strip() if data['image_url'] else None
        
    # Handling manual stock adjustments from main edit
    if 'stock_quantity' in data:
        try:
            new_stock = float(data['stock_quantity'])
            diff = new_stock - float(product.stock_quantity)
            if diff != 0:
                product.stock_quantity = new_stock
                log = InventoryLog(
                    product_id=product.id,
                    quantity_changed=diff,
                    change_type='Correction',
                    notes='Manual stock edit'
                )
                db.session.add(log)
        except ValueError:
            return jsonify({'message': 'Invalid stock quantity'}), 400
            
    db.session.commit()
    # Clear cache
    cache.clear_pattern("products:*")
    try:
        socketio.emit('product_updated', product.to_dict())
        if 'stock_quantity' in data:
            socketio.emit('inventory_updated', product.to_dict())
    except Exception as se:
        print(f"Socket emit failed: {se}")
    return jsonify({
        'message': 'Product updated successfully',
        'product': product.to_dict()
    }), 200

@products_bp.route('/<int:product_id>', methods=['DELETE'])
@admin_required
def delete_product(product_id):
    """Delete a product (Admin only)"""
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'message': 'Product not found'}), 404
        
    db.session.delete(product)
    db.session.commit()
    # Clear cache
    cache.clear_pattern("products:*")
    try:
        socketio.emit('product_updated', {'id': product_id, 'deleted': True})
    except Exception as se:
        print(f"Socket emit failed: {se}")
    return jsonify({'message': 'Product deleted successfully'}), 200

@products_bp.route('/<int:product_id>/stock', methods=['POST'])
@admin_required
def adjust_stock(product_id):
    """Explicitly adjust stock quantity of a product (Admin only)"""
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'message': 'Product not found'}), 404
        
    data = request.get_json()
    if not data or 'adjustment' not in data:
        return jsonify({'message': 'Adjustment quantity is required'}), 400
        
    try:
        adj = float(data['adjustment'])
        change_type = data.get('change_type', 'Admin Restock')
        notes = data.get('notes', 'Manual adjustment')
    except ValueError:
        return jsonify({'message': 'Invalid adjustment quantity'}), 400
        
    product.stock_quantity = float(product.stock_quantity) + adj
    
    inv_log = InventoryLog(
        product_id=product.id,
        quantity_changed=adj,
        change_type=change_type,
        notes=notes
    )
    db.session.add(inv_log)
    db.session.commit()
    # Clear cache
    cache.clear_pattern("products:*")
    # Invalidate reports stats cache as inventory stock levels altered
    cache.delete("reports:stats")
    
    try:
        socketio.emit('inventory_updated', product.to_dict())
        socketio.emit('product_updated', product.to_dict())
    except Exception as se:
        print(f"Socket emit failed: {se}")
    
    return jsonify({
        'message': 'Stock updated successfully',
        'product': product.to_dict()
    }), 200

@products_bp.route('/upload-image', methods=['POST'])
@admin_required
def upload_image():
    """Endpoint for uploading product images (Admin only)"""
    if 'image' not in request.files:
        return jsonify({'message': 'No image file provided'}), 400
        
    file = request.files['image']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
        
    if file and allowed_file(file.filename):
        try:
            # Create folder if it doesn't exist
            os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Generate a unique base name to save as WebP
            unique_id = uuid.uuid4().hex
            webp_filename = f"{unique_id}.webp"
            card_filename = f"{unique_id}_card.webp"
            thumb_filename = f"{unique_id}_thumb.webp"
            
            main_path = os.path.join(current_app.config['UPLOAD_FOLDER'], webp_filename)
            card_path = os.path.join(current_app.config['UPLOAD_FOLDER'], card_filename)
            thumb_path = os.path.join(current_app.config['UPLOAD_FOLDER'], thumb_filename)
            
            # Process image with Pillow
            from PIL import Image
            img = Image.open(file)
            
            # Handle alpha channel (transparency) if converting to RGB
            if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
                # Create a white background for transparent parts
                background = Image.new('RGB', img.size, (255, 255, 255))
                background.paste(img, mask=img.split()[3] if img.mode == 'RGBA' else img.convert('RGBA').split()[3])
                img = background
            else:
                img = img.convert('RGB')
            
            import io
            import base64
            
            # 1. Main image: Resize image to fit within max size 800x800 and encode to Base64
            main_buffer = io.BytesIO()
            main_img = img.copy()
            main_img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            main_img.save(main_buffer, format="WEBP", quality=80)
            main_base64 = base64.b64encode(main_buffer.getvalue()).decode('utf-8')
            image_url = f"data:image/webp;base64,{main_base64}"
            
            # 2. Card image: Resize to fit within 300x300 and encode to Base64
            card_buffer = io.BytesIO()
            card_img = img.copy()
            card_img.thumbnail((300, 300), Image.Resampling.LANCZOS)
            card_img.save(card_buffer, format="WEBP", quality=75)
            card_base64 = base64.b64encode(card_buffer.getvalue()).decode('utf-8')
            card_image_url = f"data:image/webp;base64,{card_base64}"
            
            # 3. Thumbnail image: Resize to fit within 100x100 and encode to Base64
            thumb_buffer = io.BytesIO()
            thumb_img = img.copy()
            thumb_img.thumbnail((100, 100), Image.Resampling.LANCZOS)
            thumb_img.save(thumb_buffer, format="WEBP", quality=70)
            thumb_base64 = base64.b64encode(thumb_buffer.getvalue()).decode('utf-8')
            thumbnail_url = f"data:image/webp;base64,{thumb_base64}"
            
            # Keep saving to disk as a local cache/fallback
            try:
                os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
                main_path = os.path.join(current_app.config['UPLOAD_FOLDER'], webp_filename)
                card_path = os.path.join(current_app.config['UPLOAD_FOLDER'], card_filename)
                thumb_path = os.path.join(current_app.config['UPLOAD_FOLDER'], thumb_filename)
                
                with open(main_path, "wb") as f:
                    f.write(main_buffer.getvalue())
                with open(card_path, "wb") as f:
                    f.write(card_buffer.getvalue())
                with open(thumb_path, "wb") as f:
                    f.write(thumb_buffer.getvalue())
            except Exception as disk_err:
                print(f"Warning: Failed to write static uploads to disk fallback: {disk_err}")
            
            return jsonify({
                'message': 'Image uploaded and optimized successfully',
                'image_url': image_url,
                'card_image_url': card_image_url,
                'thumbnail_url': thumbnail_url
            }), 200
        except Exception as e:
            return jsonify({'message': f'Image optimization failed: {str(e)}'}), 500
            
    return jsonify({'message': 'Invalid file extension allowed'}), 400
