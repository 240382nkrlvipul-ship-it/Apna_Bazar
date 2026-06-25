import os
from flask import Blueprint, request, jsonify, g
from backend.database import db, Customer, Cart, CartItem, Product, Order, OrderItem, Village, Payment, InventoryLog, Notification, CustomerLocation
from backend.utils.auth_helper import token_required, admin_required
from backend.utils.distance import calculate_haversine_distance
from backend.config import Config
from backend.socket_service import socketio
from datetime import datetime
from sqlalchemy.orm import joinedload
from backend.utils.cache import cache


orders_bp = Blueprint('orders', __name__)

# ==========================================
# CART ROUTES
# ==========================================

@orders_bp.route('/cart', methods=['GET'])
@token_required
def get_cart():
    """Retrieve the logged-in customer's cart"""
    if g.user_role != 'customer':
        return jsonify({'message': 'Cart is only for customers'}), 403
        
    cart = Cart.query.filter_by(customer_id=g.user_id).first()
    if not cart:
        cart = Cart(customer_id=g.user_id)
        db.session.add(cart)
        db.session.commit()
        
    return jsonify(cart.to_dict()), 200

@orders_bp.route('/cart/items', methods=['POST'])
@token_required
def add_to_cart():
    """Add or update product quantity in customer's cart"""
    if g.user_role != 'customer':
        return jsonify({'message': 'Cart is only for customers'}), 403
        
    data = request.get_json()
    if not data or 'product_id' not in data or 'quantity' not in data:
        return jsonify({'message': 'Product ID and quantity are required'}), 400
        
    product_id = data['product_id']
    try:
        qty = float(data['quantity'])
    except ValueError:
        return jsonify({'message': 'Quantity must be a number'}), 400
        
    if qty <= 0:
        return jsonify({'message': 'Quantity must be greater than zero'}), 400
        
    product = Product.query.get(product_id)
    if not product:
        return jsonify({'message': 'Product not found'}), 404
        
    # Check if stock is available
    if float(product.stock_quantity) < qty:
        return jsonify({
            'message': f'Insufficient stock. Only {product.stock_quantity} {product.unit} available.',
            'available_stock': float(product.stock_quantity)
        }), 400
        
    cart = Cart.query.filter_by(customer_id=g.user_id).first()
    if not cart:
        cart = Cart(customer_id=g.user_id)
        db.session.add(cart)
        db.session.commit()
        
    item = CartItem.query.filter_by(cart_id=cart.id, product_id=product_id).first()
    if item:
        item.quantity = qty
    else:
        item = CartItem(cart_id=cart.id, product_id=product_id, quantity=qty)
        db.session.add(item)
        
    db.session.commit()
    return jsonify(cart.to_dict()), 200

@orders_bp.route('/cart/items/<int:item_id>', methods=['DELETE'])
@token_required
def remove_from_cart(item_id):
    """Remove item from cart"""
    if g.user_role != 'customer':
        return jsonify({'message': 'Cart is only for customers'}), 403
        
    cart = Cart.query.filter_by(customer_id=g.user_id).first()
    if not cart:
        return jsonify({'message': 'Cart not found'}), 404
        
    item = CartItem.query.filter_by(id=item_id, cart_id=cart.id).first()
    if not item:
        return jsonify({'message': 'Cart item not found'}), 404
        
    db.session.delete(item)
    db.session.commit()
    
    return jsonify(cart.to_dict()), 200

@orders_bp.route('/cart/clear', methods=['DELETE'])
@token_required
def clear_cart():
    """Clear customer cart"""
    if g.user_role != 'customer':
        return jsonify({'message': 'Cart is only for customers'}), 403
        
    cart = Cart.query.filter_by(customer_id=g.user_id).first()
    if not cart:
        return jsonify({'message': 'Cart not found'}), 404
        
    CartItem.query.filter_by(cart_id=cart.id).delete()
    db.session.commit()
    
    return jsonify(cart.to_dict()), 200


# ==========================================
# ORDER ROUTES
# ==========================================

@orders_bp.route('/orders', methods=['POST'])
@token_required
def place_order():
    """Place a new order (Checkout)"""
    if g.user_role != 'customer':
        return jsonify({'message': 'Only customers can place orders'}), 403
        
    data = request.get_json()
    if not data or not all(k in data for k in ('customer_name', 'customer_mobile', 'village_id', 'payment_method')):
        return jsonify({'message': 'Missing checkout details'}), 400
        
    # Geolocation permission check
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    if latitude is None or longitude is None:
        return jsonify({'message': 'Location permission is required to place an order. Please allow location access.'}), 400
        
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (ValueError, TypeError):
        return jsonify({'message': 'Invalid latitude or longitude coordinate values'}), 400
        
    # Village validation
    village_id = data['village_id']
    village = Village.query.get(village_id)
    if not village or not village.is_allowed:
        return jsonify({'message': 'Delivery is not available in the selected village'}), 400
        
    # Delivery Radius Validation (within configured limit, e.g. 15 KM)
    distance = calculate_haversine_distance(Config.SHOP_LATITUDE, Config.SHOP_LONGITUDE, lat, lon)
    if distance > Config.DELIVERY_RADIUS_KM:
        return jsonify({'message': 'Sorry, delivery is currently unavailable at your location.'}), 400
        
    # Extract address fields
    house_number = data.get('house_number', '').strip()
    area_street = data.get('area_street', '').strip()
    landmark = data.get('landmark', '').strip()
    
    if house_number and area_street:
        delivery_address = f"House No: {house_number}, Area/Street: {area_street}"
        if landmark:
            delivery_address += f", Landmark: {landmark}"
        delivery_address += f", Village: {village.name_en}"
    elif 'delivery_address' in data:
        delivery_address = data['delivery_address'].strip()
    else:
        return jsonify({'message': 'House number and Area/Street are required'}), 400
        
    cart = Cart.query.filter_by(customer_id=g.user_id).first()
    if not cart or not cart.items:
        return jsonify({'message': 'Your shopping cart is empty'}), 400
        
    # Verify stock availability for all items before making any modifications
    out_of_stock = []
    items_to_process = []
    for item in cart.items:
        product = item.product
        if float(product.stock_quantity) < float(item.quantity):
            out_of_stock.append({
                'product_id': product.id,
                'name_en': product.name_en,
                'available_stock': float(product.stock_quantity),
                'requested': float(item.quantity)
            })
        else:
            items_to_process.append((item, product))
            
    if out_of_stock:
        return jsonify({
            'message': 'Some products in your cart are out of stock or have insufficient quantity.',
            'out_of_stock': out_of_stock
        }), 400
        
    total_amount = 0.00
    order_items = []
    
    # Process order items and deduct stock
    for item, product in items_to_process:
        price = float(product.discount_price if product.discount_price else product.price)
        qty = float(item.quantity)
        total_amount += price * qty
        
        # Deduct stock
        product.stock_quantity = float(product.stock_quantity) - qty
        
        # Log inventory change
        inv_log = InventoryLog(
            product_id=product.id,
            quantity_changed=-qty,
            change_type='Order Deduct',
            notes=f'Order placement'
        )
        db.session.add(inv_log)
        
        # Build order item DTO
        o_item = OrderItem(
            product_id=product.id,
            product_name_en=product.name_en,
            product_name_hi=product.name_hi,
            product_name_mr=product.name_mr,
            price=price,
            quantity=qty,
            unit=product.unit
        )
        order_items.append(o_item)
        
    # Add delivery charge from selected village
    delivery_charge = float(village.delivery_charge)
    total_amount += delivery_charge
    
    # Save/update customer address
    existing_loc = CustomerLocation.query.filter_by(customer_id=g.user_id).first()
    if not existing_loc:
        existing_loc = CustomerLocation(customer_id=g.user_id)
        db.session.add(existing_loc)
    existing_loc.latitude = lat
    existing_loc.longitude = lon
    existing_loc.address = delivery_address
    existing_loc.landmark = landmark
        
    # Create order record
    order = Order(
        customer_id=g.user_id,
        village_id=village_id,
        customer_name=data['customer_name'].strip(),
        customer_mobile=data['customer_mobile'].strip(),
        delivery_address=delivery_address,
        order_notes=data.get('order_notes', '').strip(),
        payment_method=data['payment_method'],
        payment_status='Pending',
        order_status='Order Received',
        total_amount=total_amount,
        delivery_charge=delivery_charge,
        latitude=lat,
        longitude=lon,
        delivery_status='Pending'
    )
    db.session.add(order)
    db.session.commit() # Save to get order ID
    
    # Assign order ID to items and save them
    for item in order_items:
        item.order_id = order.id
        db.session.add(item)
        
    # Create payment record
    payment = Payment(
        order_id=order.id,
        payment_method=data['payment_method'],
        amount=total_amount,
        status='Pending'
    )
    db.session.add(payment)
    
    # Clear customer cart
    CartItem.query.filter_by(cart_id=cart.id).delete()
    
    # Store Admin and Customer Notifications (which simulates WhatsApp integration)
    admin_notif = Notification(
        user_type='admin',
        title_en=f"New Order Received! #{order.id}",
        title_hi=f"नया ऑर्डर प्राप्त हुआ! #{order.id}",
        title_mr=f"नवीन ऑर्डर प्राप्त झाली! #{order.id}",
        message_en=f"Order #{order.id} placed by {order.customer_name} from village {village.name_en}. Total: ₹{total_amount:.2f}.",
        message_hi=f"ऑर्डर #{order.id} {order.customer_name} द्वारा गाँव {village.name_hi} से की गई। कुल: ₹{total_amount:.2f}.",
        message_mr=f"ऑर्डर #{order.id} {order.customer_name} द्वारे गाव {village.name_mr} वरून आली. एकूण: ₹{total_amount:.2f}."
    )
    db.session.add(admin_notif)
    
    cust_notif = Notification(
        user_id=g.user_id,
        user_type='customer',
        title_en=f"Order Confirmed #{order.id}",
        title_hi=f"ऑर्डर की पुष्टि हुई #{order.id}",
        title_mr=f"ऑर्डरची पुष्टी झाली #{order.id}",
        message_en=f"Thank you, {order.customer_name}! Your order #{order.id} has been received and is being prepared.",
        message_hi=f"धन्यवाद, {order.customer_name}! आपका ऑर्डर #{order.id} प्राप्त हो गया है और तैयार किया जा रहा है.",
        message_mr=f"धन्यवाद, {order.customer_name}! तुमची ऑर्डर #{order.id} प्राप्त झाली आहे आणि तयारी सुरू आहे."
    )
    db.session.add(cust_notif)
    db.session.commit()
    
    # Simulate WhatsApp notifications in server logs
    frontend_url = Config.FRONTEND_URL
    whatsapp_msg_cust = (
        f"WhatsApp SIMULATION (Customer): Sent to {order.customer_mobile}\n"
        f"Hello {order.customer_name}, your order #{order.id} of Rs.{total_amount:.2f} is CONFIRMED. "
        f"Status: Order Received. Track it here: {frontend_url}/orders/{order.id}"
    )
    whatsapp_msg_admin = (
        f"WhatsApp SIMULATION (Admin Notify): Sent to Store Manager (+91 9876543210)\n"
        f"Alert: New order #{order.id} placed by {order.customer_name} (+91 {order.customer_mobile}) "
        f"for village {village.name_en}. Total: Rs.{total_amount:.2f} (COD)."
    )
    print("\n" + "*"*80)
    print(whatsapp_msg_cust)
    print("-"*80)
    print(whatsapp_msg_admin)
    print("*"*80 + "\n")
    
    # Clear cache since order placed and stock levels changed
    cache.delete("reports:stats")
    cache.clear_pattern("products:*")
    
    # Emit real-time Socket.IO alert to Admin Dashboards
    try:
        socketio.emit('new_order', order.to_dict(), to='admins')
        socketio.emit('customer_location_updated', existing_loc.to_dict(), to='admins')
        for item in order.items:
            if item.product_id:
                product = Product.query.get(item.product_id)
                if product:
                    socketio.emit('inventory_updated', product.to_dict())
    except Exception as e:
        print(f"Socket.io failed to emit order placement events: {e}")
        
    return jsonify({
        'message': 'Order placed successfully',
        'order': order.to_dict(),
        'whatsapp_simulated': [whatsapp_msg_cust, whatsapp_msg_admin]
    }), 201

