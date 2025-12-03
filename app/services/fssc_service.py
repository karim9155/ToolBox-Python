import os
import shutil
import uuid
from app.utils.fssc.preflight import Preflight
from app.utils.fssc.layout_extraction import LayoutExtraction
from app.utils.fssc.header_footer_removal import HeaderFooterRemoval
from app.utils.fssc.font_clustering import FontClustering
from app.utils.fssc.heading_detection import HeadingDetection
from app.utils.fssc.hierarchy_builder import HierarchyBuilder
from app.utils.fssc.tree_flattener import TreeFlattener

class FSSCService:
    def __init__(self, upload_dir="uploads", debug_root="debug"):
        self.upload_dir = upload_dir
        self.debug_root = debug_root
        os.makedirs(self.upload_dir, exist_ok=True)
        os.makedirs(self.debug_root, exist_ok=True)

    def process_file(self, file_content: bytes, filename: str):
        # Create a unique session ID for this processing
        session_id = str(uuid.uuid4())
        
        # Define paths
        file_path = os.path.join(self.upload_dir, f"{session_id}_{filename}")
        debug_dir = None # os.path.join(self.debug_root, f"{session_id}_{filename}")
        
        # Save the file
        with open(file_path, "wb") as f:
            f.write(file_content)
            
        print(f"Processing {filename} (Session: {session_id})")
        
        results = {
            "session_id": session_id,
            "filename": filename,
            "status": "failed",
            "error": None,
            "output": None
        }

        try:
            # 1. Preflight
            preflight = Preflight(file_path, debug_dir)
            preflight_data = preflight.run()
            
            # 2. Layout & Signal Extraction
            layout_extractor = LayoutExtraction(file_path, debug_dir)
            signals = layout_extractor.run()
            
            # 2b. Header & Footer Removal
            hf_remover = HeaderFooterRemoval(signals, debug_dir)
            signals = hf_remover.run()

            # 3. Font Clustering
            font_clusterer = FontClustering(signals, debug_dir)
            font_clusters = font_clusterer.run()

            # 4. Heading Detection
            heading_detector = HeadingDetection(signals, font_clusters, debug_dir)
            headings = heading_detector.run()

            # Extract tables structure from signals for HierarchyBuilder
            tables_data = [{"page_number": p["page_number"], "tables": p.get("tables", [])} for p in signals]

            # 5. Hierarchy Builder
            hierarchy_builder = HierarchyBuilder(headings, font_clusters, tables_data, debug_dir)
            tree = hierarchy_builder.run()
            
            # 6. Tree Flattener
            flattener = TreeFlattener(tree)
            flat_nodes = flattener.run()
            
            results["status"] = "success"
            results["output"] = {"nodes": flat_nodes}
            
            # Optional: Clean up upload? 
            # os.remove(file_path)
            
        except Exception as e:
            print(f"Error processing {filename}: {e}")
            results["error"] = str(e)
            
        return results
