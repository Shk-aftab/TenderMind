import os
from flask import Flask, request, redirect, url_for, render_template, jsonify
from werkzeug.utils import secure_filename
from models import Tender
from extensions import db
import json

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'

# Configure the database URI and any other settings
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tenders.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False  # This is optional but recommended to avoid warnings

# Initialize db with the Flask app
db.init_app(app)

# Create the database tables if they don't exist
with app.app_context():
    db.create_all()




@app.route("/")
def index():
    return render_template("index.html")

# Corrected the spelling of the route here
@app.route("/dashboard",  methods=['GET', 'POST'])
def dashboard():
    tenders = Tender.query.all()
    print(tenders)
    return render_template('dashboard.html', tenders=tenders)

@app.route('/create_tender', methods=['POST'])
def create_tender():
    name = request.form['name']
    file = request.files['file']

    if file:
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Ensure the uploads directory exists
        if not os.path.exists(app.config['UPLOAD_FOLDER']):
            os.makedirs(app.config['UPLOAD_FOLDER'])

        file.save(file_path)

        # Send file to RAG and get response (simulate here)
        rag_output = send_to_rag_application(file_path)

        # Save tender data
        new_tender = Tender(name=name, json_data=json.dumps(rag_output))
        db.session.add(new_tender)
        db.session.commit()

    return redirect(url_for('dashboard'))


# Route to handle file upload and save tender data
@app.route('/upload_tender/<int:tender_id>', methods=['POST'])
def upload_tender(tender_id):
    file = request.files['file']
    tender = Tender.query.get_or_404(tender_id)

    if file:
        filename = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filename)

        # Placeholder for sending to RAG application
        rag_output = send_to_rag_application(filename)

        # Update the tender with the RAG output (json data)
        tender.json_data = json.dumps(rag_output)
        db.session.commit()

    return redirect(url_for('dashboard'))


def send_to_rag_application(filename):
    # This function will handle sending the file to RAG and getting the JSON response.
    # Here, we use a mock response for demonstration purposes.
    return {
    "Overview": {
        "Tender Title": "Not Provided",
        "Issuing Company": "Not Provided",
        "Deadline": "Not Provided",
        "Reference Number": "Not Provided"
    },
    "Cost Information": {
        "Budget Information": "Es ist zu erwarten, dass das Projekt signifikant in das Budget eingreift, aber eine detaillierte Kostenübersicht wird in der Verhandlungsphase besprochen.",
        "Payment Terms": "Not Provided",
        "Cost Breakdown": "Not Provided"
    },
    "Key Objectives": "Entwicklung einer umfassenden Vertriebssoftware-Lösung, die Außendienstmitarbeiter unterstützt, Angebote generiert und Innendienst-Vertriebsaktivitäten verwaltet.",
    "General Requirements": "- Multi-Plattform-Kompatibilität mit Windows, macOS, Android und iOS. - Benutzerfreundlichkeit mit intuitiver Benutzeroberfläche und Unterstützung für verschiedene Mitarbeiter-Level. - Hochgradige Sicherheit mit Datenschutzstandards, Verschlüsselung und rollenbasierter Zugangskontrolle. - Nahtlose Integration mit bestehenden und zukünftigen IT-Systemen.",
    "Special Requirements": "- Geolokalisierungsintegration für optimierte Kundenbesuche und Routenplanung. - Echtzeit-Produkt- und Lagerbestandsinformationen für Außendienstmitarbeiter. - Augmented Reality (AR) für mobile Produktdemonstrationen. - KPI-Tracking und Aufgabenverwaltung für Innendienst-Vertriebsaktivitäten.",
    "Phases and Milestones": {
        "Anforderungsanalyse": "0-1 Monat",
        "Design und Architekturplanung": "1-2 Monate",
        "Entwicklung und Implementierung": "3-9 Monate",
        "Testphase": "9-10 Monate",
        "Schulung und Einführung": "10-11 Monate",
        "Abnahme und Übergabe": "12. Monat"
    },
    "Submission Guidelines": "Not Provided",
    "Technical Specifications": "- Agile Entwicklungsmethoden (Scrum/Kanban) - Meilensteinplanung mit regelmäßigen Überprüfungen - API-Dokumentation, Benutzerhandbücher und Schulungsmaterialien - Offline-Funktionalität für Außendienstmitarbeiter - Automatische Angebotsübersetzung mit Berücksichtigung kultureller Nuancen",
    "Legal and Compliance Requirements": "ISO 27001 Zertifizierung und Compliance-Dokumentation",
    "Support and Maintenance": "- Mindestens 24 Monate Garantie nach Abnahme - Kostenlose Fixes für sicherheitsrelevante und kritische Fehler - Umfangreiche Support- und Wartungsverträge mit 24/7-Support und SLA - Schulungsprogramme für Benutzer und Administratoren",
    "Project Team and Qualifications": "Not Provided",
    "Contact Information": {
        "Name": "Not Provided",
        "Email": "Not Provided",
        "Phone": "Not Provided",
        "Address": "Not Provided"
    }
}


# Reusable store function
def store_tender_data(tender_id, json_data):
    tender = Tender.query.get_or_404(tender_id)
    tender.json_data = json.dumps(json_data)
    db.session.commit()

@app.route('/get_tender_data/<int:tender_id>', methods=['GET'])
def get_tender_data(tender_id):
    tender = Tender.query.get_or_404(tender_id)
    tender_data = json.loads(tender.json_data)

    card_data = []
    for i, (title, content) in enumerate(tender_data.items()):
        if i >= 4:  # Only display the first 4 key-value pairs
            break
        card_data.append({'title': title, 'content': content})

    print(card_data)

    return jsonify({'card_data': card_data})


@app.route('/process_addons', methods=['POST'])
def process_addons():
    data = request.json
    tender_id = data.get('tender_id')
    selected_addons = data.get('addons', [])

    # Retrieve the tender data
    tender = Tender.query.get_or_404(tender_id)
    tender_data = json.loads(tender.json_data)

    # Collect selected addons data
    card_data_addons = []
    for addon in selected_addons:
        if addon in tender_data:
            card_data_addons.append({
                'title': addon,
                'content': tender_data[addon]
            })

    return jsonify({'card_data_addons': card_data_addons})




@app.route('/get_response', methods=['POST'])
def get_response():
    data = request.get_json()
    user_message = data.get('message')

    # Here you can process the user message and generate a response
    # For now, we'll just return a simple response
    bot_response = f"You said: {user_message}"

    # You can replace the below with logic to retrieve information from your document
    source_info = "CPQ Tender (Page 5)"  # Example source information

    return jsonify({'response': bot_response, 'source': source_info})


@app.route("/about")
def about():
    return render_template("about.html", app_data=app_data)


@app.route("/service")
def service():
    return render_template("service.html", app_data=app_data)


@app.route("/contact")
def contact():
    return render_template("contact.html", app_data=app_data)


if __name__ == "__main__":
    app.run(debug=True)