@orders_bp.route('/orders', methods=['GET'])
@token_required
def get_orders():
    """List orders for admin or customer with pagination"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    query = Order.query.options(joinedload(Order.items))
    
    # If admin, fetch all with optional filters
    if g.user_role in ['admin', 'superadmin', 'staff']:
        status_filter = request.args.get('status')
        customer_id = request.args.get('customer_id', type=int)
        village_id = request.args.get('village_id', type=int)
        search_query = request.args.get('search', '').strip()
        
        if status_filter and status_filter != 'All':
            query = query.filter_by(order_status=status_filter)
        if customer_id:
            query = query.filter_by(customer_id=customer_id)
        if village_id:
            query = query.filter_by(village_id=village_id)
        if search_query:
            if search_query.isdigit():
                query = query.filter(
                    (Order.id == int(search_query)) | 
                    (Order.customer_mobile.ilike(f'%{search_query}%'))
                )
            else:
                query = query.filter(Order.customer_name.ilike(f'%{search_query}%'))
            
        paginated = query.order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    else:
        # Customer fetches only their own
        paginated = query.filter_by(customer_id=g.user_id).order_by(Order.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        
    return jsonify({
        'orders': [o.to_dict() for o in paginated.items],
        'total': paginated.total,
        'page': paginated.page,
        'pages': paginated.pages
    }), 200

@orders_bp.route('/orders/<int:order_id>', methods=['GET'])
@token_required
def get_order_details(order_id):
    """Retrieve details of a single order"""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'message': 'Order not found'}), 404
        
    # Check permissions (customer must own the order)
    if g.user_role == 'customer' and order.customer_id != g.user_id:
        return jsonify({'message': 'Access denied'}), 403
        
    return jsonify(order.to_dict()), 200

@orders_bp.route('/orders/<int:order_id>/status', methods=['PUT'])
@admin_required
def update_order_status(order_id):
    """Update order status (Admin only) and handle cancellations/payments"""
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'message': 'Order not found'}), 404
        
    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({'message': 'Order status is required'}), 400
        
    new_status = data['status'].strip()
    valid_statuses = ['Order Received', 'Preparing', 'Packed', 'Out For Delivery', 'Delivered', 'Cancelled']
    if new_status not in valid_statuses:
        return jsonify({'message': 'Invalid order status value'}), 400
        
    old_status = order.order_status
    if old_status == new_status:
        return jsonify({'message': 'Status is already set to this value', 'order': order.to_dict()}), 200
        
    # If transitioning to Cancelled, RESTOCK items
    if new_status == 'Cancelled' and old_status != 'Cancelled':
        for item in order.items:
            if item.product_id:
                product = Product.query.get(item.product_id)
                if product:
                    product.stock_quantity = float(product.stock_quantity) + float(item.quantity)
                    log = InventoryLog(
                        product_id=product.id,
                        quantity_changed=float(item.quantity),
                        change_type='Correction',
                        notes=f'Restock due to order #{order.id} cancellation'
                    )
                    db.session.add(log)
                    
        # Update payment status if cancelled
        payment = Payment.query.filter_by(order_id=order.id).first()
        if payment:
            payment.status = 'Failed'
        order.payment_status = 'Failed'
        
    # If transition to Delivered, mark payment as paid if COD
    elif new_status == 'Delivered':
        payment = Payment.query.filter_by(order_id=order.id).first()
        if payment:
            payment.status = 'Success'
        order.payment_status = 'Paid'
        
    order.order_status = new_status
    
    # Store customer status notification
    cust_notif = Notification(
        user_id=order.customer_id,
        user_type='customer',
        title_en=f"Order Status Update #{order.id}",
        title_hi=f"ऑर्डर की स्थिति में बदलाव #{order.id}",
        title_mr=f"ऑर्डर स्थिती बदलली #{order.id}",
        message_en=f"Your order #{order.id} status is updated to '{new_status}'.",
        message_hi=f"आपका ऑर्डर #{order.id} अब '{new_status}' की स्थिति में है।",
        message_mr=f"तुमच्या ऑर्डरची #{order.id} स्थिती आता '{new_status}' आहे."
    )
    db.session.add(cust_notif)
    db.session.commit()
    
    # Simulate status update WhatsApp
    whatsapp_msg_cust = (
        f"WhatsApp SIMULATION (Customer): Sent to {order.customer_mobile}\n"
        f"Hi {order.customer_name}, status of order #{order.id} has changed to: {new_status}. "
        f"Track here: {Config.FRONTEND_URL}/orders/{order.id}"
    )
    print("\n" + "="*80)
    print(whatsapp_msg_cust)
    print("="*80 + "\n")
    
    # Clear cache
    cache.delete("reports:stats")
    
    # Emit real-time update to customer and admin via Socket.IO rooms
    try:
        socketio.emit('order_status_updated', {
            'order_id': order.id,
            'status': new_status,
            'payment_status': order.payment_status
        }, to=f"order_{order.id}")
        socketio.emit('order_status_changed', {
            'order_id': order.id,
            'status': new_status,
            'payment_status': order.payment_status
        }, to='admins')
    except Exception as e:
        print(f"Socket.io failed to emit order_status_updated: {e}")
        
    return jsonify({
        'message': f'Order status updated to {new_status}',
        'order': order.to_dict(),
        'whatsapp_simulated': whatsapp_msg_cust
    }), 200

@orders_bp.route('/orders/<int:order_id>/reorder', methods=['POST'])
@token_required
def reorder_previous(order_id):
    """Reorder a past order by fetching and adding all items to customer's cart (clearing it first)"""
    if g.user_role != 'customer':
        return jsonify({'message': 'Only customers can reorder'}), 403
        
    order = Order.query.get(order_id)
    if not order or order.customer_id != g.user_id:
        return jsonify({'message': 'Order not found'}), 404
        
    # Get user's cart
    cart = Cart.query.filter_by(customer_id=g.user_id).first()
    if not cart:
        cart = Cart(customer_id=g.user_id)
        db.session.add(cart)
        db.session.commit()
        
    # Clear existing cart items
    CartItem.query.filter_by(cart_id=cart.id).delete()
    
    # Add old items to cart
    issues = []
    for item in order.items:
        if not item.product_id:
            issues.append(f"Product '{item.product_name_en}' is no longer available in store.")
            continue
            
        product = Product.query.get(item.product_id)
        if not product or not product.is_visible:
            issues.append(f"Product '{item.product_name_en}' is currently unavailable.")
            continue
            
        # Add to cart (up to available stock)
        qty_to_add = min(float(item.quantity), float(product.stock_quantity))
        if qty_to_add <= 0:
            issues.append(f"Product '{product.name_en}' is currently out of stock.")
            continue
            
        cart_item = CartItem(
            cart_id=cart.id,
            product_id=product.id,
            quantity=qty_to_add
        )
        db.session.add(cart_item)
        
        if qty_to_add < float(item.quantity):
            issues.append(f"Reduced quantity of '{product.name_en}' from {item.quantity} to {qty_to_add} {product.unit} due to stock limits.")
            
    db.session.commit()
    return jsonify({
        'message': 'Past order items loaded into cart',
        'cart': cart.to_dict(),
        'issues': issues
    }), 200

@orders_bp.route('/notifications', methods=['GET'])
@token_required
def get_notifications():
    """Retrieve notifications (Customer gets customer-specific, Admin gets admin-specific)"""
    if g.user_role in ['admin', 'superadmin', 'staff']:
        notifs = Notification.query.filter_by(user_type='admin').order_by(Notification.created_at.desc()).limit(50).all()
    else:
        notifs = Notification.query.filter_by(user_type='customer', user_id=g.user_id).order_by(Notification.created_at.desc()).limit(50).all()
        
    return jsonify([n.to_dict() for n in notifs]), 200

@orders_bp.route('/notifications/read-all', methods=['POST'])
@token_required
def read_all_notifications():
    """Mark all current notifications as read"""
    if g.user_role in ['admin', 'superadmin', 'staff']:
        db.session.query(Notification).filter(Notification.user_type == 'admin').update({Notification.is_read: True})
    else:
        db.session.query(Notification).filter(Notification.user_type == 'customer', Notification.user_id == g.user_id).update({Notification.is_read: True})
        
    db.session.commit()
    return jsonify({'message': 'All notifications marked as read'}), 200

@orders_bp.route('/saved-address', methods=['GET', 'POST'])
@token_required
def manage_saved_address():
    """Retrieve or update customer saved address"""
    if g.user_role != 'customer':
        return jsonify({'message': 'Only customers have saved addresses'}), 403
        
    if request.method == 'GET':
        loc = CustomerLocation.query.filter_by(customer_id=g.user_id).order_by(CustomerLocation.created_at.desc()).first()
        if not loc:
            return jsonify({'saved': False}), 200
        return jsonify({
            'saved': True,
            'address': {
                'latitude': loc.latitude,
                'longitude': loc.longitude,
                'address': loc.address,
                'landmark': loc.landmark
            }
        }), 200
        
    elif request.method == 'POST':
        data = request.get_json()
        if not data:
            return jsonify({'message': 'Missing data'}), 400
            
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        address = data.get('address', '').strip()
        landmark = data.get('landmark', '').strip()
        
        if latitude is None or longitude is None or not address:
            return jsonify({'message': 'Latitude, longitude and address are required'}), 400
            
        try:
            lat = float(latitude)
            lon = float(longitude)
        except ValueError:
            return jsonify({'message': 'Invalid latitude or longitude'}), 400
            
        loc = CustomerLocation.query.filter_by(customer_id=g.user_id).first()
        if not loc:
            loc = CustomerLocation(customer_id=g.user_id)
            db.session.add(loc)
            
        loc.latitude = lat
        loc.longitude = lon
        loc.address = address
        loc.landmark = landmark
        db.session.commit()
        
        return jsonify({
            'message': 'Address saved successfully',
            'address': {
                'latitude': loc.latitude,
                'longitude': loc.longitude,
                'address': loc.address,
                'landmark': loc.landmark
            }
        }), 200

@orders_bp.route('/previous-addresses', methods=['GET'])
@token_required
def get_previous_addresses():
    """Retrieve unique previous delivery addresses used by the customer in their past orders or saved location"""
    if g.user_role != 'customer':
        return jsonify({'message': 'Only customers have previous addresses'}), 403
        
    import re
    addresses = []
    seen = set()
    
    # 1. First check the active saved location
    loc = CustomerLocation.query.filter_by(customer_id=g.user_id).first()
    cust = Customer.query.get(g.user_id)
    cust_name = cust.name if (cust and cust.name) else 'Customer'
    cust_mobile = cust.mobile if (cust and cust.mobile) else ''
    
    if loc and loc.address:
        addr_str = loc.address.strip()
        key = (addr_str.lower(), round(loc.latitude, 5) if loc.latitude else 0.0, round(loc.longitude, 5) if loc.longitude else 0.0)
        seen.add(key)
        
        house_no, area_street, landmark = "", "", ""
        house_match = re.search(r"House\s*No:\s*([^,]+)", addr_str, re.IGNORECASE)
        area_match = re.search(r"Area/Street:\s*([^,]+)", addr_str, re.IGNORECASE)
        landmark_match = re.search(r"Landmark:\s*([^,]+)", addr_str, re.IGNORECASE)
        
        if house_match:
            house_no = house_match.group(1).strip()
        if area_match:
            area_street = area_match.group(1).strip()
        if landmark_match:
            landmark = landmark_match.group(1).strip()
            
        village_id = None
        village_match = re.search(r"Village:\s*([^,]+)", addr_str, re.IGNORECASE)
        if village_match:
            v_name = village_match.group(1).strip()
            v_rec = Village.query.filter(Village.name_en.ilike(v_name)).first()
            if v_rec:
                village_id = v_rec.id

        if not house_no and not area_street:
            area_street = addr_str
            
        addresses.append({
            'id': 0, # Saved location ID marker
            'customer_name': cust_name,
            'customer_mobile': cust_mobile,
            'house_number': house_no,
            'area_street': area_street,
            'landmark': landmark or loc.landmark or '',
            'village_id': village_id,
            'latitude': loc.latitude,
            'longitude': loc.longitude,
            'display_address': f"[Saved Address] {addr_str}"
        })
        
    # 2. Query previous orders placed by this customer
    orders = Order.query.filter_by(customer_id=g.user_id).order_by(Order.created_at.desc()).all()
    for o in orders:
        if not o.delivery_address:
            continue
            
        addr_str = o.delivery_address.strip()
        key = (addr_str.lower(), round(o.latitude, 5) if o.latitude else 0.0, round(o.longitude, 5) if o.longitude else 0.0)
        if key in seen:
            continue
        seen.add(key)
        
        house_no, area_street, landmark = "", "", ""
        house_match = re.search(r"House\s*No:\s*([^,]+)", addr_str, re.IGNORECASE)
        area_match = re.search(r"Area/Street:\s*([^,]+)", addr_str, re.IGNORECASE)
        landmark_match = re.search(r"Landmark:\s*([^,]+)", addr_str, re.IGNORECASE)
        
        if house_match:
            house_no = house_match.group(1).strip()
        if area_match:
            area_street = area_match.group(1).strip()
        if landmark_match:
            landmark = landmark_match.group(1).strip()
            
        if not house_no and not area_street:
            area_street = addr_str
            
        addresses.append({
            'id': o.id,
            'customer_name': o.customer_name,
            'customer_mobile': o.customer_mobile,
            'house_number': house_no,
            'area_street': area_street,
            'landmark': landmark,
            'village_id': o.village_id,
            'latitude': o.latitude,
            'longitude': o.longitude,
            'display_address': addr_str
        })
        
    return jsonify({'addresses': addresses}), 200
