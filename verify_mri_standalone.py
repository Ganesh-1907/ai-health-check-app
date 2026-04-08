import sys
import os
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw

# Add app directory to sys.path
sys.path.append(os.path.join(os.getcwd(), "backend"))

from app.services.mri_engine import MRIEngine

def _load_sample_bytes():
    cli_path = Path(sys.argv[1]).expanduser() if len(sys.argv) > 1 else None
    env_path = Path(os.environ["MRI_SAMPLE_PATH"]).expanduser() if os.environ.get("MRI_SAMPLE_PATH") else None
    fallback_path = Path("/home/ganesh/Desktop/Garduda_seva/MRI-Disease-detection/backend/textFiles/brain/Te-glTr_0002.jpg")

    for candidate in [cli_path, env_path, fallback_path]:
        if candidate and candidate.exists():
            return candidate.name, BytesIO(candidate.read_bytes())

    image = Image.new("L", (224, 224), color=25)
    draw = ImageDraw.Draw(image)
    draw.ellipse((52, 36, 172, 188), fill=150)
    draw.ellipse((96, 92, 148, 144), fill=215)
    draw.rectangle((30, 100, 70, 122), fill=95)
    buffer = BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    buffer.seek(0)
    return "synthetic_mri.png", buffer

def test_mri_engine():
    engine = MRIEngine()
    sample_name, img_bytes = _load_sample_bytes()

    result = engine.predict(img_bytes)
    print("Sample:", sample_name)
    print("Result Keys:", result.keys())
    print("Prediction Label:", result.get("prediction_label"))
    print("Confidence:", result.get("confidence"))
    print("Inference Mode:", result.get("inference_mode"))
    if result.get("model_warning"):
        print("Model Warning:", result.get("model_warning"))
    print("Features:", result.get("features"))
    if "enhanced_image" in result:
        print("Enhanced Image Base64 length:", len(result["enhanced_image"]))

if __name__ == "__main__":
    test_mri_engine()
