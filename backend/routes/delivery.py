from flask import Blueprint, request, jsonify, g
from datetime import datetime, date
from werkzeug.security import generate_password_hash
from backend.database import db, Order, DeliveryAgent, DeliveryAssignment, Payment, Notification
from backend.utils.auth_helper import admin_required, agent_required
from backend.socket_service import socketio
from sqlalchemy.orm import joinedload
from backend.utils.cache import cache

delivery_bp = Blueprint('delivery', __name__)

# ==========================================
# ADMIN DELIVERY AGENT CRUD ROUTES
# ==========================================

@delivery_bp.route('/agents', methods=['GET'])
@admin_required
def get_agents():
    """List all delivery agents with their stats (paginated)"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    paginated = DeliveryAgent.query.order_by(DeliveryAgent.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    results = []
    for agent in paginated.items:
        # Calculate stats
        assigned_count = DeliveryAssignment.query.filter_by(delivery_agent_id=agent.id).count()
        delivered_count = DeliveryAssignment.query.filter_by(delivery_agent_id=agent.id, status='Delivered').count()
        
        results.append({
            'id': agent.id,
            'name': agent.name,
            'mobile': agent.mobile,
            'status': agent.status,
            'assigned_orders': assigned_count,
            'delivered_orders': delivered_count,
            'created_at': agent.created_at.isoformat() if agent.created_at else None
        })
    return jsonify({
        'agents': results,
        'total': paginated.total,
        'page': paginated.page,
        'pages': paginated.pages
    }), 200

@delivery_bp.route('/agents', methods=['POST'])
@admin_required
def create_agent():
    """Create a new delivery agent"""
    data = request.get_json()
    if not data or not all(k in data for k in ('name', 'mobile', 'password')):
        return jsonify({'message': 'Missing agent details'}), 400
        
    name = data['name'].strip()
    mobile = data['mobile'].strip()
    password = data['password'].strip()
    
    # Check if mobile exists
    existing = DeliveryAgent.query.filter_by(mobile=mobile).first()
    if existing:
        return jsonify({'message': 'Delivery agent with this mobile number already exists'}), 400
        
    agent = DeliveryAgent(
        name=name,
        mobile=mobile,
        password_hash=generate_password_hash(password),
        status=data.get('status', 'Active')
    )
    db.session.add(agent)
    db.session.commit()
    
    return jsonify({'message': 'Delivery agent created successfully', 'agent': agent.to_dict()}), 201

@delivery_bp.route('/agents/<int:agent_id>', methods=['PUT'])
@admin_required
def update_agent(agent_id):
    """Update delivery agent details"""
    agent = DeliveryAgent.query.get(agent_id)
    if not agent:
        return jsonify({'message': 'Delivery agent not found'}), 404
        
    data = request.get_json()
    if not data:
        return jsonify({'message': 'Missing data'}), 400
        
    if 'name' in data:
        agent.name = data['name'].strip()
    if 'mobile' in data:
        mobile = data['mobile'].strip()
        existing = DeliveryAgent.query.filter_by(mobile=mobile).first()
        if existing and existing.id != agent_id:
            return jsonify({'message': 'Mobile number is already used by another agent'}), 400
        agent.mobile = mobile
    if 'password' in data and data['password'].strip():
        agent.password_hash = generate_password_hash(data['password'].strip())
    if 'status' in data:
        agent.status = data['status']
        
    db.session.commit()
    return jsonify({'message': 'Delivery agent updated successfully', 'agent': agent.to_dict()}), 200

# ==========================================
# ADMIN ASSIGNMENT & ANALYTICS ROUTES
# ==========================================

@delivery_bp.route('/assignments', methods=['POST'])
@admin_required
def assign_order():
    """Assign an order to a delivery agent"""
    data = request.get_json()
    if not data or not all(k in data for k in ('order_id', 'delivery_agent_id')):
        return jsonify({'message': 'Missing order_id or delivery_agent_id'}), 400
        
    order_id = data['order_id']
    agent_id = data['delivery_agent_id']
    
    order = Order.query.get(order_id)
    if not order:
        return jsonify({'message': 'Order not found'}), 404
        
    agent = DeliveryAgent.query.get(agent_id)
    if not agent:
        return jsonify({'message': 'Delivery agent not found'}), 404
        
    if agent.status != 'Active':
        return jsonify({'message': 'Cannot assign order to an inactive delivery agent'}), 400
        
    # Check if there is an existing assignment
    assignment = DeliveryAssignment.query.filter_by(order_id=order_id).first()
    if not assignment:
        assignment = DeliveryAssignment(order_id=order_id, delivery_agent_id=agent_id)
        db.session.add(assignment)
    else:
        assignment.delivery_agent_id = agent_id
        assignment.status = 'Assigned'
        assignment.assigned_at = datetime.utcnow()
        assignment.delivered_at = None
        
    # Update Order delivery details
    order.delivery_agent_id = agent_id
    order.delivery_status = 'Assigned'
    order.order_status = 'Assigned To Delivery Agent'
    
    # Store customer and agent notifications
    cust_notif = Notification(
        user_id=order.customer_id,
        user_type='customer',
        title_en=f"Order Assigned to Delivery Agent",
        title_hi=f"ऑर्डर डिलीवरी एजेंट को सौंपा गया",
        title_mr=f"ऑर्डर डिलिव्हरी एजंटकडे सोपवली",
        message_en=f"Your order #{order.id} has been assigned to delivery agent {agent.name} ({agent.mobile}).",
        message_hi=f"आपका ऑर्डर #{order.id} डिलीवरी एजेंट {agent.name} ({agent.mobile}) को सौंप दिया गया है।",
        message_mr=f"तुमची ऑर्डर #{order.id} डिलिव्हरी एजंट {agent.name} ({agent.mobile}) कडे सोपवली आहे."
    )
    db.session.add(cust_notif)
    
    db.session.commit()
    
    # Invalidate Stats cache
    cache.delete("reports:stats")
    
    # Emit real-time Socket.IO alerts
    try:
        # Notify the specific agent
        socketio.emit('agent_assigned', {
            'order_id': order.id,
            'agent_id': agent.id,
            'agent_name': agent.name,
            'agent_mobile': agent.mobile,
            'status': 'Assigned To Delivery Agent'
        }, to=f"agent_{agent.id}")
        
        socketio.emit('order_assigned', {
            'order_id': order.id,
            'agent_id': agent.id,
            'agent_name': agent.name,
            'agent_mobile': agent.mobile,
            'status': 'Assigned To Delivery Agent'
        }, to='admins')
        
        socketio.emit('order_status_updated', {
            'order_id': order.id,
            'status': 'Assigned To Delivery Agent',
            'payment_status': order.payment_status
        }, to=f"order_{order.id}")
        
        socketio.emit('order_status_changed', {
            'order_id': order.id,
            'status': 'Assigned To Delivery Agent',
            'payment_status': order.payment_status
        }, to='admins')
    except Exception as e:
        print(f"Socket.IO emit error: {e}")
        
    return jsonify({
        'message': f'Order #{order.id} successfully assigned to agent {agent.name}',
        'assignment': assignment.to_dict(),
        'order': order.to_dict()
    }), 200

@delivery_bp.route('/analytics', methods=['GET'])
@admin_required
def get_analytics():
    """Retrieve delivery performance and analytics summary"""
    total_assignments = DeliveryAssignment.query.count()
    delivered_count = DeliveryAssignment.query.filter_by(status='Delivered').count()
    failed_count = DeliveryAssignment.query.filter_by(status='Failed').count()
    
    success_rate = 0.0
    if total_assignments > 0:
        success_rate = round((delivered_count / total_assignments) * 100, 2)
        
    # Delivery Agent Performance details
    agents = DeliveryAgent.query.all()
    agent_performance = []
    for agent in agents:
        agent_assigns = DeliveryAssignment.query.filter_by(delivery_agent_id=agent.id).all()
        total_agent_delivs = len(agent_assigns)
        success_agent_delivs = sum(1 for a in agent_assigns if a.status == 'Delivered')
        
        agent_success_rate = 0.0
        if total_agent_delivs > 0:
            agent_success_rate = round((success_agent_delivs / total_agent_delivs) * 100, 2)
            
        # Calculate Average Delivery Time (in minutes)
        deliv_times = []
        for a in agent_assigns:
            if a.status == 'Delivered' and a.delivered_at and a.assigned_at:
                diff = (a.delivered_at - a.assigned_at).total_seconds() / 60.0
                deliv_times.append(diff)
                
        avg_time = round(sum(deliv_times) / len(deliv_times), 1) if deliv_times else 0.0
        
        agent_performance.append({
            'id': agent.id,
            'name': agent.name,
            'mobile': agent.mobile,
            'total_deliveries': total_agent_delivs,
            'delivered_orders': success_agent_delivs,
            'success_rate': agent_success_rate,
            'avg_delivery_time_mins': avg_time
        })
        
    return jsonify({
        'total_deliveries': total_assignments,
        'delivered_orders': delivered_count,
        'failed_deliveries': failed_count,
        'success_rate': success_rate,
        'agent_performance': agent_performance
    }), 200

# ==========================================
# DELIVERY AGENT DASHBOARD ROUTES
# ==========================================

@delivery_bp.route('/dashboard/stats', methods=['GET'])
@agent_required
def get_agent_stats():
    """Retrieve stats for the logged-in delivery agent"""
    agent_id = g.user_id
    
    total_assigned = DeliveryAssignment.query.filter_by(delivery_agent_id=agent_id).count()
    pending = DeliveryAssignment.query.filter(
        DeliveryAssignment.delivery_agent_id == agent_id,
        DeliveryAssignment.status.in_(['Assigned', 'Out For Delivery'])
    ).count()
    
    today_start = datetime.combine(date.today(), datetime.min.time())
    today_end = datetime.combine(date.today(), datetime.max.time())
    
    delivered_today = DeliveryAssignment.query.filter(
        DeliveryAssignment.delivery_agent_id == agent_id,
        DeliveryAssignment.status == 'Delivered',
        DeliveryAssignment.delivered_at >= today_start,
        DeliveryAssignment.delivered_at <= today_end
    ).count()
    
    # Calculate earnings (₹20 per delivery)
    earnings = delivered_today * 20.00
    
    return jsonify({
        'total_assigned_orders': total_assigned,
        'pending_deliveries': pending,
        'delivered_orders_today': delivered_today,
        'earnings': earnings
    }), 200

@delivery_bp.route('/dashboard/orders', methods=['GET'])
@agent_required
def get_agent_orders():
    """List assigned orders for the logged-in agent (paginated)"""
    agent_id = g.user_id
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    paginated = DeliveryAssignment.query.filter_by(delivery_agent_id=agent_id)\
                                        .options(joinedload(DeliveryAssignment.order))\
                                        .order_by(DeliveryAssignment.assigned_at.desc())\
                                        .paginate(page=page, per_page=per_page, error_out=False)
                                        
    results = []
    
    for assign in paginated.items:
        order = assign.order
        if not order:
            continue
            
        items = [{
            'product_name_en': item.product_name_en,
            'product_name_hi': item.product_name_hi,
            'product_name_mr': item.product_name_mr,
            'quantity': float(item.quantity),
            'unit': item.unit,
            'price': float(item.price)
        } for item in order.items]
        
        results.append({
            'assignment_id': assign.id,
            'assignment_status': assign.status,
            'assigned_at': assign.assigned_at.isoformat() if assign.assigned_at else None,
            'delivered_at': assign.delivered_at.isoformat() if assign.delivered_at else None,
            'order': {
                'id': order.id,
                'customer_name': order.customer_name,
                'customer_mobile': order.customer_mobile,
                'delivery_address': order.delivery_address,
                'order_notes': order.order_notes,
                'payment_method': order.payment_method,
                'payment_status': order.payment_status,
                'order_status': order.order_status,
                'total_amount': float(order.total_amount),
                'latitude': order.latitude,
                'longitude': order.longitude,
                'items': items
            }
        })
        
    return jsonify({
        'orders': results,
        'total': paginated.total,
        'page': paginated.page,
        'pages': paginated.pages
    }), 200

@delivery_bp.route('/assignments/<int:assignment_id>/status', methods=['PUT'])
@agent_required
def update_assignment_status(assignment_id):
    """Update order delivery status from agent panel"""
    agent_id = g.user_id
    assign = DeliveryAssignment.query.filter_by(id=assignment_id, delivery_agent_id=agent_id).first()
    if not assign:
        return jsonify({'message': 'Assignment not found or unauthorized'}), 404
        
    order = Order.query.get(assign.order_id)
    if not order:
        return jsonify({'message': 'Order not found'}), 404
        
    data = request.get_json()
    if not data or 'status' not in data:
        return jsonify({'message': 'Status parameter is required'}), 400
        
    new_status = data['status'].strip()
    valid_statuses = ['Out For Delivery', 'Delivered', 'Failed']
    if new_status not in valid_statuses:
        return jsonify({'message': f'Invalid status. Must be one of {valid_statuses}'}), 400
        
    # Workflow transitions
    assign.status = new_status
    order.delivery_status = new_status
    
    if new_status == 'Out For Delivery':
        order.order_status = 'Out For Delivery'
        
    elif new_status == 'Delivered':
        order.order_status = 'Delivered'
        assign.delivered_at = datetime.utcnow()
        # Mark payment as Paid (especially for COD)
        payment = Payment.query.filter_by(order_id=order.id).first()
        if payment:
            payment.status = 'Success'
        order.payment_status = 'Paid'
        
    elif new_status == 'Failed':
        order.order_status = 'Unable To Deliver'
        # Restock products if order fails delivery
        # Note: or admin can decide. But to be safe and responsive, we can set status to 'Unable To Deliver'.
        
    # Store customer notifications
    cust_notif = Notification(
        user_id=order.customer_id,
        user_type='customer',
        title_en=f"Order Status Update: {order.order_status}",
        title_hi=f"ऑर्डर की स्थिति: {order.order_status}",
        title_mr=f"ऑर्डरची स्थिती: {order.order_status}",
        message_en=f"Your order #{order.id} status is now '{order.order_status}'.",
        message_hi=f"आपका ऑर्डर #{order.id} अब '{order.order_status}' की स्थिति में है।",
        message_mr=f"तुमची ऑर्डर #{order.id} आता '{order.order_status}' स्थितीमध्ये आहे."
    )
    db.session.add(cust_notif)
    db.session.commit()
    
    # Invalidate cache since status updated
    cache.delete("reports:stats")
    
    # Emit real-time updates via Socket.IO
    try:
        socketio.emit('order_status_updated', {
            'order_id': order.id,
            'status': order.order_status,
            'payment_status': order.payment_status
        }, to=f"order_{order.id}")
        socketio.emit('order_status_changed', {
            'order_id': order.id,
            'status': order.order_status,
            'payment_status': order.payment_status
        }, to='admins')
        if new_status == 'Out For Delivery':
            socketio.emit('delivery_started', {
                'order_id': order.id,
                'agent_id': agent_id
            }, to='admins')
        elif new_status == 'Delivered':
            socketio.emit('delivery_completed', {
                'order_id': order.id,
                'agent_id': agent_id
            }, to='admins')
    except Exception as e:
        print(f"Socket.IO emit error: {e}")
        
    return jsonify({
        'message': f'Assignment status updated to {new_status}',
        'assignment': assign.to_dict(),
        'order': order.to_dict()
    }), 200
