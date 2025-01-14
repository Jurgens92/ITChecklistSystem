from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, send_file, session
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
    ChecklistNotes,
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

@main.route("/toggle-admin/<int:user_id>", methods=["POST"])
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))

    if current_user.id == user_id:
        flash("Cannot change your own admin status")
        return redirect(url_for("main.manage_users"))

    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    
    new_role = "admin" if user.is_admin else "standard user"
    flash(f"Changed {user.username}'s role to {new_role}")
    return redirect(url_for("main.manage_users"))

@main.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("main.login"))


@main.route("/client/<int:client_id>", methods=["GET"])
@login_required
def client_checklist(client_id):
    client = Client.query.get_or_404(client_id)
    
    # Get all available templates for the dropdown
    templates = ChecklistTemplate.query.all()  # Add this line
    
    # Get all items for this client
    items_by_category = {}
    categories = ChecklistCategory.query.all()
    
    for category in categories:
        # Get existing items for this client and category
        items = ChecklistItem.query.filter_by(
            client_id=client_id,
            category_id=category.id
        ).all()
        
        if items:  # Only add categories that have items
            items_by_category[category] = items

    # If no items exist, create them from the client's template
    if not items_by_category:
        # Get the client's template from the most recent addition
        template = ChecklistTemplate.query.get(request.args.get('template_id', type=int))
        
        if not template:
            # Fallback to default template
            template = ChecklistTemplate.query.filter_by(is_default=True).first()
        
        if template:
            categories = ChecklistCategory.query.filter_by(template_id=template.id).all()
            
            for category in categories:
                template_items = TemplateItem.query.filter_by(
                    template_id=template.id,
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
                
                if items:  # Only add categories that have items
                    items_by_category[category] = items
            
            db.session.commit()

    return render_template(
        "checklist.html",
        client=client,
        items_by_category=items_by_category,
        templates=templates
    )

@main.route("/submit_checklist", methods=["POST"])
@login_required
def submit_checklist():
    client_id = request.form.get("client_id")
    if not client_id:
        flash("No client specified")
        return redirect(url_for("main.dashboard"))
        
    completed_item_ids = request.form.getlist("items")
    notes_text = request.form.get("notes", "")
    
    try:
        # Create a new checklist record
        record = ChecklistRecord(
            client_id=client_id,
            user_id=current_user.id
        )
        db.session.add(record)
        db.session.flush()  # Get the record ID
        
        # Add notes if provided
        if notes_text and notes_text.strip():
            notes = ChecklistNotes(
                checklist_record_id=record.id,
                note_text=notes_text.strip(),
                user_id=current_user.id
            )
            db.session.add(notes)
        
        # Get all items for this client
        client_items = ChecklistItem.query.filter_by(client_id=client_id).all()
        
        # Create CompletedItem entries and build summary data
        summary_data = {}
        for item in client_items:
            completed = str(item.id) in completed_item_ids
            completed_item = CompletedItem(
                record_id=record.id,
                checklist_item_id=item.id,
                completed=completed
            )
            db.session.add(completed_item)
            
            # Build summary data for completed items
            if completed:
                category = ChecklistCategory.query.get(item.category_id)
                if category.name not in summary_data:
                    summary_data[category.name] = []
                summary_data[category.name].append(item.description)
        
        db.session.commit()

        # Only return JSON if it's an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'status': 'success',
                'summary': summary_data,
                'notes': notes_text.strip(),
                'clearStorage': True,
                'clientId': client_id
            })
        
        # For regular form submit, store data in session and redirect
        session['checklist_summary'] = {
            'summary': summary_data,
            'notes': notes_text.strip()
        }
        # Return HTML with script to clear localStorage before redirecting
        return f"""
        <script>
            localStorage.removeItem('checklist_state_{client_id}');
            window.location.href = '{url_for("main.checklist_summary")}';
        </script>
        """
        
    except Exception as e:
        db.session.rollback()
        flash(f"Error submitting checklist: {str(e)}")
        return redirect(url_for("main.dashboard"))

