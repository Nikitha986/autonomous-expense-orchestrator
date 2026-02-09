import re
import io
import os
import base64
from typing import Dict, Optional
from PIL import Image, ImageEnhance, ImageFilter, UnidentifiedImageError
import pytesseract
import pdfplumber
import numpy as np
from datetime import datetime
from dotenv import load_dotenv

# PDF handling
try:
    import pypdfium2 as pdfium
    PYPDFIUM_AVAILABLE = True
except ImportError:
    PYPDFIUM_AVAILABLE = False

load_dotenv()

# Claude 3.5 Sonnet Integration
try:
    from anthropic import Anthropic
    CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
    CLAUDE_AVAILABLE = CLAUDE_API_KEY is not None
    if CLAUDE_AVAILABLE:
        claude_client = Anthropic(api_key=CLAUDE_API_KEY)
except (ImportError, Exception) as e:
    CLAUDE_AVAILABLE = False
    print(f"Claude not available: {e}")


# -------------------------------------------------
# OCR HELPERS
# -------------------------------------------------
def preprocess_image_for_ocr(image: Image.Image, mode: str = "standard") -> Image.Image:
    """
    Preprocess image for better OCR accuracy.
    mode: "standard" for printed text, "handwritten" for handwritten, "thermal" for thermal receipts
    """
    # Convert to RGB if needed
    if image.mode != "RGB":
        image = image.convert("RGB")
    
    # Resize if too small
    if image.width < 300 or image.height < 300:
        scale = max(300 / image.width, 300 / image.height)
        new_size = (int(image.width * scale), int(image.height * scale))
        image = image.resize(new_size, Image.Resampling.LANCZOS)
    
    # Enhance contrast
    enhancer = ImageEnhance.Contrast(image)
    image = enhancer.enhance(1.5)
    
    # Enhance sharpness for handwritten/thermal
    if mode in ["handwritten", "thermal"]:
        enhancer = ImageEnhance.Sharpness(image)
        image = enhancer.enhance(2.0)
        
        # Apply median filter to reduce noise
        image = image.filter(ImageFilter.MedianFilter(size=3))
    
    # Enhance brightness
    enhancer = ImageEnhance.Brightness(image)
    image = enhancer.enhance(1.1)
    
    return image


def run_ocr_image(image: Image.Image, mode: str = "standard") -> str:
    """
    Run OCR with multiple attempts for better accuracy.
    Falls back gracefully if Tesseract not available.
    """
    try:
        # Preprocess for standard OCR
        preprocessed = preprocess_image_for_ocr(image, mode)
        
        # Try standard OCR first
        config = "--psm 6"  # Assume single uniform block of text
        if mode == "handwritten":
            config = "--psm 3 -c tessedit_char_whitelist=0123456789.,₹/- "
        
        text = pytesseract.image_to_string(preprocessed, config=config)
        
        # If confidence is low, try alternative PSM
        if len(text.strip()) < 20:
            config_alt = "--psm 1"  # Auto page segmentation with OSD
            text_alt = pytesseract.image_to_string(preprocessed, config=config_alt)
            if len(text_alt.strip()) > len(text.strip()):
                text = text_alt
        
        return text.strip()
    
    except pytesseract.pytesseract.TesseractNotFoundError:
        print("⚠️ Tesseract not installed - using fallback extraction")
        return fallback_ocr(image)
    except Exception as e:
        print(f"OCR error: {e} - using fallback")
        return fallback_ocr(image)


def fallback_ocr(image: Image.Image) -> str:
    """
    Fallback extraction when Tesseract is unavailable.
    Uses image analysis and pattern matching.
    """
    try:
        # Analyze image for text-like regions
        img_array = np.array(image)
        
        # Convert to grayscale
        if len(img_array.shape) == 3:
            gray = np.mean(img_array, axis=2)
        else:
            gray = img_array
        
        # Find dark regions (likely text)
        threshold = np.percentile(gray, 30)
        text_mask = gray < threshold
        
        # Get image info as text fallback
        width, height = image.size
        fallback_text = f"""
RECEIPT IMAGE METADATA
Width: {width}px
Height: {height}px
Text Detection: Analysis mode (Tesseract unavailable)
Please ensure Tesseract OCR is installed for full extraction.

For manual extraction, receipt dimensions suggest: {width}x{height}px document
Text regions detected: {np.sum(text_mask)} pixels
"""
        return fallback_text
    except Exception as e:
        return f"Fallback extraction failed: {str(e)}"


