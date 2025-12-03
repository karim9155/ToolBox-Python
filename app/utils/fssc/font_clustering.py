import json
import os
from collections import defaultdict

class FontClustering:
    def __init__(self, signals, debug_dir):
        self.signals = signals
        self.debug_dir = debug_dir

    def run(self):
        """
        Groups text spans by font properties to identify hierarchy levels.
        """
        print("Running Font Clustering...")
        
        clusters = defaultdict(lambda: {
            "count": 0,
            "text_samples": [],
            "total_len": 0
        })

        for page in self.signals:
            for block in page["blocks"]:
                for line in block["lines"]:
                    for span in line["spans"]:
                        # Create a unique key for the font style
                        # Round size to 1 decimal to handle PDF floating point variances
                        size = round(span["size"], 1)
                        font_key = (span["font"], size, span["flags"], span["color"])
                        
                        cluster = clusters[font_key]
                        cluster["count"] += 1
                        cluster["total_len"] += len(span["text"])
                        
                        # Keep first few samples
                        if len(cluster["text_samples"]) < 5:
                            cluster["text_samples"].append(span["text"])

        # Convert to list and sort
        sorted_clusters = []
        for key, data in clusters.items():
            font_name, size, flags, color = key
            
            # Determine if bold/italic based on flags
            # PyMuPDF flags: 1=superscript, 2=italic, 4=serifed, 8=monospaced, 16=bold
            is_bold = bool(flags & 16)
            is_italic = bool(flags & 2)
            
            sorted_clusters.append({
                "font": font_name,
                "size": size,
                "color": color,
                "is_bold": is_bold,
                "is_italic": is_italic,
                "flags": flags,
                "count": data["count"],
                "avg_len": data["total_len"] / data["count"] if data["count"] > 0 else 0,
                "examples": data["text_samples"]
            })

        # Sort by size (descending) then by boldness
        sorted_clusters.sort(key=lambda x: (x["size"], x["is_bold"]), reverse=True)
        
        # Assign IDs
        for idx, cluster in enumerate(sorted_clusters):
            cluster["id"] = idx + 1

        self._write_debug(sorted_clusters)
        return sorted_clusters

    def _write_debug(self, data):
        if not self.debug_dir:
            return
        os.makedirs(self.debug_dir, exist_ok=True)
        output_path = os.path.join(self.debug_dir, "font_clusters.json")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Debug output saved to: {output_path}")
