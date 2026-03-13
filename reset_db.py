import sys
import os
from app import create_app
from models import db, User, ClassGroup

app = create_app()

with app.app_context():
    print("Dropping all tables...")
    db.drop_all()
    print("Creating all tables...")
    db.create_all()
    
    # Seed admin user
    print("Seeding admin user...")
    admin = User(username="admin", role="admin")
    admin.set_password("admin")
    db.session.add(admin)
    
    # Needs at least one class for the system to not break on register page
    print("Seeding default class...")
    default_class = ClassGroup(name="Alpha", department="General")
    db.session.add(default_class)
    
    db.session.commit()
    print("Database reset successfully! login: admin / admin")