def extract_via_claude(image_data: bytes) -> str:
    """
    Extract text from receipt image using Claude 3.5 Sonnet Vision.
    Returns: Date, Amount, Vendor information in structured format.
    """
    if not CLAUDE_AVAILABLE or not claude_client:
        return ""
    
    try:
        # Convert bytes to base64
        base64_image = base64.standard_b64encode(image_data).decode("utf-8")
        
        # Detect image format
        try:
            img = Image.open(io.BytesIO(image_data))
            format_map = {"JPEG": "image/jpeg", "PNG": "image/png", "GIF": "image/gif", "WEBP": "image/webp"}
            media_type = format_map.get(img.format, "image/jpeg")
        except:
            media_type = "image/jpeg"
        
        # Call Claude vision
        response = claude_client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": base64_image,
                            },
                        },
                        {
                            "type": "text",
                            "text": """Extract expense information from this receipt. 
Return ONLY the following format (no extra text):
DATE: [DD-MM-YYYY or NA]
AMOUNT: [₹ number or NA]
VENDOR: [Business name or NA]
TEXT: [All readable text from receipt]

Be strict about finding actual amounts and dates. If unclear, return NA."""
                        }
                    ],
                }
            ],
        )
        
        return response.content[0].text
    except Exception as e:
        print(f"Claude vision error: {e}")
        return ""


def parse_claude_response(response_text: str) -> Dict[str, str]:
    """Parse Claude's structured response format."""
    result = {
        "date": "NA",
        "amount": "NA",
        "vendor": "NA",
        "text": ""
    }
    
    for line in response_text.splitlines():
        line = line.strip()
        if line.startswith("DATE:"):
            result["date"] = line.replace("DATE:", "").strip()
        elif line.startswith("AMOUNT:"):
            result["amount"] = line.replace("AMOUNT:", "").strip()
        elif line.startswith("VENDOR:"):
            result["vendor"] = line.replace("VENDOR:", "").strip()
        elif line.startswith("TEXT:"):
            result["text"] = line.replace("TEXT:", "").strip()
        elif result["text"]:  # Continue capturing multi-line text
            result["text"] += f"\n{line}"
    
    return result


# -------------------------------------------------
# FIELD EXTRACTION
# -------------------------------------------------
def extract_amount(text: str) -> float:
    """Extract amount with multiple fallback patterns."""
    keywords = [
        "net payable", "amount to pay", "total amount", "payable",
        "grand total", "total", "amount", "₹", "rs", "price",
        "bill", "cost", "rate"
    ]

    candidates = []
    
    for line in text.lower().splitlines():
        clean = line.replace(",", "").replace("₹", "").strip()
        
        # Find all numbers in this line
        nums = re.findall(r"(\d{1,7}(?:\.\d{1,2})?)", clean)
        
        for n in nums:
            try:
                val = float(n)
                # Accept values between ₹50 and ₹10,000,000 (reject too tiny values)
                if 50 <= val <= 10_000_000:
                    # Score based on keywords
                    keyword_score = sum(5 for k in keywords if k in line)
                    # Heavily prefer larger numbers in "total" lines and table contexts
                    position_score = 20 if any(k in line for k in ["total", "amount to pay", "payable"]) else 0
                    # Prefer lines with table elements (|, -)
                    if "|" in line or line.strip().startswith("-"):
                        position_score += 5
                    score = keyword_score + position_score
                    candidates.append((score, val))
            except ValueError:
                pass

    if not candidates:
        return 0.0

    # Return highest scoring candidate
    candidates.sort(key=lambda x: (-x[0], -x[1]))  # Sort by score desc, then amount desc
    return candidates[0][1]


