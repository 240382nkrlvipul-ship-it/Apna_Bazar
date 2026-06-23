-- MySQL Database Schema for Village Grocery Store Management & Online Ordering Platform

CREATE DATABASE IF NOT EXISTS village_grocery_db;
USE village_grocery_db;

-- 1. Admins Table
CREATE TABLE IF NOT EXISTS admins (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'admin', -- 'superadmin', 'admin', 'staff'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 2. Customers Table
CREATE TABLE IF NOT EXISTS customers (
    id INT AUTO_INCREMENT PRIMARY KEY,
    mobile VARCHAR(15) UNIQUE NOT NULL,
    name VARCHAR(100) NULL,
    otp_hash VARCHAR(255) NULL,
    otp_expiry TIMESTAMP NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 3. Villages Table (approved villages restriction)
CREATE TABLE IF NOT EXISTS villages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name_en VARCHAR(100) UNIQUE NOT NULL,
    name_hi VARCHAR(100) NOT NULL,
    name_mr VARCHAR(100) NOT NULL,
    is_allowed BOOLEAN DEFAULT TRUE,
    delivery_charge DECIMAL(10,2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 4. Categories Table
CREATE TABLE IF NOT EXISTS categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name_en VARCHAR(100) UNIQUE NOT NULL,
    name_hi VARCHAR(100) NOT NULL,
    name_mr VARCHAR(100) NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    image_url VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 5. Products Table
CREATE TABLE IF NOT EXISTS products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NULL,
    name_en VARCHAR(255) NOT NULL,
    name_hi VARCHAR(255) NOT NULL,
    name_mr VARCHAR(255) NOT NULL,
    description_en TEXT NULL,
    description_hi TEXT NULL,
    description_mr TEXT NULL,
    price DECIMAL(10,2) NOT NULL,
    discount_price DECIMAL(10,2) DEFAULT NULL,
    stock_quantity DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    unit VARCHAR(20) NOT NULL, -- 'kg', 'packet', 'litre', 'piece'
    is_visible BOOLEAN DEFAULT TRUE,
    image_url VARCHAR(255) NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 6. Product Extra Images Table
CREATE TABLE IF NOT EXISTS product_images (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    image_url VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 7. Carts Table
CREATE TABLE IF NOT EXISTS carts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 8. Cart Items Table
CREATE TABLE IF NOT EXISTS cart_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cart_id INT NOT NULL,
    product_id INT NOT NULL,
    quantity DECIMAL(10,2) NOT NULL DEFAULT 1.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cart_id) REFERENCES carts(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 9. Orders Table
CREATE TABLE IF NOT EXISTS orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NULL,
    village_id INT NULL,
    customer_name VARCHAR(100) NOT NULL,
    customer_mobile VARCHAR(15) NOT NULL,
    delivery_address TEXT NOT NULL,
    order_notes TEXT NULL,
    payment_method VARCHAR(20) NOT NULL, -- 'COD', 'UPI'
    payment_status VARCHAR(20) NOT NULL DEFAULT 'Pending', -- 'Pending', 'Paid', 'Failed'
    order_status VARCHAR(30) NOT NULL DEFAULT 'Order Received', -- 'Order Received', 'Preparing', 'Packed', 'Out For Delivery', 'Delivered', 'Cancelled'
    total_amount DECIMAL(10,2) NOT NULL,
    delivery_charge DECIMAL(10,2) DEFAULT 0.00,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
    FOREIGN KEY (village_id) REFERENCES villages(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 10. Order Items Table
CREATE TABLE IF NOT EXISTS order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    product_id INT NULL,
    product_name_en VARCHAR(255) NOT NULL,
    product_name_hi VARCHAR(255) NOT NULL,
    product_name_mr VARCHAR(255) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    quantity DECIMAL(10,2) NOT NULL,
    unit VARCHAR(20) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 11. Payments Table
CREATE TABLE IF NOT EXISTS payments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    payment_method VARCHAR(20) NOT NULL,
    transaction_id VARCHAR(100) NULL,
    amount DECIMAL(10,2) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Pending', -- 'Pending', 'Success', 'Failed'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 12. Inventory Logs Table
CREATE TABLE IF NOT EXISTS inventory_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    product_id INT NOT NULL,
    quantity_changed DECIMAL(10,2) NOT NULL,
    change_type VARCHAR(50) NOT NULL, -- 'Order Deduct', 'Admin Restock', 'Correction'
    notes TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 13. Notifications Table
CREATE TABLE IF NOT EXISTS notifications (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NULL, -- NULL means broadcast or admin notification
    user_type VARCHAR(10) NOT NULL DEFAULT 'admin', -- 'admin', 'customer'
    title_en VARCHAR(255) NOT NULL,
    title_hi VARCHAR(255) NULL,
    title_mr VARCHAR(255) NULL,
    message_en TEXT NOT NULL,
    message_hi TEXT NULL,
    message_mr TEXT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 14. Delivery Agents Table
CREATE TABLE IF NOT EXISTS delivery_agents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    mobile VARCHAR(15) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Active', -- 'Active', 'Inactive'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 15. Delivery Assignments Table
CREATE TABLE IF NOT EXISTS delivery_assignments (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT NOT NULL,
    delivery_agent_id INT NOT NULL,
    assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    delivered_at TIMESTAMP NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'Assigned', -- 'Assigned', 'Out For Delivery', 'Delivered', 'Failed'
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE,
    FOREIGN KEY (delivery_agent_id) REFERENCES delivery_agents(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 16. Customer Locations Table
CREATE TABLE IF NOT EXISTS customer_locations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_id INT NOT NULL,
    latitude DOUBLE NOT NULL,
    longitude DOUBLE NOT NULL,
    address TEXT NOT NULL,
    landmark TEXT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Add Delivery Columns to Orders Table (for systems that don't support ADD COLUMN IF NOT EXISTS, these can be run conditionally or are standard in modern MySQL)
ALTER TABLE orders ADD COLUMN IF NOT EXISTS latitude DOUBLE NULL;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS longitude DOUBLE NULL;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_agent_id INT NULL;
ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(30) NULL DEFAULT 'Pending';

