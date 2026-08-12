import os
import shutil
import cv2
from PIL import Image
import imagehash
import numpy as np
from collections import defaultdict

from utils import write_json, get_image_size

def compute_image_hash(image_path):
    try:

        img = cv2.imdecode(np.fromfile(image_path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise ValueError(f"Failed to read image: {image_path}")
        pil_img = Image.fromarray(img)
        hash_value = imagehash.dhash(pil_img)
        return hash_value
    except Exception as e:
        print(f"Error while processing image {image_path}: {e}")
        return None

def deduplicate_images(capture_dir, threshold=5):
    hash_dict={}
    for subdir in os.listdir(capture_dir):
        subdir_path = os.path.join(capture_dir, subdir)
        if not os.path.isdir(subdir_path):
            continue
        for filename in os.listdir(subdir_path):
            if filename.lower().endswith('_portrait.png'):
                image_path = os.path.join(subdir_path, filename)
                l_filename = image_path.replace('_portrait.png','_landscape.png')
                p_size = get_image_size(image_path)
                l_size = get_image_size(l_filename)
                if p_size == l_size:
                    print(p_size)
                    print(l_filename)
                    continue

                image_hash = compute_image_hash(image_path)                
                if image_hash is None:
                    continue
                found_similar = False
                for existing_hash in hash_dict.keys():
                    distance = image_hash - existing_hash
                    if distance <= threshold:
                        hash_dict[existing_hash].append(image_path)
                        found_similar = True
                        break
                
                if not found_similar:
                    hash_dict[image_hash] = [] 
                    hash_dict[image_hash].append(image_path)
                    
    result = {str(k): v for k, v in hash_dict.items()}
    return result

def process_duplicates(hash_dict, output_replace):
    unique_count = 0
    for hash_value, image_paths in hash_dict.items():

        p_unique_image = image_paths[0]
        output_path = p_unique_image.replace('capture',output_replace)
        output_dir = os.path.dirname(output_path)
        os.makedirs(output_dir, exist_ok=True)
        shutil.copy(p_unique_image, output_path)

        l_unique_image=p_unique_image.replace('_portrait.png','_landscape.png')
        output_path = l_unique_image.replace('capture',output_replace)
        shutil.copy(l_unique_image, output_path)

        p_unique_xml=p_unique_image.replace('png','xml')
        output_path = p_unique_xml.replace('capture',output_replace)
        shutil.copy(p_unique_xml, output_path)
        
        l_unique_xml=l_unique_image.replace('png','xml')
        output_path = l_unique_xml.replace('capture',output_replace)
        shutil.copy(l_unique_xml, output_path)
        unique_count += 1
        
    print(f"Retained {unique_count} unique image pairs in total")

