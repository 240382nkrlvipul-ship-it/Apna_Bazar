import jwt
import datetime
from functools import wraps
from flask import request, jsonify, g
from backend.config import Config
from backend.database import Admin, Customer

def encode_token(user_id, role='customer'):
    """Generates a JWT token for the user/admin"""
    try:
        payload = {
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=1),
            'iat': datetime.datetime.utcnow(),
            'sub': user_id,
            'role': role
        }
        return jwt.encode(
            payload,
            Config.JWT_SECRET,
            algorithm='HS256'
        )
    except Exception as e:
        return None

def decode_token(token):
    """Decodes a JWT token"""
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=['HS256'])
        return payload
    except jwt.ExpiredSignatureError:
        return 'Expired'
    except jwt.InvalidTokenError:
        return 'Invalid'

def token_required(f):
    """Decorator to require valid token for a route"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Check authorization header
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        data = decode_token(token)
        if data == 'Expired':
            return jsonify({'message': 'Token is expired!'}), 401
        if data == 'Invalid' or not isinstance(data, dict):
            return jsonify({'message': 'Token is invalid!'}), 401
            
        g.user_id = data.get('sub')
        g.user_role = data.get('role', 'customer')
        
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    """Decorator to require admin privileges for a route"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        data = decode_token(token)
        if data == 'Expired':
            return jsonify({'message': 'Token is expired!'}), 401
        if data == 'Invalid' or not isinstance(data, dict):
            return jsonify({'message': 'Token is invalid!'}), 401
            
        if data.get('role') not in ['admin', 'superadmin']:
            return jsonify({'message': 'Admin privilege required!'}), 403
            
        g.user_id = data.get('sub')
        g.user_role = data.get('role')
        
        return f(*args, **kwargs)
    return decorated

def agent_required(f):
    """Decorator to require delivery agent privileges for a route"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'message': 'Token is missing!'}), 401
        
        data = decode_token(token)
        if data == 'Expired':
            return jsonify({'message': 'Token is expired!'}), 401
        if data == 'Invalid' or not isinstance(data, dict):
            return jsonify({'message': 'Token is invalid!'}), 401
            
        if data.get('role') != 'agent':
            return jsonify({'message': 'Agent privilege required!'}), 403
            
        g.user_id = data.get('sub')
        g.user_role = data.get('role')
        
        return f(*args, **kwargs)
    return decorated

