import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from passporteye import read_mrz
import pytesseract
from typing import Optional
import io
from dotenv import load_dotenv
import os

# Patch cv2.findContours for PassportEye compatibility.
_original_findContours = cv2.findContours

def findContours_wrapper(*args, **kwargs):
    results = _original_findContours(*args, **kwargs)
    if isinstance(results, tuple) and len(results) == 3:
        # Return only contours and hierarchy, ignoring the first image.
        return results[1], results[2]
    return results

cv2.findContours = findContours_wrapper

# Load environment variables from the .env file
load_dotenv()

# Set the Tesseract command path from the environment variable
tesseract_cmd = os.getenv("TESSERACT_CMD")
if not tesseract_cmd:
    raise Exception("TESSERACT_CMD is not set in the .env file. Please define the path to Tesseract.")

# Configure pytesseract to use the specified Tesseract executable
pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

#start the app 
app = FastAPI(title="Passport Validation API")

# Configure Tesseract path if needed (uncomment and modify)
# pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

def check_image_quality(image: np.ndarray) -> tuple[bool, str]:
    """Check if the image meets minimum quality standards."""
    height, width = image.shape[:2]
    
    # Minimum resolution check (~600 DPI equivalent)
    if width < 800 or height < 600:
        return False, "Image resolution too low (min 1200x900 pixels required)"
    
    # Sharpness check (Laplacian variance)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
    if sharpness < 50:
        return False, f"Image is too blurry (sharpness score: {sharpness:.1f})"
    
    return True, "Image quality OK"

def validate_mrz(image: np.ndarray) -> tuple[bool, Optional[dict]]:
    """Extract and validate MRZ data using valid_score threshold."""
    # Save image temporarily for PassportEye
    temp_path = "temp_passport.jpg"
    cv2.imwrite(temp_path, image)
    
    mrz = read_mrz(temp_path)
    if mrz is None:
        return False, None
    
    # Check MRZ validity using valid_score threshold
    if not hasattr(mrz, 'valid_score') or mrz.valid_score <= 50:
        return False, None
    
    # Return data even if some individual checks failed, as long as score is good
    return True, {
        "country": mrz.country,
        "passport_number": mrz.number,
        "birth_date": mrz.date_of_birth,
        "expiry_date": mrz.expiration_date,
        "name": mrz.names,
        "surname": mrz.surname,
        "gender": mrz.sex,
        "nationality": mrz.nationality,
        # Optional: Include validation details for transparency
        "validation_details": {
            "valid_score": mrz.valid_score,
            "number_valid": mrz.valid_number,
            "dob_valid": mrz.valid_date_of_birth,
            "expiry_valid": mrz.valid_expiration_date,
            "composite_valid": mrz.valid_composite
        }
    }
def check_passport_layout(image: np.ndarray) -> tuple[bool, str]:
    """Verify basic passport layout structure."""
    height, width = image.shape[:2]
    
    # Face detection (should be on right side for most passports)
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
    
    if len(faces) == 0:
        return False, "No face detected in passport photo"
    
    x, y, w, h = faces[0]
    if x > width * 0.4:  # Face should be on right side
        return False, "Face position incorrect (should be on right side)"
    
    return True, "Basic layout OK"

@app.post("/validate-passport")
async def validate_passport(file: UploadFile = File(...)):
    try:
        # Read image file
        contents = await file.read()
        nparr = np.frombuffer(contents, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if image is None:
            raise HTTPException(status_code=400, detail="Invalid image file")
        
        # Step 1: Image quality check
        quality_ok, quality_msg = check_image_quality(image)
        if not quality_ok:
            return JSONResponse(
                status_code=400,
                content={"valid": False, "error": quality_msg}
            )
        
        # Step 2: MRZ validation
        mrz_ok, mrz_data = validate_mrz(image)
        if not mrz_ok:
            return JSONResponse(
                status_code=400,
                content={"valid": False, "error": "MRZ not found or invalid"}
            )
        
        # Step 3: Layout validation
        layout_ok, layout_msg = check_passport_layout(image)
        if not layout_ok:
            return JSONResponse(
                status_code=400,
                content={"valid": False, "error": layout_msg}
            )
        
        # If all checks pass
        return {
            "valid": True,
            "country": mrz_data["country"],
            "passport_number": mrz_data["passport_number"],
            "birth_date": mrz_data["birth_date"],
            "expiry_date": mrz_data["expiry_date"],
            "name": f"{mrz_data['surname']} {mrz_data['name']}",
            "gender": mrz_data["gender"],
            "nationality": mrz_data["nationality"],
            "checks": {
                "image_quality": quality_msg,
                "layout_validation": layout_msg
                #"tampering_check": tampering_msg
            }
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing error: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)