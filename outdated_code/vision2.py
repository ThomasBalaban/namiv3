import ollama
import requests
import tempfile
import time
from io import BytesIO
from PIL import Image  # Requires Pillow package

# Image URL
image1 = 'https://www.petassure.com/petassure/file-streams/page/nAk0IIkia4IAggZg00k0p1caring-for-those-new-puppies.jpg.jpg'
image2 = 'https://cdn.thewirecutter.com/wp-content/media/2022/03/elden-ring-2048px-0003.jpg?auto=webp&quality=75&crop=1.91:1&width=1200'
image3 = 'https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRLdHmrRTolnLaLEm1YBbetYqIwjDhi0DSCLQ&s'
image4 = 'https://images.nintendolife.com/screenshots/101499/large.jpg'


def optimize_image(image_bytes, target_size=512, quality=90):  # Increased size and quality
    """Resize image while preserving key details"""
    img = Image.open(BytesIO(image_bytes))
    
    # Preserve transparency for PNGs by converting to RGBA first
    if img.mode == 'P':
        img = img.convert('RGBA')
    elif img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')
    
    # Only resize if image is larger than target
    if max(img.size) > target_size:
        ratio = target_size / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.Resampling.BICUBIC)  # Softer scaling
    
    # Save with optimized but higher quality settings
    output = BytesIO()
    img.save(
        output,
        format='JPEG',
        quality=quality,
        optimize=True,
        subsampling=0,  # Keep color resolution high
        qtables='web_high'  # Use web-optimized quantization
    )
    return output.getvalue()

# Download the image
response = requests.get(image4, headers={'User-Agent': 'Mozilla/5.0'})
response.raise_for_status()  # Check for download errors

# OPTIMIZE HERE - Add this processing step
optimized_content = optimize_image(response.content)

# Save OPTIMIZED image to temporary file
with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_file:
    tmp_file.write(optimized_content)  # Use optimized content
    image_path = tmp_file.name

# Query Ollama with local image path
try:
    # Start timer
    start_time = time.time()

    res = ollama.chat(
        model="llama3.2-vision",
        messages=[
                {
                    'role': 'user', 
                    'content': '''
                        game: Five nights at freddys 3. Describe only the immediate action or conflict about to occur.
                        Focus on: [subject] + [action] + [key threat/environment]. 
                        Example: "game: Elden Ring. A warrior draws their sword facing a dragon in murky wetlands."
                        Avoid environmental adjectives. Keep under 150 chars.
                        ''', 
                    'images': [image_path]
                }
            ],
            options={'temperature': 0.2, 'num_predict': 100}
    )
    # Calculate elapsed time
    elapsed_time = time.time() - start_time
    
    # Print results
    print(f"\ngeneration took {elapsed_time:.1f}s\n")
    print(res['message']['content'])
    
finally:
    # Clean up temporary file
    import os
    os.remove(image_path)