def extract_vendor(text: str) -> str:
    """Extract vendor name with better heuristics for institutions and receipts."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    
    # Common vendor keywords to prioritize
    vendor_keywords = [
        "amazon", "flipkart", "swiggy", "zomato", "uber", "ola", "indigo",
        "hotel", "restaurant", "coffee", "starbucks", "airbnb", "booking",
        "visa", "mastercard", "branch", "store", "shop", "supermarket",
        "airlines", "railway", "metro", "institute", "university", "college",
        "hospital", "clinic", "pharmacy", "school", "bank", "atm"
    ]
    
    # First pass: Look for organization/institution names
    # These are usually at the start and contain "Dr.", "Ltd.", "Inc.", "Institute", etc.
    for line in lines[:5]:
        line_lower = line.lower()
        # Check if line looks like an organization name
        if any(keyword in line_lower for keyword in ["institute", "university", "college", "ltd", "inc", "hospital", "bank"]):
            if len(line) > 5:
                return line.upper()
    
    # Second pass: look for known vendors in first 10 lines
    for line in lines[:10]:
        line_lower = line.lower()
        for vendor in vendor_keywords:
            if vendor in line_lower:
                return line.upper()
    
    # Third pass: return first substantial line with mostly letters (not just "Acknowledgement" or single words)
    for line in lines[:6]:
        letters = sum(c.isalpha() for c in line)
        if letters / max(len(line), 1) > 0.5 and len(line) > 10:  # Prefer longer lines
            # Skip lines that are just headers like "Acknowledgement", "Receipt", etc.
            if line.lower() not in ["acknowledgement", "receipt", "invoice", "bill", "note"]:
                return line.upper()
    
    return "UNKNOWN"


def extract_employee_name(text: str) -> str:
    """Heuristic extraction of employee name from receipt text.

    Strategies:
    - Look for labeled lines like 'Name:', 'Employee:', 'Passenger:'
    - Fallback to the largest capitalized line near the top that is not the vendor
    - Return None if not found
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    label_re = re.compile(r"(?:name|employee|passenger|paid to)[:\-\s]+(.+)", flags=re.IGNORECASE)
    for line in lines[:12]:
        m = label_re.search(line)
        if m:
            candidate = m.group(1).strip()
            if 3 <= len(candidate) <= 60:
                return candidate.title()

    # Fallback: look for a long capitalized word line (likely a person or organization)
    for line in lines[:8]:
        # ignore common headers
        if line.lower() in ["receipt", "invoice", "bill", "total", "amount"]:
            continue
        letters = sum(c.isalpha() for c in line)
        if letters / max(len(line), 1) > 0.5 and 3 <= len(line.split()) <= 4:
            # If looks like a name, return title-cased
            return line.title()

    return None


def extract_date(text: str) -> str:
    """Extract date with multiple formats and heuristics.

    Strategy:
    - Look for labeled lines containing 'date', 'invoice date', 'bill date'.
    - Try parsing with dateutil if available (dayfirst=True).
    - Fall back to several common strptime patterns.
    - Return ISO-formatted date (YYYY-MM-DD) or 'NA'.
    """
    if not text or not text.strip():
        return "NA"

    # Normalize whitespace and split into lines
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 1) Look for labeled date lines (e.g., 'Date: 12-11-2025' or 'Invoice Date 12/11/25')
    # allow shorter/longer candidates after the label and accept a wider set of characters
    label_re = re.compile(r"(invoice\s*date|bill\s*date|date of issue|date)[:\s]*([\w\d\-/.,\s]{1,60})",
                          flags=re.IGNORECASE)
    for line in lines:
        m = label_re.search(line)
        if m:
            candidate = m.group(2).strip()
            parsed = _parse_date_string(candidate)
            if parsed:
                return parsed

    # 2) Look for any date-like token in the text (prefer lines containing month names or separators)
    month_re = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\b", flags=re.IGNORECASE)

    # broader token matcher: supports 12-11-2025, 12.11.2025, 12 11 2025, 2025-11-12
    date_token_re = re.compile(r"\d{1,2}([./\-\s])\d{1,2}\1\d{2,4}")
    iso_re = re.compile(r"\d{4}[./\-]\d{1,2}[./\-]\d{1,2}")

    for line in lines:
        if month_re.search(line) or date_token_re.search(line) or iso_re.search(line):
            # try to extract a date substring using the best matching regex
            m = date_token_re.search(line) or iso_re.search(line)
            if m:
                parsed = _parse_date_string(m.group(0))
                if parsed:
                    return parsed

            # fallback: try to parse the whole line (handles '12 Nov 2025' etc.)
            parsed = _parse_date_string(line)
            if parsed:
                return parsed

    # 3) As a last resort, search entire text for any date-like pattern
    # final attempt: search the whole text for broader date tokens
    m = date_token_re.search(text) or iso_re.search(text)
    if m:
        parsed = _parse_date_string(m.group(0))
        if parsed:
            return parsed

    # As a last-ditch, look for a 4-digit year and nearby numbers to assemble a date
    m = re.search(r"(\d{1,2})[^\d]{1,3}(\d{1,2})[^\d]{1,3}(20\d{2})", text)
    if m:
        candidate = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        parsed = _parse_date_string(candidate)
        if parsed:
            return parsed

    # No date found
    return "NA"


