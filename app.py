from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from config import Config
from models import db
from routes.auth_routes import auth_bp
from routes.data_routes import data_bp
from routes.timetable_routes import timetable_bp
from routes.settings_routes import settings_bp
import os


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Configure CORS for production and development
    allowed_origins = [
        "https://timetable-geration-frontend.vercel.app",
        "http://localhost:5173",
        "http://localhost:3000",
    ]
    
    CORS(app, 
         resources={r"/api/*": {"origins": allowed_origins}},
         supports_credentials=True,
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    db.init_app(app)
    JWTManager(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(data_bp)
    app.register_blueprint(timetable_bp)
    app.register_blueprint(settings_bp, url_prefix='/api/settings')

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    with app.app_context():
        db.create_all()

    return app

app = create_app()

if __name__ == "__main__":
    debug_mode = os.environ.get("FLASK_ENV") == "development"
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=debug_mode, port=port, host="0.0.0.0")
