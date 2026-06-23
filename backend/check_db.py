import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.app import create_app
from backend.database import db

try:
    app = create_app()
    with app.app_context():
        print("\n=== Registered SQLAlchemy Models ===")
        for mapper in db.Model.registry.mappers:
            print(f"- {mapper.class_.__name__} (Table: {mapper.local_table.name})")
        print("===================================\n")
except Exception as e:
    import traceback
    traceback.print_exc()
