from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file
from flask_login import login_user, logout_user, login_required, current_user
from app.models import (
    User,
    Client,
    ChecklistItem,
    ChecklistRecord,
    ChecklistTemplate,
    CompletedItem,
    TemplateItem,
    ChecklistCategory,
)
from app import db
from sqlalchemy import func, text
from datetime import datetime, timedelta

from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

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
    
    # Get the default template
    default_template = ChecklistTemplate.query.filter_by(is_default=True).first()
    if not default_template:
        flash("No default template found. Please create one first.")
        return redirect(url_for("main.dashboard"))
    
    # Get all categories for this template
    categories = ChecklistCategory.query.filter_by(template_id=default_template.id).all()
    
    items_by_category = {}
    for category in categories:
        # Get existing items for this client and category
        items = ChecklistItem.query.filter_by(
            client_id=client_id,
            category_id=category.id
        ).all()
        
        # If no items exist, create them from template
        if not items:
            template_items = TemplateItem.query.filter_by(
                template_id=default_template.id,
                category_id=category.id
            ).all()
            
            items = []
            for template_item in template_items:
                item = ChecklistItem(
                    client_id=client_id,
                    description=template_item.description,
                    category_id=category.id,
                    completed=False
                )
                db.session.add(item)
                items.append(item)
            
            db.session.commit()
        
        items_by_category[category] = items

    return render_template(
        "checklist.html",
        client=client,
        items_by_category=items_by_category
    )

@main.route("/submit_checklist", methods=["POST"])
@login_required
def submit_checklist():
    client_id = request.form.get("client_id")
    if not client_id:
        flash("No client specified")
        return redirect(url_for("main.dashboard"))
        
    completed_item_ids = request.form.getlist("items")
    
    # Create a new checklist record
    record = ChecklistRecord(
        client_id=client_id,
        user_id=current_user.id
    )
    db.session.add(record)
    db.session.commit()
    
    # Get all checklist items for this client
    client_items = ChecklistItem.query.filter_by(client_id=client_id).all()
    
    # Create completed items entries
    for item in client_items:
        completed_item = CompletedItem(
            record_id=record.id,
            checklist_item_id=item.id,
            completed=str(item.id) in completed_item_ids
        )
        db.session.add(completed_item)
    
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

@main.route("/export-client-report/<int:client_id>")
@login_required
def export_client_report(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    client = Client.query.get_or_404(client_id)
    records = db.session.execute(
        text('''
            SELECT 
                cr.date_performed as date_performed,
                us.username as username,
                che.category as category,
                che.description as description,
                com.completed as completed,
                (SELECT COUNT(*) 
                 FROM completed_item ci 
                 WHERE ci.record_id = cr.id AND ci.completed = true) as completed_count
            FROM completed_item com
            JOIN checklist_record cr ON cr.id = com.record_id 
            JOIN user us ON us.id = cr.user_id
            JOIN checklist_item che ON che.id = com.checklist_item_id
            WHERE cr.client_id = :client_id
            ORDER BY cr.date_performed DESC'''),
        {"client_id": client_id}
    )

    buffer = BytesIO()
    
    # Create the PDF object with wider margins
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,  # Reduced margins (0.5 inch)
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    elements = []
    styles = getSampleStyleSheet()
    title_style = styles['Heading1']
    
    # Add title
    elements.append(Paragraph(f"Checklist Report - {client.name}", title_style))
    elements.append(Spacer(1, 20))
    
    # Generate report date
    report_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    elements.append(Paragraph(f"Generated: {report_date}", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Calculate column widths as percentages of page width
    page_width = letter[0] - 72  # Total width minus margins
    col_widths = [
        page_width * 0.15,  # Date
        page_width * 0.15,  # Performed by
        page_width * 0.15,  # Category
        page_width * 0.40,  # Item (wider for long descriptions)
        page_width * 0.15   # Status
    ]

    # Prepare data for the table
    table_data = [['Date', 'Performed by', 'Category', 'Item', 'Status']]
    
    for record in records:
        date_performed = datetime.fromisoformat(record.date_performed)
        table_data.append([
            date_performed.strftime('%Y-%m-%d %H:%M'),
            record.username,
            record.category,
            Paragraph(record.description, styles['Normal']),  # Wrap long text
            'Completed' if record.completed else 'Not Completed'
        ])

    if len(table_data) > 1:
        table = Table(table_data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),  # Align text to top
            ('WORDWRAP', (0, 0), (-1, -1), True),  # Enable word wrapping
            ('LEFTPADDING', (0, 0), (-1, -1), 6),  # Add some padding
            ('RIGHTPADDING', (0, 0), (-1, -1), 6)
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("No records found", styles['Normal']))

    # Build PDF
    doc.build(elements)
    
    pdf = buffer.getvalue()
    buffer.close()
    
    return send_file(
        BytesIO(pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'{client.name}_checklist_report.pdf'
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
            db.session.commit()

            # Get the template
            template = ChecklistTemplate.query.get(template_id) if template_id else ChecklistTemplate.query.filter_by(is_default=True).first()

            if template:
                # Create checklist items from template items
                template_items = TemplateItem.query.filter_by(template_id=template.id).all()
                for template_item in template_items:
                    checklist_item = ChecklistItem(
                        client_id=new_client.id,
                        description=template_item.description,
                        category_id=template_item.category_id,
                        completed=False
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

@main.route('/add-category/<int:template_id>', methods=['POST'])
@login_required
def add_category(template_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    category = ChecklistCategory(
        name=data['name'],
        template_id=template_id
    )
    db.session.add(category)
    db.session.commit()
    return jsonify({'status': 'success'})

@main.route('/delete-category/<int:category_id>', methods=['POST'])
@login_required
def delete_category(category_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    category = ChecklistCategory.query.get_or_404(category_id)
    db.session.delete(category)
    db.session.commit()
    return jsonify({'status': 'success'})

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
    categories = ChecklistCategory.query.filter_by(template_id=template_id).all()

    if request.method == "POST":
        try:
            data = request.get_json()
            if not data or 'items' not in data:
                return jsonify({"status": "error", "message": "No items data provided"}), 400

            # Begin transaction
            # Delete existing template items
            TemplateItem.query.filter_by(template_id=template_id).delete()

            # Add new items
            for item_data in data['items']:
                if 'description' not in item_data or 'category_id' not in item_data:
                    continue
                    
                new_item = TemplateItem(
                    description=item_data['description'],
                    category_id=item_data['category_id'],
                    template_id=template_id
                )
                db.session.add(new_item)

            db.session.commit()
            return jsonify({"status": "success"})

        except Exception as e:
            db.session.rollback()
            print(f"Error saving template: {str(e)}")  # For debugging
            return jsonify({"status": "error", "message": str(e)}), 500

    # GET request - render the template edit form
    template_items = TemplateItem.query.filter_by(template_id=template_id).all()
    return render_template(
        "edit_template.html", 
        template=template, 
        categories=categories
    )

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


