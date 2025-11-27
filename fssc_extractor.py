import fitz  # PyMuPDF
import re
import json
import sys
import traceback
from pathlib import Path
from typing import List, Dict, Tuple

class FSSCExtractorV2:
    """Extract structured content from FSSC 22000 audit reports"""
    
    def __init__(self, pdf_path: str):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        # Define expected structure
        self.structure = self._define_structure()
    
    def _define_structure(self) -> List[Dict]:
        """Define the complete expected structure"""
        return [
            # ISO 22000 Chapters
            {"number": "1", "title": "Contexte de l'organisation", "type": "iso",
             "sections": ["4.1", "4.2", "4.3", "4.4"]},
            {"number": "2", "title": "Management, Leadership et planification", "type": "iso",
             "sections": ["5.1", "5.2", "5.3", "6.1", "6.2", "6.3"]},
            {"number": "3", "title": "Ressources, support", "type": "iso",
             "sections": ["7.1", "7.2", "7.3", "7.4", "7.5"]},
            {"number": "4", "title": "Opérations,réalisation", "type": "iso",
             "sections": ["8.1 et 8.2", "8.3", "8.4", "8.5", "8.5.1.2", "8.5.1.3", "8.5.1.4", 
                          "8.5.1.5", "8.5.2.1", "8.5.2.2", "8.5.2.3", "8.5.3", "8.5.4", 
                          "8.6", "8.7", "8.8", "8.9.2", "8.9.3", "8.9.4", "8.9.5"]},
            {"number": "5", "title": "Evaluations de la performance,améliorations", "type": "iso",
             "sections": ["9.1", "9.2", "9.3", "10.1", "10.2", "10.3"]},
            
            # FSSC 2.5.x Chapters (2.5.18 is optional)
            {"number": "2.5.1", "title": "Gestion des services et des produits achétés", "type": "fssc",
             "sections": ["2.5.1"]},
            {"number": "2.5.2", "title": "Etiquetage des produits et matériaux imprimés", "type": "fssc",
             "sections": ["2.5.2"]},
            {"number": "2.5.3", "title": "Food defense", "type": "fssc",
             "sections": ["2.5.3"]},
            {"number": "2.5.4", "title": "Atténuation de la fraude alimentaire", "type": "fssc",
             "sections": ["2.5.4"]},
            {"number": "2.5.5", "title": "Utilisation du logo", "type": "fssc",
             "sections": ["2.5.5"]},
            {"number": "2.5.6", "title": "Gestion des allergènes", "type": "fssc",
             "sections": ["2.5.6"]},
            {"number": "2.5.7", "title": "Surveillance de l'environnement", "type": "fssc",
             "sections": ["2.5.7"]},
            {"number": "2.5.8", "title": "Culture qualité /Culture de la sécurité alimentaire", "type": "fssc",
             "sections": ["2.5.8"]},
            {"number": "2.5.9", "title": "Contrôle qualité", "type": "fssc",
             "sections": ["2.5.9"]},
            {"number": "2.5.10", "title": "Transport, stockage et entreposage", "type": "fssc",
             "sections": ["2.5.10"]},
            {"number": "2.5.11", "title": "Maîtrise des dangers et mesures pour prévenir les contaminations croisées", "type": "fssc",
             "sections": ["2.5.11"]},
            {"number": "2.5.12", "title": "Vérification des PRP", "type": "fssc",
             "sections": ["2.5.12"]},
            {"number": "2.5.13", "title": "Développement de produits", "type": "fssc",
             "sections": ["2.5.13"]},
            {"number": "2.5.14", "title": "Etat de santé", "type": "fssc",
             "sections": ["2.5.14"]},
            {"number": "2.5.15", "title": "Gestion d'équipments", "type": "fssc",
             "sections": ["2.5.15"]},
            {"number": "2.5.16", "title": "Pertes et gaspillages alimentaires", "type": "fssc",
             "sections": ["2.5.16"]},
            {"number": "2.5.17", "title": "Exigences en matière de communication", "type": "fssc",
             "sections": ["2.5.17"]},
            {"number": "2.5.18", "title": "Exigences pour les organisations ayant une certification multisite", "type": "fssc",
             "sections": ["2.5.18"], "optional": True},
            
            # ISO TS 22002-1 Food Chapters
            {"number": "4", "title": "Food: Construction et disposition des bâtiments", "type": "food",
             "sections": ["4.1", "4.2", "4.3"]},
            {"number": "5", "title": "Food: Disposition des locaux et de l'espace de travail", "type": "food",
             "sections": ["5.1", "5.2", "5.3", "5.4", "5.5", "5.6", "5.7"]},
            {"number": "6", "title": "Food: Services généraux - air, eau, énergie", "type": "food",
             "sections": ["6.1", "6.2", "6.3", "6.4", "6.5", "6.6"]},
            {"number": "7", "title": "Food: Élimination des déchets", "type": "food",
             "sections": ["7.1", "7.2", "7.3", "7.4"]},
            {"number": "8", "title": "Food: Aptitude, nettoyage et maintenance des équipements", "type": "food",
             "sections": ["8.1", "8.2", "8.3", "8.4", "8.5", "8.6"]},
            {"number": "9", "title": "Food: Gestion des produits achetés", "type": "food",
             "sections": ["9.1", "9.2", "9.3"]},
            {"number": "10", "title": "Food: Mesures de prévention des transferts de contamination", "type": "food",
             "sections": ["10.1", "10.2", "10.3", "10.4"]},
            {"number": "11", "title": "Food: Nettoyage et désinfection", "type": "food",
             "sections": ["11.1", "11.2", "11.3", "11.4", "11.5"]},
            {"number": "12", "title": "Food: Maîtrise des nuisibles", "type": "food",
             "sections": ["12.1", "12.2", "12.3", "12.4", "12.5", "12.6"]},
            {"number": "13", "title": "Food: Hygiène des membres du personnel et installations destinées aux employés", "type": "food",
             "sections": ["13.1", "13.2", "13.3", "13.4", "13.5", "13.6", "13.7", "13.8"]},
            {"number": "14", "title": "Food: Produits retraités/recyclés", "type": "food",
             "sections": ["14.1", "14.2", "14.3"]},
            {"number": "15", "title": "Food: Procédures de rappel des produits", "type": "food",
             "sections": ["15.1", "15.2"]},
            {"number": "16", "title": "Food: Entreposage, stockage et transport", "type": "food",
             "sections": ["16.1", "16.2", "16.3"]},
            {"number": "17", "title": "Food: Informations sur le produit et sensibilisation des consommateurs", "type": "food",
             "sections": ["17"]},
            {"number": "18", "title": "Food: Prévention de l'introduction intentionnelle de dangers dans les denrées", "type": "food",
             "sections": ["18.1 / 18.2"]},
        ]
    
    def extract(self) -> dict:
        """Main extraction pipeline"""
        print(f"Starting extraction from: {self.pdf_path.name}")
        
        # Extract text from PDF
        print("  [1/3] Extracting text from PDF...")
        full_text = self._extract_text_from_pdf()
        
        # Save full text
        txt_output_path = self.pdf_path.with_suffix('.txt')
        print(f"  [2/3] Saving extracted text to: {txt_output_path.name}")
        with open(txt_output_path, 'w', encoding='utf-8') as f:
            f.write(full_text)
        
        # Extract structured content
        print("  [3/3] Extracting structured content...")
        result = self._extract_all_chapters(full_text)
        
        print(f"✓ Extraction complete!")
        print(f"  - Chapters extracted: {len(result['chapters'])}")
        total_sections = sum(len(ch['sections']) for ch in result['chapters'])
        print(f"  - Sections extracted: {total_sections}")
        
        return result
    
    def _extract_text_from_pdf(self) -> str:
        """Extract all text from PDF"""
        doc = fitz.open(str(self.pdf_path))
        full_text = ""
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            page_text = page.get_text()
            page_text = self._clean_page_text(page_text)
            full_text += f"\n\n===PAGE {page_num + 1}===\n\n{page_text}"
        
        doc.close()
        return full_text
    
    def _clean_page_text(self, page_text: str) -> str:
        """Remove headers, footers, and noise"""
        lines = page_text.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line_stripped = line.strip()
            
            if not line_stripped:
                continue
            
            # Skip footers
            if re.match(r'^Rapport d\'audit \(provisoire\)$', line_stripped):
                continue
            if re.match(r'^©\s*\d{4}\s+ProCert\s+www\.procert\.ch$', line_stripped):
                continue
            if re.match(r'^\d{4}-\d{2}-\d{2}$', line_stripped):
                continue
            if re.match(r'^\d+\s*/\s*\d+$', line_stripped):
                continue
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines)
    
    def _extract_all_chapters(self, text: str) -> dict:
        """Extract all chapters and their sections"""
        # Find document boundaries
        start_marker = "1 Contexte de l'organisation"
        end_marker = "6. Constats d'audit"
        
        start_pos = text.find(start_marker)
        if start_pos == -1:
            # Fallback if exact marker not found
            start_pos = 0
        
        end_pos = text.find(end_marker)
        if end_pos == -1:
            end_pos = len(text)
        
        section_text = text[start_pos:end_pos]
        
        # Find all chapter positions
        chapter_positions = self._find_all_chapters(section_text)
        
        result = {
            "source": str(self.pdf_path.name),
            "chapters": []
        }
        
        # Extract each chapter
        for expected_ch in self.structure:
            chapter_data = self._extract_chapter(
                section_text,
                expected_ch,
                chapter_positions
            )
            if chapter_data:
                result["chapters"].append(chapter_data)
        
        return result
    
    def _find_all_chapters(self, text: str) -> List[Dict]:
        """Find all chapter headers in the document"""
        positions = []
        
        # Pattern 1: ISO chapters (single digit 1-5 + title without "Food:")
        # Must start with digits 1-5 (not 0, not 6+) to avoid false matches with tables/lists
        pattern_iso = r'^([1-5])\s+([A-ZÉÈÊËÀÂÄÏÎÔÙÛÜŸÇ][^\n]+?)(?=\s*$)'
        for match in re.finditer(pattern_iso, text, re.MULTILINE):
            title = match.group(2).strip()
            if not title.startswith("Food:"):
                positions.append({
                    "number": match.group(1),
                    "title": title,
                    "position": match.start(),
                    "type": "iso"
                })
        
        # Pattern 2: FSSC chapters (2.5.x only - not 8.5.x or other section numbers!)
        pattern_fssc = r'^(2\.5\.\d+)\s+([^\n]+?)(?=\s*$)'
        for match in re.finditer(pattern_fssc, text, re.MULTILINE):
            positions.append({
                "number": match.group(1),
                "title": match.group(2).strip(),
                "position": match.start(),
                "type": "fssc"
            })
        
        # Pattern 3: Food chapters (digit + "Food:")
        pattern_food = r'^(\d{1,2})\s+(Food:[^\n]+?)(?=\s*$)'
        for match in re.finditer(pattern_food, text, re.MULTILINE):
            positions.append({
                "number": match.group(1),
                "title": match.group(2).strip(),
                "position": match.start(),
                "type": "food"
            })
        
        # Sort by position
        positions.sort(key=lambda x: x["position"])
        return positions
    
    def _extract_chapter(self, text: str, expected_ch: Dict, all_positions: List[Dict]) -> Dict:
        """Extract a single chapter and its sections"""
        # Find this chapter in the positions
        chapter_match = None
        chapter_idx = None
        
        for idx, pos in enumerate(all_positions):
            # Match by number AND type
            if pos["number"] == expected_ch["number"] and pos["type"] == expected_ch["type"]:
                chapter_match = pos
                chapter_idx = idx
                break
        
        if not chapter_match:
            print(f"    ⚠ Warning: Chapter {expected_ch['number']} ({expected_ch['type']}) '{expected_ch['title']}' not found")
            return None
        
        # Determine chapter boundaries
        chapter_start = chapter_match["position"]
        chapter_end = len(text)
        
        if chapter_idx is not None and chapter_idx + 1 < len(all_positions):
            chapter_end = all_positions[chapter_idx + 1]["position"]
        
        chapter_text = text[chapter_start:chapter_end]
        
        # Extract sections
        sections = self._extract_sections(
            chapter_text,
            expected_ch,
            chapter_start
        )
        
        return {
            "number": expected_ch["number"],
            "title": expected_ch["title"],
            "sections": sections
        }
    
    def _extract_sections(self, chapter_text: str, expected_ch: Dict, chapter_start: int) -> List[Dict]:
        """Extract sections from chapter text"""
        sections = []
        
        # Build regex pattern for each expected section individually
        section_positions = []
        
        for expected_section in expected_ch["sections"]:
            # Escape the section number for regex
            escaped_section = re.escape(expected_section)
            
            # Pattern: optional leading space + section number + optional text (may span multiple lines)
            # Match section number at line start, then capture everything until next section or chapter
            pattern = r'^\s*(' + escaped_section + r')(?:\s+(.+?))?(?=\n|$)'
            
            for match in re.finditer(pattern, chapter_text, re.MULTILINE):
                section_positions.append({
                    "section": expected_section,
                    "position": match.start(),
                    "content_start": match.end()
                })
        
        # Sort by position
        section_positions.sort(key=lambda x: x["position"])
        
        # If no sections found and this is a 2.5.x chapter, use entire chapter as section
        if len(section_positions) == 0 and expected_ch["number"] in expected_ch["sections"]:
            content = chapter_text.strip()
            first_newline = content.find('\n')
            if first_newline != -1:
                content = content[first_newline:].strip()
            
            sections.append({
                "section": expected_ch["number"],
                "content": content
            })
            return sections
        
        # Extract content for each section
        for i, section in enumerate(section_positions):
            start = section["position"]
            end = section_positions[i+1]["position"] if i + 1 < len(section_positions) else len(chapter_text)
            
            # Extract content, skipping the section header itself if possible
            # We use content_start from regex match to skip the number
            # But we need to be careful about the end
            
            raw_content = chapter_text[start:end]
            # Simple cleanup: remove the first line if it's just the section number
            lines = raw_content.split('\n')
            if lines and section["section"] in lines[0]:
                content = '\n'.join(lines[1:]).strip()
            else:
                content = raw_content.strip()

            sections.append({
                "section": section["section"],
                "content": content
            })
        
        return sections
    
    def _titles_match(self, expected: str, found: str) -> bool:
        """Check if two titles match (fuzzy)"""
        # Normalize
        exp_norm = self._normalize_text(expected).replace(" ", "").replace(",", "")
        found_norm = self._normalize_text(found).replace(" ", "").replace(",", "")
        
        # Calculate overlap
        min_len = min(len(exp_norm), len(found_norm))
        if min_len == 0:
            return False
        
        overlap = sum(1 for a, b in zip(exp_norm[:min_len], found_norm[:min_len]) if a == b)
        overlap_ratio = overlap / min_len
        
        # Check keywords
        exp_keywords = self._extract_keywords(expected)
        found_keywords = self._extract_keywords(found)
        keyword_matches = sum(1 for kw in exp_keywords if kw in found_keywords)
        
        # Accept if good overlap or keyword matches
        return overlap_ratio >= 0.6 or keyword_matches >= 2
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        return ' '.join(text.lower().split())
    
    def _extract_keywords(self, text: str) -> set:
        """Extract meaningful keywords"""
        normalized = self._normalize_text(text)
        stop_words = {'de', 'la', 'le', 'les', 'des', 'et', 'du', 'un', 'une', 'à', 'l', 'pour', 'dans'}
        words = [w for w in normalized.split() if len(w) > 2 and w not in stop_words]
        return set(words)
    
    def save(self, result: dict, output_path: str = None):
        """Save extraction results to JSON"""
        if output_path is None:
            output_path = str(self.pdf_path.with_suffix('.json'))
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Saved to: {output_path}")
        return output_path