def _parse_date_string(s: str) -> Optional[str]:
    """Try to parse a date string and return ISO date YYYY-MM-DD or None."""
    if not s or not s.strip():
        return None

    s = s.strip()
    # Remove common suffixes/words
    s = re.sub(r"(st|nd|rd|th)\b", "", s, flags=re.IGNORECASE)
    s = s.replace(".", "-")
    s = s.replace(",", "")
    s = s.replace("\u2013", "-")  # en-dash
    s = s.strip()

    # Try dateutil if available
    try:
        from dateutil import parser as dateutil_parser

        try:
            dt = dateutil_parser.parse(s, dayfirst=True, fuzzy=True)
            return dt.date().isoformat()
        except Exception:
            pass
    except Exception:
        # dateutil not available — continue to manual parsing
        pass

    # Manual patterns (dayfirst preferred)
    patterns = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d-%m-%y",
        "%d/%m/%y",
        "%Y-%m-%d",
        "%d %b %Y",
        "%d %B %Y",
        "%b %d %Y",
        "%B %d %Y",
    ]

    for fmt in patterns:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.date().isoformat()
        except Exception:
            continue

    # Try to extract numbers and reorder if possible (e.g., 12 11 2025)
    nums = re.findall(r"\d{1,4}", s)
    if len(nums) >= 3:
        # heuristic: take last 3 numbers as D M Y or Y M D
        for order in [(0,1,2), (2,1,0)]:
            try:
                d = int(nums[order[0]])
                m = int(nums[order[1]])
                y = int(nums[order[2]])
                if y < 100:  # two-digit year
                    y += 2000 if y < 70 else 1900
                if 1 <= m <= 12 and 1 <= d <= 31 and 1900 <= y <= 2100:
                    return datetime(y, m, d).date().isoformat()
            except Exception:
                continue

    return None


def calculate_confidence(amount: float, vendor: str, text: str) -> float:
    score = 0.4
    if amount > 0:
        score += 0.3
    if vendor != "UNKNOWN":
        score += 0.2
    if len(text) > 100:
        score += 0.1
    return round(min(score, 1.0), 2)


def detect_image_mode(image: Image.Image) -> str:
    """
    Detect if image is handwritten, printed, or thermal.
    """
    # Convert to numpy array for analysis
    img_array = np.array(image.convert("L"))  # Grayscale
    
    # Calculate variance of gradients (handwritten has higher variance)
    grad_x = np.abs(np.diff(img_array, axis=1)).mean()
    grad_y = np.abs(np.diff(img_array, axis=0)).mean()
    gradient_variance = grad_x + grad_y
    
    # Calculate color uniformity (thermal receipts have low color range)
    if image.mode == "RGB":
        img_rgb = np.array(image)
        color_range = (img_rgb.max(axis=2) - img_rgb.min(axis=2)).mean()
        if color_range < 30:  # Very low color variance = thermal
            return "thermal"
    
    # High gradient variance = handwritten
    if gradient_variance > 15:
        return "handwritten"
    
    return "standard"


