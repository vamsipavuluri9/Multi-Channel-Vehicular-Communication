from flask import Flask, request, jsonify
import os
from datetime import datetime

app = Flask(__name__)

# Folder where uploaded files will be saved
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploaded_pcaps')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

@app.route('/')
def home():
    return "Flask Central Server is Running!"

@app.route('/upload_pcap', methods=['POST'])
def upload_pcap():
    if 'pcap_file' not in request.files:
        return jsonify({"message": "No file part in request"}), 400

    file = request.files['pcap_file']
    
    if file.filename == '':
        return jsonify({"message": "No file selected"}), 400

    laptop_id = request.form.get('laptop_id', 'Unknown_Laptop')
    laptop_folder = os.path.join(app.config['UPLOAD_FOLDER'], laptop_id)
    os.makedirs(laptop_folder, exist_ok=True)

    save_path = os.path.join(laptop_folder, file.filename)
    file.save(save_path)

    return jsonify({"message": f"File '{file.filename}' uploaded successfully"}), 200

@app.route('/get_dummy_message', methods=['GET'])
def get_dummy_message():
    laptop_id = request.args.get('laptop_id')

    if not laptop_id:
        return {"message": "Missing laptop_id"}, 400

    # Dynamically generate dummy message at poll time
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg = (f"Hello from Central Server! You are currently out of RSU zone.\n"
           f"Your ID: {laptop_id}\n"
           f"Timestamp: {timestamp}")

    return {"message": msg}, 200

if __name__ == '__main__':
    app.run(debug=True)
