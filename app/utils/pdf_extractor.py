#!/usr/bin/env python3
"""
Extract images and text from PDF files (with OCR support)
Usage: python extract_pdf_images.py <pdf_path> <output_dir>
"""

import sys
import os
import base64
import json
from pathlib import Path

try:
    import fitz  # PyMuPDF
except ImportError:
    print("ERROR: PyMuPDF not installed. Run: pip install PyMuPDF", file=sys.stderr)
    sys.exit(1)

try:
    from PIL import Image
    import pytesseract
    # Set Tesseract path for Windows
    if sys.platform == "win32":
        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    OCR_AVAILABLE = True
    print(f"OCR is available. Tesseract path: {pytesseract.pytesseract.tesseract_cmd}", file=sys.stderr)
except ImportError as e:
    OCR_AVAILABLE = False
    print(f"WARNING: OCR not available. Error: {e}", file=sys.stderr)
    print("WARNING: Install with: pip install pytesseract pillow", file=sys.stderr)
    print("WARNING: Also install Tesseract-OCR from: https://github.com/UB-Mannheim/tesseract/wiki", file=sys.stderr)


def extract_images_from_pdf(pdf_path, output_dir):
    """Extract all images and text from a PDF file and save them."""
    try:
        # Open the PDF
        pdf_document = fitz.open(pdf_path)
        
        images = []
        texts = []
        image_index = 0
        
        # Iterate through all pages
        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            
            # Extract text from page (direct text extraction)
            page_text = page.get_text("text").strip()
            print(f"Page {page_num + 1}: extracted {len(page_text)} characters (direct)", file=sys.stderr)
            
            # If no direct text found and OCR is available, try OCR
            if not page_text and OCR_AVAILABLE:
                print(f"Page {page_num + 1}: Attempting OCR...", file=sys.stderr)
                try:
                    # Render page to image for OCR
                    mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR quality
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes("png")
                    
                    # Convert to PIL Image and run OCR
                    from io import BytesIO
                    img = Image.open(BytesIO(img_data))
                    page_text = pytesseract.image_to_string(img).strip()
                    print(f"Page {page_num + 1}: extracted {len(page_text)} characters (OCR)", file=sys.stderr)
                except Exception as e:
                    print(f"Page {page_num + 1}: OCR failed - {str(e)}", file=sys.stderr)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
            elif not page_text:
                print(f"Page {page_num + 1}: No text found and OCR not available", file=sys.stderr)
            
            if page_text:  # Only add if there's actual text
                texts.append({
                    "pageNumber": page_num + 1,
                    "text": page_text
                })
                print(f"Page {page_num + 1}: Added {len(page_text)} chars to texts array", file=sys.stderr)
            
            # Get all images on the page
            image_list = page.get_images(full=True)
            
            for img_index, img in enumerate(image_list):
                xref = img[0]  # XREF number
                
                try:
                    # Extract image
                    base_image = pdf_document.extract_image(xref)
                    image_bytes = base_image["image"]
                    image_ext = base_image["ext"]  # png, jpg, etc.
                    
                    # Save image to output directory
                    image_filename = f"image-{image_index}.{image_ext}"
                    image_path = os.path.join(output_dir, image_filename)
                    
                    with open(image_path, "wb") as img_file:
                        img_file.write(image_bytes)
                    
                    # Add to results (page_num + 1 because pages are 1-indexed for users)
                    images.append({
                        "index": image_index,
                        "filename": image_filename,
                        "path": image_path,
                        "mimeType": f"image/{image_ext}",
                        "size": len(image_bytes),
                        "pageNumber": page_num + 1
                    })
                    
                    image_index += 1
                    
                except Exception as e:
                    print(f"Error extracting image {xref} from page {page_num}: {e}", file=sys.stderr)
                    continue
        
        pdf_document.close()
        
        print(f"Total extracted: {len(images)} images, {len(texts)} text pages", file=sys.stderr)
        
        # Return results as JSON
        result = {
            "success": True,
            "totalImages": len(images),
            "totalPages": len(texts),
            "images": images,
            "texts": texts
        }
        
        print(json.dumps(result))
        return 0
        
    except Exception as e:
        error_result = {
            "success": False,
            "error": str(e)
        }
        print(json.dumps(error_result))
        return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python extract_pdf_images.py <pdf_path> <output_dir>", file=sys.stderr)
        sys.exit(1)
    
    pdf_path = sys.argv[1]
    output_dir = sys.argv[2]
    
    # Create output directory if it doesn't exist
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    sys.exit(extract_images_from_pdf(pdf_path, output_dir))
