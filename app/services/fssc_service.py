import os
import tempfile
from app.utils.visual_parser import VisualParser
from app.utils.pdf_analyzer import PDFAnalyzer
from app.utils.data_models import StandardNode

def extract_fssc(file_bytes):
    # Save the uploaded file bytes to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name
    try:
        analyzer = PDFAnalyzer(tmp_path)
        config = analyzer.analyze()
        parser = VisualParser(tmp_path, config)
        nodes = parser.parse()
        document_id = os.path.basename(tmp_path)
        flat_nodes = []
        for node in nodes:
            flat_nodes.extend(node.to_flat_list(document_id))
        # Sort by display_order before returning
        flat_nodes.sort(key=lambda n: n["display_order"])
        return flat_nodes
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass