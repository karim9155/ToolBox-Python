import os
import json

class Preflight:
    def __init__(self, file_path, debug_dir):
        self.file_path = file_path
        self.debug_dir = debug_dir
        self.filename = os.path.basename(file_path)

    def run(self):
        """
        Executes the preflight checks.
        1. Check file existence.
        2. Detect file type (extension).
        3. (Placeholder) Detect report type.
        4. Write debug output.
        """
        print(f"Running Preflight for: {self.filename}")
        
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Input file not found: {self.file_path}")

        file_ext = os.path.splitext(self.filename)[1].lower()
        
        # Placeholder for report type detection logic
        report_type = "unknown" 
        
        result = {
            "filename": self.filename,
            "file_path": self.file_path,
            "extension": file_ext,
            "detected_report_type": report_type,
            "file_size": os.path.getsize(self.file_path)
        }

        self._write_debug(result)
        return result

    def _write_debug(self, data):
        if not self.debug_dir:
            return
        os.makedirs(self.debug_dir, exist_ok=True)
        output_path = os.path.join(self.debug_dir, "preflight.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"Debug output saved to: {output_path}")