@main.route("/checklist-summary")
@login_required
def checklist_summary():
    summary_data = session.pop('checklist_summary', None)
    if not summary_data:
        return redirect(url_for('main.dashboard'))
    return render_template('checklist_summary.html', summary=summary_data)

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
    
    # Get records with completed counts
    records = ChecklistRecord.query.filter_by(client_id=client_id)\
        .order_by(ChecklistRecord.date_performed.desc())\
        .all()
    
    return render_template(
        "client_report.html", 
        client=client, 
        records=records
    )


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
    
    # Get all checklist records for this client with their completed items
    records = ChecklistRecord.query.filter_by(client_id=client_id)\
        .order_by(ChecklistRecord.date_performed.desc())\
        .all()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    elements = []
    styles = getSampleStyleSheet()
    
    # Add title
    elements.append(Paragraph(f"Checklist Report - {client.name}", styles['Heading1']))
    elements.append(Spacer(1, 20))
    
    # Add report date
    report_date = datetime.now().strftime("%Y-%m-%d %H:%M")
    elements.append(Paragraph(f"Generated: {report_date}", styles['Normal']))
    elements.append(Spacer(1, 20))

    # Prepare table data
    table_data = [['Date', 'Performed By', 'Category', 'Item', 'Status']]
    
    for record in records:
        # Get all completed items for this record
        completed_items = CompletedItem.query.filter_by(record_id=record.id).all()
        
        # Get notes for this record
        notes = ChecklistNotes.query.filter_by(checklist_record_id=record.id).first()
        
        for completed_item in completed_items:
            # Get the checklist item details
            checklist_item = ChecklistItem.query.get(completed_item.checklist_item_id)
            if checklist_item:
                category = ChecklistCategory.query.get(checklist_item.category_id)
                category_name = category.name if category else "No Category"
                
                table_data.append([
                    record.date_performed.strftime('%Y-%m-%d %H:%M'),
                    record.user.username,
                    category_name,
                    Paragraph(checklist_item.description, styles['Normal']),
                    'Completed' if completed_item.completed else 'Not Completed'
                ])
        
        # Add notes if they exist
        if notes:
            # Add a spacer row
            table_data.append(['', '', '', '', ''])
            # Add the notes row
            table_data.append([
                record.date_performed.strftime('%Y-%m-%d %H:%M'),
                record.user.username,
                'Notes',
                Paragraph(notes.note_text, styles['Normal']),
                ''
            ])
            # Add another spacer row
            table_data.append(['', '', '', '', ''])

    if len(table_data) > 1:
        # Calculate column widths
        page_width = letter[0] - 72
        col_widths = [
            page_width * 0.15,  # Date
            page_width * 0.15,  # Performed by
            page_width * 0.15,  # Category
            page_width * 0.40,  # Item
            page_width * 0.15   # Status
        ]

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
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('WORDWRAP', (0, 0), (-1, -1), True)
        ]))
        elements.append(table)
    else:
        elements.append(Paragraph("No records found for this client", styles['Normal']))

    doc.build(elements)
    buffer.seek(0)
    
    return send_file(
        buffer,
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
        # Check for existing client
        if Client.query.filter_by(name=client_name).first():
            flash("A client with this name already exists.")
            return redirect(url_for("main.manage_clients"))
            
        try:
            # Create new client
            new_client = Client(name=client_name, is_active=True)
            db.session.add(new_client)
            db.session.flush()  # Get the client ID
            
            # Apply template
            if template_id:
                template = ChecklistTemplate.query.get(int(template_id))
            else:
                template = ChecklistTemplate.query.filter_by(is_default=True).first()
            
            if template:
                # Get all template items with categories
                template_items = db.session.query(
                    TemplateItem, ChecklistCategory
                ).join(
                    ChecklistCategory, 
                    TemplateItem.category_id == ChecklistCategory.id
                ).filter(
                    TemplateItem.template_id == template.id
                ).all()
                
                # Create checklist items
                for template_item, category in template_items:
                    item = ChecklistItem(
                        client_id=new_client.id,
                        description=template_item.description,
                        category_id=category.id,
                        completed=False
                    )
                    db.session.add(item)
                
            db.session.commit()
            flash(f"Client added successfully with template {template.name if template else 'None'}")
            
        except Exception as e:
            db.session.rollback()
            flash(f"Error creating client: {str(e)}")
            
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
    
    if request.method == "POST":
        try:
            data = request.get_json()
            if not data:
                return jsonify({"status": "error", "message": "No data provided"}), 400

            # Delete existing template items
            TemplateItem.query.filter_by(template_id=template_id).delete()
            
            # Add new items
            if 'items' in data:
                for item_data in data['items']:
                    if 'description' in item_data and 'category_id' in item_data:
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
            print(f"Error saving template: {str(e)}")  # Debug logging
            return jsonify({"status": "error", "message": str(e)}), 500

    # GET request handling
    categories = ChecklistCategory.query.filter_by(template_id=template_id).all()
    items_by_category = {}
    
    for category in categories:
        items = TemplateItem.query.filter_by(
            template_id=template_id,
            category_id=category.id
        ).all()
        items_by_category[category] = items

    return render_template(
        "edit_template.html",
        template=template,
        categories=categories,
        items_by_category=items_by_category
    )

@main.route("/add-template-to-client/<int:client_id>", methods=["POST"])
@login_required
def add_template_to_client(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))
    
    client = Client.query.get_or_404(client_id)
    template_id = request.form.get('template_id')
    
    if template_id:
        template = ChecklistTemplate.query.get(template_id)
        if template:
            categories = ChecklistCategory.query.filter_by(template_id=template.id).all()
            duplicates_prevented = 0
            items_added = 0
            
            for category in categories:
                template_items = TemplateItem.query.filter_by(
                    template_id=template.id,
                    category_id=category.id
                ).all()
                
                for template_item in template_items:
                    # Check if this item already exists for this client and category
                    existing_item = ChecklistItem.query.filter_by(
                        client_id=client_id,
                        category_id=category.id,
                        description=template_item.description
                    ).first()
                    
                    if not existing_item:
                        checklist_item = ChecklistItem(
                            client_id=client_id,
                            description=template_item.description,
                            category_id=category.id,
                            completed=False
                        )
                        db.session.add(checklist_item)
                        items_added += 1
                    else:
                        duplicates_prevented += 1
            
            try:
                db.session.commit()
                if duplicates_prevented > 0:
                    flash(f"Added {items_added} new items from {template.name} template. "
                          f"Skipped {duplicates_prevented} duplicate items.")
                else:
                    flash(f"Successfully added {items_added} items from {template.name} template.")
            except Exception as e:
                db.session.rollback()
                flash(f"Error adding template: {str(e)}")
    
    return redirect(url_for("main.client_checklist", client_id=client_id))

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

