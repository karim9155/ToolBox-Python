import os
from utils.visual_parser import VisualParser
from utils.pdf_analyzer import PDFAnalyzer
from utils.data_models import StandardNode

def extract_fssc(pdf_path):
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")
    analyzer = PDFAnalyzer(pdf_path)
    config = analyzer.analyze()
    parser = VisualParser(pdf_path, config)
    nodes = parser.parse()
    document_id = os.path.basename(pdf_path) + "_" + str(int(os.path.getmtime(pdf_path)))
    flat_nodes = []
    for node in nodes:
        flat_nodes.extend(node.to_flat_list(document_id))
    return flat_nodes