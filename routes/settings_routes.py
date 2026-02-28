from flask import Blueprint, jsonify, request
from models import db, SystemSetting
from routes.auth_routes import token_required

settings_bp = Blueprint("settings_routes", __name__)

DEFAULT_SETTINGS = {
    "max_theory_per_day": {"value": "3", "desc": "Maximum theory hours a class can have per day."},
    "max_lab_per_day": {"value": "2", "desc": "Maximum lab blocks (each 2-hour) a class can have per day."},
    "max_total_hours": {"value": "7", "desc": "Maximum total academic hours per day."},
    "short_break_duration": {"value": "15", "desc": "Short break duration in minutes (e.g., 15)."},
    "long_break_duration": {"value": "30", "desc": "Long break duration in minutes (e.g., 30)."},
    "lab_block_duration": {"value": "2", "desc": "Standard lab block duration in hours (e.g., 2)."},
}

@settings_bp.route("/", methods=["GET"])
@token_required
def get_settings(current_user):
    if current_user.role != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    # Seed defaults if empty
    existing = {s.key: s for s in SystemSetting.query.all()}
    needs_commit = False
    
    for k, v in DEFAULT_SETTINGS.items():
        if k not in existing:
            setting = SystemSetting(key=k, value=v["value"], description=v["desc"])
            db.session.add(setting)
            existing[k] = setting
            needs_commit = True
            
    if needs_commit:
        db.session.commit()

    return jsonify([{
        "key": s.key,
        "value": s.value,
        "description": s.description,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None
    } for s in existing.values()]), 200

@settings_bp.route("/<key>", methods=["PUT"])
@token_required
def update_setting(current_user, key):
    if current_user.role != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    if "value" not in data:
        return jsonify({"error": "Value required"}), 400

    setting = SystemSetting.query.get(key)
    if not setting:
        return jsonify({"error": "Setting not found"}), 404

    setting.value = str(data["value"])
    db.session.commit()

    return jsonify({"message": "Setting updated successfully"}), 200

@settings_bp.route("/bulk", methods=["PUT"])
@token_required
def update_bulk_settings(current_user):
    if current_user.role != "admin":
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    if not isinstance(data, dict):
        return jsonify({"error": "Invalid format, dict expected"}), 400

    for key, value in data.items():
        setting = SystemSetting.query.get(key)
        if setting:
            setting.value = str(value)
            
    db.session.commit()
    return jsonify({"message": "Settings updated successfully"}), 200
