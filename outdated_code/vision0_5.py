import requests
import torch
from PIL import Image
from transformers import AutoProcessor, AutoModelForCausalLM 
from phi_3_vision_mlx import generate
import sys
from io import StringIO

# Redirect stdout to suppress internal prints
old_stdout = sys.stdout
sys.stdout = StringIO()

if __name__ == "__main__":
    # Load an image from a URL
    image_url = "https://www.petassure.com/petassure/file-streams/page/nAk0IIkia4IAggZg00k0p1caring-for-those-new-puppies.jpg.jpg"
    result = generate('What is shown in this image?', image_url, verbose=False)
    clean_result = result.replace("<|end|>", "").strip()
    sys.stdout = old_stdout

    print(clean_result.strip())