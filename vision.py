import requests
import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForCausalLM 

def initialize_vision_model():
    vision_path = "microsoft/Florence-2-base-ft"
    vision_model = AutoModelForCausalLM.from_pretrained(vision_path, trust_remote_code=True)
    processor = AutoProcessor.from_pretrained(vision_path, trust_remote_code=True)
    
    # Use MPS if available (Apple Silicon), else fallback to CPU
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    vision_model.to(device)
    return vision_model, processor, device

if __name__ == "__main__":
    # Initialize the model and processor
    vision_model, processor, device = initialize_vision_model()

    # Load an image from a URL
    image_url = "https://www.petassure.com/petassure/file-streams/page/nAk0IIkia4IAggZg00k0p1caring-for-those-new-puppies.jpg.jpg"
    response = requests.get(image_url, stream=True)
    img = Image.open(response.raw).convert("RGB")
    
    # Provide a text prompt along with the image
    prompt_text = "Describe this image in detail."
    inputs = processor(text=prompt_text, images=img, return_tensors="pt")
    inputs = {k: v.to(device) for k, v in inputs.items()}
    
    # Generate output using the model
    outputs = vision_model.generate(**inputs)
    generated_text = processor.batch_decode(outputs, skip_special_tokens=True)[0]
    print("Generated Text:", generated_text)
