import os
from PIL import Image
import numpy as np
import cv2
import base64
from io import BytesIO

TORCH_IMPORT_ERROR = None

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torchvision import transforms
except Exception as exc:
    torch = None
    nn = None
    F = None
    transforms = None
    TORCH_IMPORT_ERROR = exc

if nn is not None:
    class MyModel(nn.Module):
        def __init__(self, num_classes):
            super(MyModel, self).__init__()
            self.conv1 = nn.Conv2d(3, 32, kernel_size=4, stride=1, padding=0)
            self.bn1 = nn.BatchNorm2d(32)
            self.conv2 = nn.Conv2d(32, 64, kernel_size=4, stride=1, padding=0)
            self.bn2 = nn.BatchNorm2d(64)
            self.conv3 = nn.Conv2d(64, 128, kernel_size=4, stride=1, padding=0)
            self.bn3 = nn.BatchNorm2d(128)
            self.conv4 = nn.Conv2d(128, 128, kernel_size=4, stride=1, padding=0)
            self.bn4 = nn.BatchNorm2d(128)
            self.pool = nn.MaxPool2d(kernel_size=3, stride=3)
            self.pool2 = nn.MaxPool2d(kernel_size=3, stride=2)
            self.fc1 = nn.Linear(6 * 6 * 128, 512)
            self.fc2 = nn.Linear(512, num_classes)
            self.flatten = nn.Flatten()
            self.relu = nn.ReLU()
            self.dropout = nn.Dropout(0.5)

        def forward(self, x):
            x = self.relu(self.bn1(self.conv1(x)))
            x = self.pool(x)
            x = self.relu(self.bn2(self.conv2(x)))
            x = self.pool(x)
            x = self.relu(self.bn3(self.conv3(x)))
            x = self.pool2(x)
            x = self.relu(self.bn4(self.conv4(x)))
            x = self.flatten(x)
            x = self.relu(self.fc1(x))
            x = self.dropout(x)
            x = self.fc2(x)
            return x
else:
    class MyModel:
        pass

class MRIEngine:
    def __init__(self):
        self.model_runtime_available = all(item is not None for item in (torch, nn, F, transforms))
        self.device = "cuda" if self.model_runtime_available and torch.cuda.is_available() else "cpu"
        self.model_path = os.path.join(os.path.dirname(__file__), "..", "..", "ml", "models", "mri_model.pth")
        self.num_classes = 5
        self.label_dict = {
            0: "No Tumor",
            1: "Pituitary",
            2: "Glioma",
            3: "Meningioma",
            4: "Other",
        }
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            ),
        ]) if self.model_runtime_available else None
        self.model = self._load_model()

    def _load_model(self):
        if not self.model_runtime_available:
            return None
        if not os.path.exists(self.model_path):
            return None
        model = MyModel(num_classes=self.num_classes)
        model.load_state_dict(torch.load(self.model_path, map_location=self.device))
        model.to(self.device)
        model.eval()
        return model

    def predict(self, image_bytes):
        try:
            image = Image.open(image_bytes).convert("RGB")
            enhanced_b64, binary_b64 = self._process_visuals(image)
            features = self._extract_features(image)
            inference = self._predict_with_model(image)
            if inference is None:
                inference = self._predict_with_fallback(features, image)

            return {
                "prediction_class": inference["prediction_class"],
                "prediction_label": inference["prediction_label"],
                "confidence": inference["confidence"],
                "probabilities": inference["probabilities"],
                "enhanced_image": enhanced_b64,
                "binary_image": binary_b64,
                "features": features,
                "inference_mode": inference["inference_mode"],
                "model_warning": inference.get("model_warning"),
            }
        except Exception as e:
            return {"error": f"MRI prediction failed: {str(e)}"}

    def _predict_with_model(self, image):
        if self.model is None or self.transform is None or torch is None or F is None:
            return None

        image_tensor = self.transform(image).unsqueeze(0).to(self.device)

        with torch.no_grad():
            outputs = self.model(image_tensor)
            probs = F.softmax(outputs, dim=1)
            confidence, predicted = torch.max(probs, 1)

        predicted_class = predicted.item()
        conf_value = round(float(confidence.item()), 4)
        return {
            "prediction_class": predicted_class,
            "prediction_label": self.label_dict.get(predicted_class, "Unknown"),
            "confidence": conf_value,
            "probabilities": [round(float(item), 6) for item in probs.squeeze(0).tolist()],
            "inference_mode": "model",
        }

    def _predict_with_fallback(self, features, image):
        grayscale = np.array(image.convert("L"), dtype=np.float32)
        mean_intensity = float(np.mean(grayscale)) / 255.0
        std_intensity = float(np.std(grayscale)) / 255.0
        edges = cv2.Canny(grayscale.astype(np.uint8), 40, 120)
        edge_density = float((edges > 0).mean())
        bright_ratio = float((grayscale > 180).mean())
        dark_ratio = float((grayscale < 60).mean())
        symmetry_score = float(features["Symmetry Score"])

        raw_scores = np.array([
            1.6 + symmetry_score - edge_density * 1.8 - dark_ratio * 0.8,
            0.9 + bright_ratio * 1.7 + std_intensity * 0.7,
            0.8 + dark_ratio * 1.8 + edge_density * 1.4 + (1.0 - symmetry_score),
            0.75 + std_intensity * 1.5 + bright_ratio * 0.8 + dark_ratio * 0.5,
            0.65 + edge_density * 1.2 + abs(mean_intensity - 0.5),
        ], dtype=np.float32)

        raw_scores = raw_scores - np.max(raw_scores)
        exp_scores = np.exp(raw_scores)
        probabilities = exp_scores / np.sum(exp_scores)
        predicted_class = int(np.argmax(probabilities))

        return {
            "prediction_class": predicted_class,
            "prediction_label": self.label_dict.get(predicted_class, "Unknown"),
            "confidence": round(float(np.max(probabilities)), 4),
            "probabilities": [round(float(item), 6) for item in probabilities.tolist()],
            "inference_mode": "fallback",
            "model_warning": (
                f"Using fallback MRI heuristics because the trained model runtime is unavailable"
                f"{': ' + str(TORCH_IMPORT_ERROR) if TORCH_IMPORT_ERROR else ''}."
            ),
        }

    def _extract_features(self, image):
        grayscale = np.array(image.convert("L"), dtype=np.float32)
        left_half = grayscale[:, : grayscale.shape[1] // 2]
        right_half = np.fliplr(grayscale[:, grayscale.shape[1] // 2 :])
        min_width = min(left_half.shape[1], right_half.shape[1])
        if min_width > 0:
            left_half = left_half[:, :min_width]
            right_half = right_half[:, :min_width]
            symmetry = 1.0 - min(np.mean(np.abs(left_half - right_half)) / 255.0, 1.0)
        else:
            symmetry = 0.5

        std_intensity = float(np.std(grayscale))
        tissue_density = min(0.99, max(0.1, std_intensity / 90.0))
        anomaly_volume = max(0.0, (1.0 - symmetry) * 8.0 + tissue_density * 2.5)

        return {
            "Signal Intensity": round(float(np.mean(grayscale)), 2),
            "Tissue Density": round(float(tissue_density), 3),
            "Symmetry Score": round(float(symmetry), 3),
            "Anomaly Volume (est)": f"{anomaly_volume:.1f} cm³" if anomaly_volume >= 0.2 else "0.0 cm³",
        }

    def _process_visuals(self, pil_image):
        """Prepare enhanced and binary images for UI display."""
        img = np.array(pil_image.convert("L"))
        
        # Enhanced with CLAHE
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(img)
        
        # Binary Segmentation (Otsu)
        _, binary = cv2.threshold(enhanced, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        return self._to_base64(enhanced), self._to_base64(binary)

    def _to_base64(self, img_array):
        _, buffer = cv2.imencode(".jpg", img_array)
        return base64.b64encode(buffer).decode("utf-8")
