from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token
from models import db, ClassGroup, Teacher, User

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

from functools import wraps
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()
        user_id = get_jwt_identity()
        current_user = User.query.get(user_id)
        if not current_user:
            return jsonify({"error": "User not found"}), 404
        return f(current_user, *args, **kwargs)
    return decorated


@auth_bp.post("/seed-admin")
def seed_admin():
    admin = User.query.filter_by(username="admin").first()
    if admin:
        admin.role = "admin"
        admin.teacher_id = None
        admin.class_id = None
        admin.set_password("adimn")
        db.session.commit()
        return jsonify({"message": "Admin credentials reset", "username": "admin", "password": "adimn"}), 200

    admin = User(username="admin", role="admin")
    admin.set_password("adimn")
    db.session.add(admin)
    db.session.commit()
    return jsonify({"message": "Admin created", "username": "admin", "password": "adimn"}), 201


@auth_bp.post("/login")
def login():
    data = request.get_json() or {}
    user = User.query.filter_by(username=data.get("username", "")).first()
    if not user or not user.check_password(data.get("password", "")):
        return jsonify({"error": "Invalid credentials"}), 401
    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    return jsonify(
        {
            "access_token": token,
            "user": {
                "id": user.id,
                "username": user.username,
                "role": user.role,
                "teacher_id": user.teacher_id,
                "class_id": user.class_id,
            },
        }
    )


@auth_bp.post("/register")
def register():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "student")

    if role not in ["teacher", "student"]:
        return jsonify({"error": "Only teacher or student self-registration is allowed"}), 400
    if not username or len(password) < 6:
        return jsonify({"error": "Username required and password must be at least 6 characters"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username already exists"}), 409

    teacher_id = data.get("teacher_id")
    class_id = data.get("class_id")

    if role == "teacher":
        if teacher_id:
            teacher = Teacher.query.get(teacher_id)
            if not teacher:
                return jsonify({"error": "Teacher not found"}), 404
        else:
            name = data.get("name", username)
            teacher = Teacher(name=name, max_lectures_per_day=data.get("max_lectures_per_day", 6))
            db.session.add(teacher)
            db.session.flush()
        teacher_id = teacher.id
        class_id = None

    if role == "student":
        if not class_id:
            return jsonify({"error": "class_id is required for student registration"}), 400
        if not ClassGroup.query.get(class_id):
            return jsonify({"error": "Class not found"}), 404
        teacher_id = None

    user = User(username=username, role=role, teacher_id=teacher_id, class_id=class_id)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify({"message": "Registered successfully"}), 201


@auth_bp.get("/register-options")
def register_options():
    classes = ClassGroup.query.order_by(ClassGroup.name).all()
    return jsonify({"classes": [{"id": c.id, "name": c.name, "department": c.department} for c in classes]})