@main.route("/edit-client-structure/<int:client_id>", methods=["GET", "POST"])
@login_required
def edit_client_structure(client_id):
    if not current_user.is_admin:
        flash("Access denied")
        return redirect(url_for("main.dashboard"))
        
    client = Client.query.get_or_404(client_id)
    
    if request.method == "POST":
        try:
            data = request.get_json()
            
            # Clear existing items for this client
            ChecklistItem.query.filter_by(client_id=client_id).delete()
            
            # Add new/updated items
            for category_data in data['categories']:
                category_id = category_data['id']
                items = category_data['items']
                
                for item in items:
                    new_item = ChecklistItem(
                        client_id=client_id,
                        description=item['description'],
                        category_id=category_id,
                        completed=False
                    )
                    db.session.add(new_item)
            
            db.session.commit()
            return jsonify({"status": "success"})
            
        except Exception as e:
            db.session.rollback()
            return jsonify({"status": "error", "message": str(e)}), 500
    
    # GET request - display edit form
    items_by_category = {}
    categories = ChecklistCategory.query.all()
    
    for category in categories:
        items = ChecklistItem.query.filter_by(
            client_id=client_id,
            category_id=category.id
        ).all()
        if items:
            items_by_category[category] = items
    
    return render_template(
        "edit_client_structure.html",
        client=client,
        categories=categories,
        items_by_category=items_by_category
    )

@main.route('/add-custom-category/<int:client_id>', methods=['POST'])
@login_required
def add_custom_category(client_id):
    if not current_user.is_admin:
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.get_json()
    category_name = data.get('name')
    
    if not category_name:
        return jsonify({'error': 'Category name is required'}), 400
        
    try:
        # Find or create a default template
        default_template = ChecklistTemplate.query.filter_by(is_default=True).first()
        if not default_template:
            default_template = ChecklistTemplate(name='Default Template', is_default=True)
            db.session.add(default_template)
            db.session.flush()

        # Create new category associated with the template
        category = ChecklistCategory(
            name=category_name,
            template_id=default_template.id
        )
        db.session.add(category)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'category': {
                'id': category.id,
                'name': category.name
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@main.route("/checklist-detail/<int:record_id>")
@login_required
def checklist_detail(record_id):
    record = ChecklistRecord.query.get_or_404(record_id)
    
    # Get all completed items for this record with their details
    completed_items = db.session.query(
        CompletedItem, ChecklistItem, ChecklistCategory
    ).join(
        ChecklistItem, CompletedItem.checklist_item_id == ChecklistItem.id
    ).join(
        ChecklistCategory, ChecklistItem.category_id == ChecklistCategory.id
    ).filter(
        CompletedItem.record_id == record_id
    ).all()
    
    # Organize items by category
    items_by_category = {}
    for completed_item, checklist_item, category in completed_items:
        if category not in items_by_category:
            items_by_category[category] = []
        
        items_by_category[category].append({
            'description': checklist_item.description,
            'completed': completed_item.completed
        })
    
    # Get the notes
    notes = ChecklistNotes.query.filter_by(checklist_record_id=record_id).first()
    
    return render_template(
        'checklist_detail.html',
        record=record,
        items_by_category=items_by_category,
        notes=notes
    )

@main.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_password = request.form.get("current_password")
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")
        
        if not current_user.check_password(current_password):
            flash("Current password is incorrect")
            return redirect(url_for("main.change_password"))
            
        if new_password != confirm_password:
            flash("New passwords do not match")
            return redirect(url_for("main.change_password"))
            
        if len(new_password) < 6:
            flash("New password must be at least 6 characters long")
            return redirect(url_for("main.change_password"))
            
        current_user.set_password(new_password)
        db.session.commit()
        flash("Password changed successfully")
        return redirect(url_for("main.dashboard"))
        
    return render_template("change_password.html")