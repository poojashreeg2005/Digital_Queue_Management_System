
from flask import Flask

from config import Config
from models import db

# Import models so SQLAlchemy knows all table definitions
import models

app = Flask(__name__)
app.config.from_object(Config)

# Connect SQLAlchemy to Flask
db.init_app(app)

with app.app_context():
    db.create_all()

    print("QueueFlow database tables created successfully!")

    print("Tables:")
    for table_name in db.metadata.tables:
        print("-", table_name)
