from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from app.models import (
    User,
    Client,
    ChecklistItem,
    ChecklistRecord,
    ChecklistTemplate,
    TemplateItem,
)
from app import db
from sqlalchemy import func
from datetime import datetime, timedelta

main = Blueprint("main", __name__)

@main.route("/")
@login_required
def dashboard():
    # Only get active clients
    clients = Client.query.filter_by(is_active=True).all()
    return render_template("dashboard.html", clients=clients)


@main.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username")).first()
        if user and user.check_password(request.form.get("password")):
            login_user(user)
            return redirect(url_for("main.dashboard"))
        flash("Invalid username or password")
    return render_template("login.html")


@main.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.login"))


@main.route("/client/<int:client_id>", methods=["GET"])
@login_required
def client_checklist(client_id):
    client = Client.query.get_or_404(client_id)
    # Get the template associated with this client
    server_items = ChecklistItem.query.filter_by(client_id=client_id, category="Server").all()
    desktop_items = ChecklistItem.query.filter_by(client_id=client_id, category="Desktop").all()
    return render_template(
        "checklist.html",
        client=client,
        server_items=server_items,
        desktop_items=desktop_items,
    )

@main.route("/submit_checklist", methods=["POST"])
@login_required
def submit_checklist():
    client_id = request.form.get("client_id")

    record = ChecklistRecord(client_id=client_id, user_id=current_user.id)
    db.session.add(record)
    db.session.commit()

    completed_items = list(map(int, request.form.getlist("items")))
    # update all items that were completed
    db.session.query(ChecklistItem).filter(ChecklistItem.id.in_(completed_items)).update(
        {"completed": True, "record_id": record.id}
    )
    # uncheck all items that were not completed
    db.session.query(ChecklistItem).filter(~ChecklistItem.id.in_(completed_items)).filter(ChecklistItem.client_id==client_id).update({"completed": False, "record_id": None})
    db.session.commit()
    flash("Checklist submitted successfully")
    return redirect(url_for("main.dashboard"))


@main.route("/reports")
@login_required
def reports():
    if not current_user.is_admin:
        flash("Access denied. Admin privileges required.")
        return redirect(url_for("main.dashboard"))

    # Get all clients and users for the dropdowns
    clients = Client.query.all()
    users = User.query.all()

    return render_template("reports.html", clients=clients, users=users)


@main.route("/reports/client/<int:client_id>")
@login_required
def client_report(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    client = Client.query.get_or_404(client_id)
    records = (
        ChecklistRecord.query.filter_by(client_id=client_id)
        .order_by(ChecklistRecord.date_performed.desc())
        .all()
    )

    return render_template("client_report.html", client=client, records=records)


@main.route("/reports/user/<int:user_id>")
@login_required
def user_report(user_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    user = User.query.get_or_404(user_id)
    records = (
        ChecklistRecord.query.filter_by(user_id=user_id)
        .order_by(ChecklistRecord.date_performed.desc())
        .all()
    )

    return render_template("user_report.html", user=user, records=records)


@main.route("/reports/summary")
@login_required
def summary_report():
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    # Get last 30 days of activity
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)

    # Summary statistics
    total_checks = ChecklistRecord.query.count()
    recent_checks = ChecklistRecord.query.filter(
        ChecklistRecord.date_performed >= thirty_days_ago
    ).count()
    total_clients = Client.query.count()
    total_users = User.query.count()

    # Most active clients
    active_clients = (
        db.session.query(Client, func.count(ChecklistRecord.id).label("check_count"))
        .join(ChecklistRecord)
        .group_by(Client)
        .order_by(func.count(ChecklistRecord.id).desc())
        .limit(5)
        .all()
    )

    # Most active users
    active_users = (
        db.session.query(User, func.count(ChecklistRecord.id).label("check_count"))
        .join(ChecklistRecord)
        .group_by(User)
        .order_by(func.count(ChecklistRecord.id).desc())
        .limit(5)
        .all()
    )

    return render_template(
        "summary_report.html",
        total_checks=total_checks,
        recent_checks=recent_checks,
        total_clients=total_clients,
        total_users=total_users,
        active_clients=active_clients,
        active_users=active_users,
    )


@main.route("/manage-clients")
@login_required
def manage_clients():
    if not current_user.is_admin:
        flash("Access denied. Admin privileges required.")
        return redirect(url_for("main.dashboard"))

    clients = Client.query.all()
    templates = ChecklistTemplate.query.all()
    return render_template("manage_clients.html", clients=clients, templates=templates)


@main.route("/add-client", methods=["POST"])
@login_required
def add_client():
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    client_name = request.form.get("client_name")
    template_id = request.form.get("template_id")

    if client_name:
        if Client.query.filter_by(name=client_name).first():
            flash("A client with this name already exists.")
        else:
            new_client = Client(name=client_name, is_active=True)
            db.session.add(new_client)
            db.session.commit()  # Commit to get the new client ID

            # Get the template - either selected or default
            template = None
            if template_id:
                template = ChecklistTemplate.query.get(template_id)
            if not template:
                template = ChecklistTemplate.query.filter_by(is_default=True).first()

            if template:
                # Create checklist items from template items
                for template_item in template.items:
                    checklist_item = ChecklistItem(
                        client_id=new_client.id,
                        description=template_item.description,
                        category=template_item.category,
                        completed=False,
                    )
                    db.session.add(checklist_item)

            db.session.commit()
            flash("Client added successfully.")

    return redirect(url_for("main.manage_clients"))


@main.route("/delete-template/<int:template_id>", methods=["POST"])
@login_required
def delete_template(template_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    template = ChecklistTemplate.query.get_or_404(template_id)

    try:
        # Delete associated template items first (should happen automatically with cascade)
        db.session.delete(template)
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@main.route("/toggle-client/<int:client_id>")
@login_required
def toggle_client(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    client = Client.query.get_or_404(client_id)
    client.is_active = not client.is_active
    db.session.commit()
    status = "activated" if client.is_active else "archived"
    flash(f"Client {client.name} has been {status}.")
    return redirect(url_for("main.manage_clients"))


@main.route("/manage-users")
@login_required
def manage_users():
    if not current_user.is_admin:
        flash("Access denied. Admin privileges required.")
        return redirect(url_for("main.dashboard"))

    users = User.query.all()
    return render_template("manage_users.html", users=users)


@main.route("/add-user", methods=["POST"])
@login_required
def add_user():
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    username = request.form.get("username")
    password = request.form.get("password")
    is_admin = request.form.get("is_admin") == "true"

    if username and password:
        if User.query.filter_by(username=username).first():
            flash("Username already exists.")
        else:
            new_user = User(username=username, is_admin=is_admin)
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash("User added successfully.")
    return redirect(url_for("main.manage_users"))


@main.route("/delete-user/<int:user_id>")
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    if current_user.id == user_id:
        flash("Cannot delete your own account.")
        return redirect(url_for("main.manage_users"))

    user = User.query.get_or_404(user_id)
    db.session.delete(user)
    db.session.commit()
    flash(f"User {user.username} has been deleted.")
    return redirect(url_for("main.manage_users"))


@main.route("/reset_password/<int:user_id>", methods=["POST"])
@login_required
def reset_password(user_id):
    if not current_user.is_admin:
        flash("Only administrators can reset passwords.")
        return redirect(url_for("main.manage_users"))

    user = User.query.get_or_404(user_id)
    new_password = request.form.get("new_password")

    if new_password:
        user.set_password(new_password)
        db.session.commit()
        flash(f"Password reset successfully for {user.username}")

    return redirect(url_for("main.manage_users"))


@main.route("/manage-templates")
@login_required
def manage_templates():
    if not current_user.is_admin:
        flash("Access denied. Admin privileges required.")
        return redirect(url_for("main.dashboard"))

    templates = ChecklistTemplate.query.all()
    return render_template("manage_templates.html", templates=templates)


@main.route("/add-template", methods=["POST"])
@login_required
def add_template():
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    name = request.form.get("template_name")
    is_default = request.form.get("is_default") == "true"

    if name:
        template = ChecklistTemplate(name=name, is_default=is_default)
        db.session.add(template)
        db.session.commit()
        flash("Template added successfully")

    return redirect(url_for("main.manage_templates"))


@main.route("/edit-template/<int:template_id>", methods=["GET", "POST"])
@login_required
def edit_template(template_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    template = ChecklistTemplate.query.get_or_404(template_id)

    if request.method == "POST":
        # Handle template item updates
        items_data = request.get_json()

        # Clear existing items
        TemplateItem.query.filter_by(template_id=template_id).delete()

        # Add new items
        for item in items_data:
            new_item = TemplateItem(
                description=item["description"],
                category=item["category"],
                template_id=template_id,
            )
            db.session.add(new_item)

        db.session.commit()
        return {"status": "success"}

    return render_template("edit_template.html", template=template)


@main.route("/edit-client-checklist/<int:client_id>", methods=["GET", "POST"])
@login_required
def edit_client_checklist(client_id):
    client = Client.query.get_or_404(client_id)

    if request.method == "POST":
        # Handle client checklist updates
        items_data = request.get_json()

        # Clear existing items
        client_checklist.query.filter_by(client_id=client_id).delete()

        # Add new items
        for item in items_data:
            new_item = client_checklist(
                description=item["description"],
                category=item["category"],
                client_id=client_id,
            )
            db.session.add(new_item)

        db.session.commit()
        return {"status": "success"}

    return render_template("edit_client_checklist.html", client=client)


@main.route("/delete-client/<int:client_id>", methods=["POST"])
@login_required
def delete_client(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    client = Client.query.get_or_404(client_id)

    try:
        # Delete associated records first
        ChecklistRecord.query.filter_by(client_id=client_id).delete()
        db.session.delete(client)
        db.session.commit()
        flash(f"Client {client.name} has been deleted.")
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting client: {str(e)}")

    return redirect(url_for("main.manage_clients"))


