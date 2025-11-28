# routes/fssc_api.py
from flask import Blueprint, request, jsonify
from services.fssc_service import extract_fssc

fssc_bp = Blueprint('fssc_bp', __name__)

@fssc_bp.route('/extract/fssc', methods=['POST'])
def extract_fssc_endpoint():
    pdf_path = request.json.get('pdf_path')
    if not pdf_path:
        return jsonify({'error': 'Missing pdf_path'}), 400
    try:
        result = extract_fssc(pdf_path)
        return jsonify({'nodes': result})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