# -------------------------------------------------
# MAIN VISION AGENT (IMAGE + PDF SUPPORT + CLAUDE)
# -------------------------------------------------
def vision_agent(file_bytes: bytes) -> Dict:
    """
    Accepts IMAGE or PDF bytes.
    Uses Claude 3.5 Sonnet vision first, falls back to Tesseract.
    Returns structured expense data {vendor, amount, date, confidence, text}
    """
    
    text_all = ""
    images = []
    vendor = "UNKNOWN"
    amount = 0.0
    date = "NA"
    claude_used = False
    employee_name = None

    # 1️⃣ Try as image
    is_image = False
    try:
        image = Image.open(io.BytesIO(file_bytes))
        images = [image]
        is_image = True
    except (UnidentifiedImageError, Exception):
        pass

    # 2️⃣ Try as PDF - Convert to Images using pypdfium2
    is_pdf = False
    if not is_image:
        # First try pypdfium2 (no poppler needed)
        if PYPDFIUM_AVAILABLE:
            try:
                pdf = pdfium.PdfDocument.new_from_data(file_bytes)
                num_pages = len(pdf)
                print(f"✅ PDF opened: {num_pages} page(s)")
                
                if num_pages > 0:
                    is_pdf = True
                    # Render first 3 pages to images
                    for page_idx in range(min(3, num_pages)):
                        page = pdf[page_idx]
                        bitmap = page.render(scale=2)  # 2x scale for better quality
                        pil_image = bitmap.to_pil()
                        images.append(pil_image)
                    print(f"✅ Rendered {len(images)} page(s) to images")
            except Exception as e:
                print(f"⚠️ pypdfium2 rendering failed: {e}")
        
        # Fallback: Try text extraction from pdfplumber
        if not is_pdf or not images:
            try:
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    if len(pdf.pages) > 0:
                        is_pdf = True
                        # Extract text directly from PDF
                        for page_num, page in enumerate(pdf.pages[:3]):
                            page_text = page.extract_text() or ""
                            text_all += f"\n[Page {page_num + 1}]\n{page_text}"
                        if text_all.strip():
                            print(f"✅ PDF text extracted: {len(text_all)} chars")
            except Exception as e:
                print(f"❌ pdfplumber extraction failed: {e}")

    # If not image or PDF, return error
    if not is_image and not is_pdf:
        return {
            "vendor": None,
            "amount": None,
            "date": None,
            "confidence": 0.0,
            "text": "Failed to identify file format",
        }

    # 3️⃣ PRIMARY: Try Claude 3.5 Sonnet extraction
    if CLAUDE_AVAILABLE and is_image and images:
        try:
            claude_response = extract_via_claude(file_bytes)
            if claude_response and len(claude_response) > 20:
                # Parse Claude's structured response
                parsed = parse_claude_response(claude_response)
                text_all = parsed["text"]
                
                # Extract structured fields from Claude if available
                if parsed["date"] != "NA":
                    date = parsed["date"]
                if parsed["amount"] != "NA":
                    # Try to convert Claude's amount format
                    amount_str = parsed["amount"].replace("₹", "").strip()
                    try:
                        amount = float(amount_str)
                    except:
                        amount = extract_amount(text_all) if text_all else 0.0
                if parsed["vendor"] != "NA":
                    vendor = parsed["vendor"]
                
                claude_used = True
        except Exception as e:
            print(f"Claude extraction failed: {e}")
    
    # 3B️⃣ For PDFs converted to images, also try Claude
    elif CLAUDE_AVAILABLE and is_pdf and images:
        try:
            # Use first page for Claude extraction
            first_page_bytes = io.BytesIO()
            images[0].save(first_page_bytes, format="PNG")
            first_page_bytes = first_page_bytes.getvalue()
            
            claude_response = extract_via_claude(first_page_bytes)
            if claude_response and len(claude_response) > 20:
                parsed = parse_claude_response(claude_response)
                text_all = parsed["text"]
                
                if parsed["date"] != "NA":
                    date = parsed["date"]
                if parsed["amount"] != "NA":
                    amount_str = parsed["amount"].replace("₹", "").strip()
                    try:
                        amount = float(amount_str)
                    except:
                        amount = extract_amount(text_all) if text_all else 0.0
                if parsed["vendor"] != "NA":
                    vendor = parsed["vendor"]
                
                claude_used = True
        except Exception as e:
            print(f"Claude extraction for PDF failed: {e}")

    # 4️⃣ FALLBACK: Tesseract OCR on PDF images
    if is_pdf and images:
        # For PDFs, always try OCR to get better text extraction
        for idx, image in enumerate(images):
            try:
                ocr_text = pytesseract.image_to_string(image)
                if ocr_text and len(ocr_text.strip()) > len(text_all.strip()):
                    # If OCR gives us more text, use it
                    text_all = ocr_text
                    print(f"✅ OCR extracted {len(text_all)} chars from page {idx+1}")
            except Exception as e:
                print(f"⚠️ OCR failed on page {idx+1}: {e}")
    
    # 4B️⃣ FALLBACK: Tesseract OCR if Claude didn't work
    elif not text_all and images:
        for image in images:
            mode = detect_image_mode(image)
            ocr_text = run_ocr_image(image, mode=mode)
            text_all += f"\n{ocr_text}"
            if text_all.strip():
                break  # Stop after first successful OCR

    # Clean up text
    text_all = text_all.strip()
    
    # If still no text, return error
    if not text_all:
        print("⚠️ No readable text found - trying final OCR fallback")
        # Last resort: try OCR even if we don't have extracted text
        if images:
            try:
                for idx, img in enumerate(images):
                    ocr_result = pytesseract.image_to_string(img)
                    if ocr_result and len(ocr_result.strip()) > 20:
                        text_all = ocr_result
                        print(f"✅ Final OCR successful: {len(text_all)} chars")
                        break
            except Exception as e:
                print(f"❌ Final OCR failed: {e}")
        
        if not text_all:
            return {
                "vendor": None,
                "amount": None,
                "date": None,
                "confidence": 0.0,
                "text": "No readable text found in document",
                "type": receipt_type,
            }

    # 6️⃣ Extract structured fields if Claude didn't provide them
    if not claude_used:
        if text_all:  # Only extract if we have text
            vendor = extract_vendor(text_all)
            amount = extract_amount(text_all)
            date = extract_date(text_all)
            # Try to extract employee name heuristically
            try:
                emp = extract_employee_name(text_all)
                if emp:
                    employee_name = emp
            except Exception:
                pass
            
            # If amount is too low (likely extraction error), try harder
            if amount < 50:
                # Look for common amount patterns more aggressively
                amount_patterns = [
                    r"(?:total|amount|payable|₹)\s*:?\s*₹?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
                    r"₹\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
                    r"Rs\.?\s*(\d+(?:,\d{3})*(?:\.\d{2})?)",
                ]
                for pattern in amount_patterns:
                    matches = re.findall(pattern, text_all, re.IGNORECASE)
                    if matches:
                        try:
                            # Get the largest match
                            candidate_amounts = [float(m.replace(",", "")) for m in matches]
                            largest = max([a for a in candidate_amounts if a >= 50], default=0)
                            if largest > 0:
                                amount = largest
                                print(f"✅ Amount found via pattern: ₹{amount}")
                                break
                        except:
                            pass
        else:
            print(f"❌ No text extracted for processing")
            # Don't use fallback - keep defaults as 0/NA
    
    # Calculate confidence based on what we actually extracted
    if claude_used:
        base_confidence = 0.88
    else:
        base_confidence = 0.4
    
    if amount > 0:
        base_confidence += 0.08
    if vendor != "UNKNOWN":
        base_confidence += 0.03
    if date != "NA":
        base_confidence += 0.01
    
    confidence = round(min(base_confidence, 1.0), 2)
    
    if vendor == "UNKNOWN" or amount == 0.0:
        print(f"⚠️ Extraction incomplete - Vendor: {vendor}, Amount: {amount}, Date: {date}, Text length: {len(text_all)}")

    # Determine receipt type based on image if available
    receipt_type = "unknown"
    if images:
        receipt_type = detect_image_mode(images[0])
    elif is_pdf:
        receipt_type = "pdf"

    return {
        "vendor": vendor,
        "amount": amount,
        "date": date,
        "confidence": confidence,
        "text": text_all,
        "type": receipt_type,
        "employee_name": employee_name,
    }


def extract_receipt_data(path_or_bytes) -> Dict:
    """
    Compatibility wrapper used by API endpoints.
    Accepts either a file path (str / os.PathLike) or raw bytes and returns the same
    structured dict as `vision_agent`.
    """
    try:
        # If a path string was passed, read the file bytes
        if isinstance(path_or_bytes, (str,)):
            with open(path_or_bytes, "rb") as f:
                data = f.read()
        else:
            data = path_or_bytes

        return vision_agent(data)
    except Exception as e:
        return {"vendor": None, "amount": None, "date": None, "confidence": 0.0, "text": f"error: {e}", "type": "error"}
