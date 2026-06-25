import unittest
import json
import os
from backend.app import create_app
from backend.database import db, Admin, Customer, Product, Category, Village

class GroceryAppTestCase(unittest.TestCase):
    def setUp(self):
        # Configure app to use SQLite for tests
        os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
        self.app = create_app()
        self.client = self.app.test_client()
        self.app_context = self.app.app_context()
        self.app_context.push()
        
    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def test_database_seeding(self):
        """Verify that default mock data was auto-seeded on table creation"""
        # Admin seeded
        admin = Admin.query.filter_by(username='admin').first()
        self.assertIsNotNone(admin)
        self.assertEqual(admin.role, 'superadmin')

        # Categories seeded
        dairy = Category.query.filter_by(name_en='Dairy Products').first()
        self.assertIsNotNone(dairy)
        self.assertEqual(dairy.name_mr, 'डेअरी उत्पादने')

        # Villages seeded
        palghar = Village.query.filter_by(name_en='Palghar').first()
        self.assertIsNotNone(palghar)
        self.assertEqual(float(palghar.delivery_charge), 20.00)

        # Products seeded
        milk = Product.query.filter_by(name_en='Fresh Buffalo Milk').first()
        self.assertIsNotNone(milk)
        self.assertEqual(float(milk.price), 65.00)
        self.assertEqual(milk.unit, 'litre')

    def test_public_endpoints(self):
        """Verify that categories and products list work for guests"""
        res_cats = self.client.get('/api/categories')
        self.assertEqual(res_cats.status_code, 200)
        cats_data = json.loads(res_cats.data)
        self.assertGreater(len(cats_data), 0)

        res_prods = self.client.get('/api/products')
        self.assertEqual(res_prods.status_code, 200)
        prods_data = json.loads(res_prods.data)
        self.assertGreater(len(prods_data['products']), 0)

    def test_customer_otp_simulation(self):
        """Verify simulated OTP trigger and Verification return values"""
        # 1. Request OTP
        res_req = self.client.post('/api/auth/otp/request', json={'mobile': '9999999999'})
        self.assertEqual(res_req.status_code, 200)
        req_data = json.loads(res_req.data)
        self.assertEqual(req_data['otp'], '123456') # Seeded override for test number

        # 2. Verify OTP
        res_verify = self.client.post('/api/auth/otp/verify', json={
            'mobile': '9999999999',
            'otp': '123456'
        })
        self.assertEqual(res_verify.status_code, 200)
        verify_data = json.loads(res_verify.data)
        self.assertIn('token', verify_data)
        self.assertEqual(verify_data['user']['mobile'], '9999999999')

    def test_dev_otp_system(self):
        """Verify new development OTP generation, verification, validation, single-use, and role assignment"""
        # 1. Request OTP for Customer
        res_req = self.client.post('/api/auth/send-otp', json={'mobile': '9876543210'})
        self.assertEqual(res_req.status_code, 200)
        req_data = json.loads(res_req.data)
        self.assertTrue(req_data['success'])
        otp = req_data['otp']
        self.assertEqual(len(otp), 6)
        self.assertTrue(otp.isdigit())

        # 2. Verify OTP with incorrect OTP
        res_verify_fail = self.client.post('/api/auth/verify-otp', json={
            'mobile': '9876543210',
            'otp': '000000'
        })
        self.assertEqual(res_verify_fail.status_code, 400)
        self.assertFalse(json.loads(res_verify_fail.data)['success'])

        # 3. Verify OTP with correct OTP
        res_verify_ok = self.client.post('/api/auth/verify-otp', json={
            'mobile': '9876543210',
            'otp': otp
        })
        self.assertEqual(res_verify_ok.status_code, 200)
        verify_data = json.loads(res_verify_ok.data)
        self.assertTrue(verify_data['success'])
        self.assertIn('token', verify_data)
        self.assertEqual(verify_data['role'], 'customer')
        self.assertEqual(verify_data['user']['mobile'], '9876543210')

        # 4. Verify single-use constraint (should fail on reuse)
        res_verify_reuse = self.client.post('/api/auth/verify-otp', json={
            'mobile': '9876543210',
            'otp': otp
        })
        self.assertEqual(res_verify_reuse.status_code, 400)
        self.assertFalse(json.loads(res_verify_reuse.data)['success'])

        # 5. Request OTP for Admin
        res_req_admin = self.client.post('/api/auth/send-otp', json={'mobile': '8888199091'})
        self.assertEqual(res_req_admin.status_code, 200)
        req_admin_data = json.loads(res_req_admin.data)
        self.assertTrue(req_admin_data['success'])
        admin_otp = req_admin_data['otp']

        # 6. Verify Admin OTP
        res_verify_admin = self.client.post('/api/auth/verify-otp', json={
            'mobile': '8888199091',
            'otp': admin_otp
        })
        self.assertEqual(res_verify_admin.status_code, 200)
        verify_admin_data = json.loads(res_verify_admin.data)
        self.assertTrue(verify_admin_data['success'])
        self.assertIn('token', verify_admin_data)
        self.assertEqual(verify_admin_data['role'], 'admin')

    def test_admin_login(self):
        """Verify admin login returns active JWT token"""
        res = self.client.post('/api/auth/admin/login', json={
            'username': 'admin',
            'password': 'admin123'
        })
        self.assertEqual(res.status_code, 200)
        data = json.loads(res.data)
        self.assertIn('token', data)
        self.assertEqual(data['user']['username'], 'admin')

    def test_haversine_distance(self):
        """Verify Haversine distance logic calculations"""
        from backend.utils.distance import calculate_haversine_distance
        # Same point should be 0 distance
        dist1 = calculate_haversine_distance(19.4553, 72.8120, 19.4553, 72.8120)
        self.assertAlmostEqual(dist1, 0.0, places=2)
        
        # Test distance from shop to nearby location (Arnala, approx 6 km)
        dist2 = calculate_haversine_distance(19.4553, 72.8120, 19.4674, 72.7533)
        self.assertLess(dist2, 10.0)
        self.assertGreater(dist2, 4.0)

        # Test distance from shop to Mumbai (approx 50+ km)
        dist3 = calculate_haversine_distance(19.4553, 72.8120, 18.9750, 72.8258)
        self.assertGreater(dist3, 40.0)

    def test_checkout_location_verification(self):
        """Verify order checkout location permissions and radius validations"""
        # 1. Request OTP first to create user and hash simulated OTP
        self.client.post('/api/auth/otp/request', json={'mobile': '9999999999'})
        
        # 2. Login customer to get token
        res_verify = self.client.post('/api/auth/otp/verify', json={
            'mobile': '9999999999',
            'otp': '123456'
        })
        token = json.loads(res_verify.data)['token']
        headers = {'Authorization': f'Bearer {token}'}


        # 2. Add product to cart
        product = Product.query.first()
        self.client.post('/api/cart/items', json={
            'product_id': product.id,
            'quantity': 1
        }, headers=headers)

        # 3. Checkout without location (should fail)
        res_checkout_no_loc = self.client.post('/api/orders', json={
            'customer_name': 'Test User',
            'customer_mobile': '9999999999',
            'village_id': 1,
            'payment_method': 'COD'
        }, headers=headers)
        self.assertEqual(res_checkout_no_loc.status_code, 400)
        self.assertIn('Location permission is required', json.loads(res_checkout_no_loc.data)['message'])

        # 4. Checkout with out-of-range location (should fail)
        res_checkout_out_of_range = self.client.post('/api/orders', json={
            'customer_name': 'Test User',
            'customer_mobile': '9999999999',
            'village_id': 1,
            'payment_method': 'COD',
            'latitude': 18.9750, # Mumbai (approx 53km from Virar)
            'longitude': 72.8258,
            'house_number': '12A',
            'area_street': 'Colaba Causeway'
        }, headers=headers)
        self.assertEqual(res_checkout_out_of_range.status_code, 400)
        self.assertIn('delivery is currently unavailable', json.loads(res_checkout_out_of_range.data)['message'])

        # 5. Checkout with in-range location (should succeed)
        res_checkout_in_range = self.client.post('/api/orders', json={
            'customer_name': 'Test User',
            'customer_mobile': '9999999999',
            'village_id': 1,
            'payment_method': 'COD',
            'latitude': 19.4553, # Virar
            'longitude': 72.8120,
            'house_number': '42',
            'area_street': 'Station Road',
            'landmark': 'Near Station'
        }, headers=headers)
        self.assertEqual(res_checkout_in_range.status_code, 201)
        self.assertIn('Order placed successfully', json.loads(res_checkout_in_range.data)['message'])

        # 6. Fetch previous addresses history (should return the newly placed order's address)
        res_prev_addr = self.client.get('/api/previous-addresses', headers=headers)
        self.assertEqual(res_prev_addr.status_code, 200)
        prev_addr_data = json.loads(res_prev_addr.data)
        self.assertIn('addresses', prev_addr_data)
        self.assertEqual(len(prev_addr_data['addresses']), 1)
        self.assertEqual(prev_addr_data['addresses'][0]['house_number'], '42')
        self.assertEqual(prev_addr_data['addresses'][0]['area_street'], 'Station Road')
        self.assertEqual(prev_addr_data['addresses'][0]['landmark'], 'Near Station')
        self.assertEqual(prev_addr_data['addresses'][0]['village_id'], 1)


if __name__ == '__main__':
    unittest.main()

