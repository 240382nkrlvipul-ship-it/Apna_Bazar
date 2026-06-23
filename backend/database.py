from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='admin')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'role': self.role,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Customer(db.Model):
    __tablename__ = 'customers'
    id = db.Column(db.Integer, primary_key=True)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=True)
    otp_hash = db.Column(db.String(255), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    is_verified = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    cart = db.relationship('Cart', backref='customer', uselist=False, cascade="all, delete-orphan")
    orders = db.relationship('Order', backref='customer', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'mobile': self.mobile,
            'name': self.name,
            'is_verified': self.is_verified,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Village(db.Model):
    __tablename__ = 'villages'
    id = db.Column(db.Integer, primary_key=True)
    name_en = db.Column(db.String(100), unique=True, nullable=False)
    name_hi = db.Column(db.String(100), nullable=False)
    name_mr = db.Column(db.String(100), nullable=False)
    is_allowed = db.Column(db.Boolean, default=True)
    delivery_charge = db.Column(db.Numeric(10, 2), default=0.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name_en': self.name_en,
            'name_hi': self.name_hi,
            'name_mr': self.name_mr,
            'is_allowed': self.is_allowed,
            'delivery_charge': float(self.delivery_charge) if self.delivery_charge is not None else 0.0,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name_en = db.Column(db.String(100), unique=True, nullable=False)
    name_hi = db.Column(db.String(100), nullable=False)
    name_mr = db.Column(db.String(100), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    image_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    products = db.relationship('Product', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name_en': self.name_en,
            'name_hi': self.name_hi,
            'name_mr': self.name_mr,
            'is_active': self.is_active,
            'image_url': self.image_url,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='SET NULL'), nullable=True, index=True)
    name_en = db.Column(db.String(255), nullable=False)
    name_hi = db.Column(db.String(255), nullable=False)
    name_mr = db.Column(db.String(255), nullable=False)
    description_en = db.Column(db.Text, nullable=True)
    description_hi = db.Column(db.Text, nullable=True)
    description_mr = db.Column(db.Text, nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    discount_price = db.Column(db.Numeric(10, 2), nullable=True)
    stock_quantity = db.Column(db.Numeric(10, 2), nullable=False, default=0.00)
    unit = db.Column(db.String(20), nullable=False)  # 'kg', 'packet', 'litre', 'piece'
    is_visible = db.Column(db.Boolean, default=True)
    image_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Relationships
    images = db.relationship('ProductImage', backref='product', cascade="all, delete-orphan", lazy=True)
    cart_items = db.relationship('CartItem', backref='product', cascade="all, delete-orphan", lazy=True)
    inventory_logs = db.relationship('InventoryLog', backref='product', cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        img_url = self.image_url
        card_img = None
        thumb_img = None
        if img_url:
            if img_url.startswith('/static/uploads/'):
                base_path = img_url.rsplit('.', 1)[0]
                if not base_path.endswith('_card') and not base_path.endswith('_thumb'):
                    card_img = f"{base_path}_card.webp"
                    thumb_img = f"{base_path}_thumb.webp"
                else:
                    card_img = img_url
                    thumb_img = img_url
            else:
                card_img = img_url
                thumb_img = img_url

        return {
            'id': self.id,
            'category_id': self.category_id,
            'category_name_en': self.category.name_en if self.category else 'Uncategorized',
            'category_name_hi': self.category.name_hi if self.category else 'अवर्गीकृत',
            'category_name_mr': self.category.name_mr if self.category else 'अवर्गीकृत',
            'name_en': self.name_en,
            'name_hi': self.name_hi,
            'name_mr': self.name_mr,
            'description_en': self.description_en,
            'description_hi': self.description_hi,
            'description_mr': self.description_mr,
            'price': float(self.price),
            'discount_price': float(self.discount_price) if self.discount_price is not None else None,
            'stock_quantity': float(self.stock_quantity),
            'unit': self.unit,
            'is_visible': self.is_visible,
            'image_url': self.image_url,
            'card_image_url': card_img,
            'thumbnail_url': thumb_img,
            'extra_images': [img.image_url for img in self.images],
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class ProductImage(db.Model):
    __tablename__ = 'product_images'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    image_url = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'image_url': self.image_url
        }

class Cart(db.Model):
    __tablename__ = 'carts'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='CASCADE'), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    items = db.relationship('CartItem', backref='cart', cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'items': [item.to_dict() for item in self.items],
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class CartItem(db.Model):
    __tablename__ = 'cart_items'
    id = db.Column(db.Integer, primary_key=True)
    cart_id = db.Column(db.Integer, db.ForeignKey('carts.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    quantity = db.Column(db.Numeric(10, 2), nullable=False, default=1.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'cart_id': self.cart_id,
            'product_id': self.product_id,
            'product': self.product.to_dict() if self.product else None,
            'quantity': float(self.quantity),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='SET NULL'), nullable=True, index=True)
    village_id = db.Column(db.Integer, db.ForeignKey('villages.id', ondelete='SET NULL'), nullable=True, index=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_mobile = db.Column(db.String(15), nullable=False)
    delivery_address = db.Column(db.Text, nullable=False)
    order_notes = db.Column(db.Text, nullable=True)
    payment_method = db.Column(db.String(20), nullable=False)  # 'COD', 'UPI'
    payment_status = db.Column(db.String(20), nullable=False, default='Pending') # 'Pending', 'Paid', 'Failed'
    order_status = db.Column(db.String(30), nullable=False, default='Order Received', index=True) # 'Order Received', 'Preparing', 'Packed', 'Assigned To Delivery Agent', 'Out For Delivery', 'Delivered', 'Cancelled'
    total_amount = db.Column(db.Numeric(10, 2), nullable=False)
    delivery_charge = db.Column(db.Numeric(10, 2), default=0.00)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Coordinates & Agent fields
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    delivery_agent_id = db.Column(db.Integer, db.ForeignKey('delivery_agents.id', ondelete='SET NULL'), nullable=True, index=True)
    delivery_status = db.Column(db.String(30), nullable=True, default='Pending', index=True) # 'Pending', 'Assigned', 'Out For Delivery', 'Delivered', 'Failed'

    # Relationships
    items = db.relationship('OrderItem', backref='order', cascade="all, delete-orphan", lazy=True)
    payments = db.relationship('Payment', backref='order', cascade="all, delete-orphan", lazy=True)
    assignments = db.relationship('DeliveryAssignment', backref='order', cascade="all, delete-orphan", lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'village_id': self.village_id,
            'customer_name': self.customer_name,
            'customer_mobile': self.customer_mobile,
            'delivery_address': self.delivery_address,
            'order_notes': self.order_notes,
            'payment_method': self.payment_method,
            'payment_status': self.payment_status,
            'order_status': self.order_status,
            'total_amount': float(self.total_amount),
            'delivery_charge': float(self.delivery_charge) if self.delivery_charge is not None else 0.0,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'delivery_agent_id': self.delivery_agent_id,
            'delivery_status': self.delivery_status,
            'items': [item.to_dict() for item in self.items],
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class OrderItem(db.Model):
    __tablename__ = 'order_items'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='SET NULL'), nullable=True, index=True)
    product_name_en = db.Column(db.String(255), nullable=False)
    product_name_hi = db.Column(db.String(255), nullable=False)
    product_name_mr = db.Column(db.String(255), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    quantity = db.Column(db.Numeric(10, 2), nullable=False)
    unit = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'product_id': self.product_id,
            'product_name_en': self.product_name_en,
            'product_name_hi': self.product_name_hi,
            'product_name_mr': self.product_name_mr,
            'price': float(self.price),
            'quantity': float(self.quantity),
            'unit': self.unit,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    payment_method = db.Column(db.String(20), nullable=False)
    transaction_id = db.Column(db.String(100), nullable=True)
    amount = db.Column(db.Numeric(10, 2), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Pending', index=True) # 'Pending', 'Success', 'Failed'
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'payment_method': self.payment_method,
            'transaction_id': self.transaction_id,
            'amount': float(self.amount),
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class InventoryLog(db.Model):
    __tablename__ = 'inventory_logs'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    quantity_changed = db.Column(db.Numeric(10, 2), nullable=False)
    change_type = db.Column(db.String(50), nullable=False) # 'Order Deduct', 'Admin Restock', 'Correction'
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'product_id': self.product_id,
            'product_name_en': self.product.name_en if self.product else 'Unknown Product',
            'quantity_changed': float(self.quantity_changed),
            'change_type': self.change_type,
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class Notification(db.Model):
    __tablename__ = 'notifications'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, nullable=True, index=True) # NULL means broadcast or admin notification
    user_type = db.Column(db.String(10), nullable=False, default='admin', index=True) # 'admin', 'customer'
    title_en = db.Column(db.String(255), nullable=False)
    title_hi = db.Column(db.String(255), nullable=True)
    title_mr = db.Column(db.String(255), nullable=True)
    message_en = db.Column(db.Text, nullable=False)
    message_hi = db.Column(db.Text, nullable=True)
    message_mr = db.Column(db.Text, nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'user_type': self.user_type,
            'title_en': self.title_en,
            'title_hi': self.title_hi,
            'title_mr': self.title_mr,
            'message_en': self.message_en,
            'message_hi': self.message_hi,
            'message_mr': self.message_mr,
            'is_read': self.is_read,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class DeliveryAgent(db.Model):
    __tablename__ = 'delivery_agents'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    mobile = db.Column(db.String(15), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='Active') # 'Active', 'Inactive'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    orders = db.relationship('Order', backref='delivery_agent', lazy=True)
    assignments = db.relationship('DeliveryAssignment', backref='delivery_agent', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'mobile': self.mobile,
            'status': self.status,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class DeliveryAssignment(db.Model):
    __tablename__ = 'delivery_assignments'
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id', ondelete='CASCADE'), nullable=False, index=True)
    delivery_agent_id = db.Column(db.Integer, db.ForeignKey('delivery_agents.id', ondelete='CASCADE'), nullable=False, index=True)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    delivered_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(30), nullable=False, default='Assigned', index=True) # 'Assigned', 'Out For Delivery', 'Delivered', 'Failed'

    def to_dict(self):
        return {
            'id': self.id,
            'order_id': self.order_id,
            'delivery_agent_id': self.delivery_agent_id,
            'delivery_agent_name': self.delivery_agent.name if self.delivery_agent else 'Unknown Agent',
            'assigned_at': self.assigned_at.isoformat() if self.assigned_at else None,
            'delivered_at': self.delivered_at.isoformat() if self.delivered_at else None,
            'status': self.status
        }

class CustomerLocation(db.Model):
    __tablename__ = 'customer_locations'
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('customers.id', ondelete='CASCADE'), nullable=False, index=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    address = db.Column(db.Text, nullable=False)
    landmark = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'customer_id': self.customer_id,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'address': self.address,
            'landmark': self.landmark,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }
