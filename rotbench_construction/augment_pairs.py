import logging
import os
import random
import shutil
import cv2
import numpy as np
import xml.etree.ElementTree as ET
from skimage.metrics import structural_similarity as ssim
from time import sleep
from tqdm import tqdm

from models import ModelFactory,VLMMessager
from utils import read_file, read_jsonl, clear_jsonl,append_jsonl,get_cv2image,parse_bounds
from configs import text_prompt
from PIL import Image
from explorer import mark_shape
from utils import get_image_size,clear_dir
from datetime import datetime

import pytesseract
tesseract_cmd = r'C:/Program Files/Tesseract-OCR/tesseract.exe'
pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

def widget_in_pair(xmlpath, node):
    if xmlpath.endswith('_landscape.xml'):
        pairxmlpath = xmlpath.replace('_landscape.xml', '_portrait.xml')
    elif xmlpath.endswith('_portrait.xml'):
        pairxmlpath = xmlpath.replace('_portrait.xml', '_landscape.xml')    
    else:
        print(f"Error: unrecognized XML filename format: {xmlpath}")
        return False
    
    img= get_cv2image(xmlpath.replace('.xml', '.png'))
    pairimg= get_cv2image(pairxmlpath.replace('.xml', '.png'))
    
    area=node.get('area')    

    x1,y1,x2,y2 = node.get('bounds')
    subimg = img[y1:y2, x1:x2]    
    size = (100, 100)
    crop1 = cv2.resize(subimg, size, interpolation=cv2.INTER_AREA)

    pair_tree = ET.parse(pairxmlpath)
    pair_root = pair_tree.getroot()
    pair_nodes = pair_root.findall(".//node")

    for i, pnode in enumerate(pair_nodes):
        if pnode.get("class") == node.get("class"):

            if node.get("class") in ['android.widget.Button','android.widget.TextView','android.widget.EditText']:
                if node.get("text") and node.get("text") == pnode.get('text', '') :
                    return True
            pbounds = pnode.get("bounds")
            if not pbounds:
                logging.info(f"Node {node.get('resource-id', 'unknown')} is missing the bounds attribute; skipping")
                continue

            x1, y1, x2, y2 = parse_bounds(pbounds)
            parea=(x2 - x1) * (y2 - y1)
            if parea <= 0:
                print(f"Node {pnode.get('resource-id', 'unknown')} has an invalid area; skipping: area={parea}")
                continue
            
            psubimg = pairimg[y1:y2, x1:x2]
            if psubimg is None or psubimg.size == 0:
                logging.error(f"psubimg is None. bounds=({x1},{y1},{x2},{y2})")
                continue
            crop2 = cv2.resize(psubimg, size, interpolation=cv2.INTER_AREA)
            ssim = compute_ssim(crop1, crop2)

            if ssim > 0.9 and 0.5 < area / parea < 2:
                return True
    return False


def get_class(imgsize, xml_path, class_list=None, exact_match=False):

    try:
        tree = ET.parse(xml_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"Failed to load view hierarchy file: {xml_path}")
    except ET.ParseError:
        raise ValueError(f"Invalid view hierarchy file format: {xml_path}")

    root = tree.getroot()
    nodes = root.findall(".//node")
    if not nodes:
        return []

    result = []
    for node in nodes:
        classname = node.get("class")
        package = node.get("package")
        text=node.get("text",'')
        resource_id = node.get("resource-id")
        
        if package == 'com.android.systemui':
            continue
        
        bounds = node.get("bounds")
        if not bounds:
            logging.info(f"Node {node.get('resource-id', 'unknown')} is missing the bounds attribute; skipping")
            continue
        try:
            x1, y1, x2, y2 = parse_bounds(bounds)
        except (ValueError, IndexError) as e:
            logging.error(f"bounds={str(bounds)} has an invalid format; skipping: {e}")
            continue
        
        x1= max(0, x1)
        x2= min(x2, imgsize[0])
        y1= max(0, y1)
        y2= min(y2, imgsize[1])
        if x1 >= x2 or y1 >=y2 or x1 >= imgsize[0] or y1 >= imgsize[1] or x2<=0 or y2 <=0:
            logging.error(f"bounds={bounds} is invalid; skipping")
            continue
        
        area = (x2 - x1) * (y2 - y1)
        should_include = class_list is None or (classname and (
            classname in class_list if exact_match else any(cls in classname for cls in class_list)
        ))
        
        if should_include:
            node_info = {
                'resource_id': resource_id if resource_id else 'Unknown',
                'class': classname if classname else 'Unknown',
                'bounds': (x1, y1, x2, y2),
                'area': area,
                'text': text,
            }
            if widget_in_pair(xml_path,node_info):
                result.append(node_info)
            
    if not result:
        return []
    
    return result



def mark_class( screenshot_path,savepath,views):
    mark_list = []
    for idx, region in enumerate(views, 1):
        color='green'
        mark_info = {
            'bounds': region['bounds'],
            'message': region['class'] if region['class'] else 'Unknown',

            'color': color,
            'shape': 'rectangle'
        }
        mark_list.append(mark_info)

    mark_shape(screenshot_path, savepath, mark_list)

def calculate_iou(box1, box2):
    if not box1 or not box2 or len(box1) != 4 or len(box2) != 4:
        return False
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)
    intersection = max(0, x2_i - x1_i) * max(0, y2_i - y1_i)
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection
    return intersection / union if union > 0 else 0


def add_white_border(img, border_size=200):
    bordered_img = cv2.copyMakeBorder(
        img,
        top=border_size,
        bottom=border_size,
        left=border_size,
        right=border_size,
        borderType=cv2.BORDER_CONSTANT,
        value=[255, 255, 255]
    )
    return bordered_img


def find_images_by_cv(screenshot_path, iou_threshold=0, largest=False):

    img = get_cv2image(screenshot_path)
    if img is None:
        print(f"Failed to load screenshot: {screenshot_path}")
        return []
    border_size = 50
    img = add_white_border(img, border_size)
    height, width = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    image_regions = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if area > 20000 and 0.6 < w/h < 3:
            image_regions.append((x, y, x + w, y + h, area))

    if not image_regions:
        return []

    image_regions.sort(key=lambda x: x[4], reverse=True)
    non_overlapping_regions = []
    for region in image_regions:
        x1, y1, x2, y2, area = region
        is_overlapping = False
        for kept_region in non_overlapping_regions:
            kept_x1, kept_y1, kept_x2, kept_y2, _ = kept_region
            iou = calculate_iou((x1, y1, x2, y2), (kept_x1, kept_y1, kept_x2, kept_y2))
            if iou > iou_threshold:
                is_overlapping = True
                break
        if not is_overlapping:
            non_overlapping_regions.append(region)

    if not non_overlapping_regions:
        return []
    adjusted_regions = []
    for x1, y1, x2, y2, area in non_overlapping_regions:
        x1_adj = max(0, x1 - border_size)
        y1_adj = max(0, y1 - border_size)
        x2_adj = min(img.shape[1] - 2 * border_size, x2 - border_size)
        y2_adj = min(img.shape[0] - 2 * border_size, y2 - border_size)
        area_adj = (x2_adj - x1_adj) * (y2_adj - y1_adj)
        if area_adj <= 0:
            print(f"Adjusted region area is invalid; skipping: ({x1_adj}, {y1_adj}, {x2_adj}, {y2_adj})")
            continue
        node_info = {
            'class': 'Image',
            'bounds': (x1_adj, y1_adj, x2_adj, y2_adj),
            'area': area_adj
        }
        adjusted_regions.append(node_info)

    if not adjusted_regions:
        print("No valid adjusted image region was found")
        return []
    if largest:
        largest_region = max(adjusted_regions, key=lambda x: x['area'])
        adjusted_regions = [largest_region]
    return adjusted_regions

def get_most_common_color(region_img):
    pixels = region_img.reshape(-1, 3)
    unique_colors, counts = np.unique(pixels, axis=0, return_counts=True)
    most_common_color= unique_colors[np.argmax(counts)]
    return tuple(int(c) for c in most_common_color)


def get_text_color(region_img):
    pixels = region_img.reshape(-1, 3)
    unique_colors, counts = np.unique(pixels, axis=0, return_counts=True)
    sorted_indices = np.argsort(counts)[::-1]
    b, g, r = unique_colors[sorted_indices[0]]
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    text_color = (255, 255, 255) if luminance < 128 else (0, 0, 0)
    return tuple(int(c) for c in text_color)

def get_border_color(img, region, border_size=10):
    x1, y1, x2, y2 = region
    top_y_start = max(0, y1 - border_size)
    top_y_end = y1
    bottom_y_start = y2
    bottom_y_end = min(img.shape[0], y2 + border_size)
    left_x_start = max(0, x1 - border_size)
    left_x_end = x1
    right_x_start = x2
    right_x_end = min(img.shape[1], x2 + border_size)
    top_border = img[top_y_start:top_y_end, max(0, x1):min(img.shape[1], x2)]
    bottom_border = img[bottom_y_start:bottom_y_end, max(0, x1):min(img.shape[1], x2)]
    left_border = img[max(0, y1):min(img.shape[0], y2), left_x_start:left_x_end]
    right_border = img[max(0, y1):min(img.shape[0], y2), right_x_start:right_x_end]
    border_pixels = np.concatenate([
        top_border.reshape(-1, 3),
        bottom_border.reshape(-1, 3),
        left_border.reshape(-1, 3),
        right_border.reshape(-1, 3)
    ], axis=0)

    if border_pixels.size == 0:
        print("Warning: the border region has no valid pixels; returning default color (0, 0, 0)")
        return (0, 0, 0)

    unique_colors, counts = np.unique(border_pixels, axis=0, return_counts=True)
    most_common_color = unique_colors[np.argmax(counts)]
    return tuple(int(c) for c in most_common_color)

def convert_transparent(widget_img, alpha_value=0.5):
    widget_bgra = cv2.cvtColor(widget_img, cv2.COLOR_BGR2BGRA)
    widget_bgra[:, :, 3] = int(alpha_value * 255)
    return widget_bgra


def compute_ssim(img1, img2, win_size=7):
    if img1.shape != img2.shape:
        raise ValueError("Input images must have the same dimensions for SSIM.")

    h, w = img1.shape[:2]
    min_side = min(h, w)

    if min_side < win_size:
        return 0.0
    
    if img1.ndim == 3 and img1.shape[2] in (3, 4):
        img1_ch = img1[..., :3]
        img2_ch = img2[..., :3]
        score, _ = ssim(
            img1_ch, img2_ch,
            full=True,
            channel_axis=2,
            win_size=win_size
        )
    else:
        score, _ = ssim(
            img1, img2,
            full=True,
            win_size=win_size
        )
    return float(score)
    
    
def rotate_image(imgpath, xml_path, angle=None):
    img = get_cv2image(imgpath)
    if img is None:
        print(f"Failed to read image: {imgpath}")
        return None
    
    if angle is None:
        angle = random.choice([90, -90, 180])
    
    imgsize=get_image_size(imgpath)
    views=get_class(imgsize,xml_path,class_list=['ImageView'], exact_match=False)
    cv_views=find_images_by_cv(imgpath,largest=True) 
    views.extend(cv_views)
    if not views:
        return None
    
    modified_list = []
    mutate=False
    for v in range(len(views)):
        region_selected = random.choice(views)
        region = region_selected['bounds']
        x1, y1, x2, y2 = region
        width = x2 - x1
        height = y2 - y1
        region_img = img[y1:y2, x1:x2]
        center = (width // 2, height // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        border_color=get_border_color(img,region,border_size=10)
        rotated_region = cv2.warpAffine(
                region_img, 
                matrix, 
                (width, height),
                flags=cv2.INTER_LINEAR,
                borderValue=border_color
            )
        modified_img = img.copy()
        modified_img[y1:y2, x1:x2] = rotated_region
        ssim_threshold = 0.99
        ssim=compute_ssim(modified_img[y1:y2, x1:x2], img[y1:y2, x1:x2])
        logging.info(f"SSIM = {ssim}")
        if ssim < ssim_threshold:
            mutate=True
            break
    if not mutate:
        return None 

    modified_list.append({'region':region,'modified_img':modified_img})
    return modified_list

def produce_text(imgpath,llm=False, model_config=None):
    text = "Sample Text"
    if not llm:
        return text
    if model_config is None:
        model_config={
            "name":"Qwen2.5-VL-7B-Instruct" ,
            "temperature":0.7,
            "max_token":25
        }

    model=ModelFactory.api_model(model_config)
    msger=VLMMessager()
    messages=msger.construct_prompt([imgpath],text_prompt)
    logging.info('img_path:'+imgpath)
    logging.info('prompt:' + text_prompt)
    reply=model.generate_chat(messages=messages,temperature=model_config['temperature'],max_tokens=model_config['max_token'])['output']
    logging.info('reply:'+ reply)  
    text=reply.strip()     
    return text

def fill_text(imgpath, xml_path, text=None, model_config=None):
    def fill(img, region, text=None):
        x1, y1, x2, y2 = region
        width = x2 - x1
        height = y2 - y1

        if text is None:
            marks = [{
                'bounds': region,
                'message': '',
                'color': 'red',
                'shape': 'rectangle'
            }]
            markpath = 'tmp.png'
            mark_shape(imgpath, markpath, marks)
            text = produce_text(markpath, llm=True, model_config=model_config)

        region_img = img[y1:y2, x1:x2]
        most_common_color = get_most_common_color(region_img)
        scale_factor = 1
        region_img_gray = cv2.cvtColor(region_img, cv2.COLOR_BGR2GRAY)

        region_img_resized = cv2.resize(
            region_img_gray, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC
        )
        pil_img = Image.fromarray(region_img_resized)
        ocr_data = pytesseract.image_to_data(
            pil_img,
            lang='eng',

            config='--psm 6',
            output_type=pytesseract.Output.DICT
        )
        logging.info(f'imgpath={imgpath}"')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        cv2.imwrite(f'test_ocr/{os.path.basename(imgpath)}_preprocessed_{timestamp}.png', region_img_resized)
        debug_img = region_img.copy()
        logging.info(f"OCR result {len(ocr_data['text'])}:")
        for i in range(len(ocr_data['text'])):
            ocr_text=ocr_data['text'][i].strip()
            if ocr_text:
                ocr_x1 = ocr_data['left'][i] // scale_factor
                ocr_y1 = ocr_data['top'][i] // scale_factor
                ocr_width = ocr_data['width'][i] // scale_factor
                ocr_height = ocr_data['height'][i] // scale_factor
                logging.info(f"Text: '{ocr_data['text'][i]}', coordinates: (left={ocr_x1}, top={ocr_y1}, width={ocr_width}, height={ocr_height}), confidence: {ocr_data['conf'][i]}")
                cv2.rectangle(debug_img, (ocr_x1, ocr_y1), (ocr_x1 + ocr_width, ocr_y1 + ocr_height), (0, 255, 0), 1)
        cv2.imwrite(f'test_ocr/{os.path.basename(imgpath)}_ocrboxes_{timestamp}.png', debug_img)

        modified_img = img.copy()
        border = 2
        ocr_left = x2
        ocr_right = x1
        ocr_top = y2
        ocr_bottom = y1
        logging.info(f"ocr_left: {ocr_left}, ocr_right: {ocr_right}, ocr_top: {ocr_top}, ocr_bottom: {ocr_bottom}")
        for i in range(len(ocr_data['text'])):
            ocr_text=ocr_data['text'][i].strip()
            if ocr_data['conf'][i] > 30 and any(c.isalnum() or c == '.' for c in ocr_text):
                ocr_x = ocr_data['left'][i] // scale_factor
                ocr_y = ocr_data['top'][i] // scale_factor
                ocr_w = ocr_data['width'][i] // scale_factor
                ocr_h = ocr_data['height'][i] // scale_factor
                text_bg_x1 = max(x1, x1 + ocr_x)
                text_bg_y1 = max(y1, y1 + ocr_y)
                text_bg_x2 = min(x2, x1 + ocr_x + ocr_w)
                text_bg_y2 = min(y2, y1 + ocr_y + ocr_h)
                cv2.rectangle(
                    modified_img,
                    pt1=(text_bg_x1-border, text_bg_y1-border),
                    pt2=(text_bg_x2+border, text_bg_y2+border),
                    color=most_common_color,
                    thickness=-1
                )
                ocr_left=min(ocr_left, text_bg_x1)
                ocr_right=max(ocr_right, text_bg_x2)
                ocr_top=min(ocr_top, text_bg_y1)
                ocr_bottom=max(ocr_bottom, text_bg_y2)
                logging.info(f"update ocr_left: {ocr_left}, ocr_right: {ocr_right}, ocr_top: {ocr_top}, ocr_bottom: {ocr_bottom}")

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.0
        thickness = 2
        padding = 10
        text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
        text_width, text_height = text_size[0], text_size[1]

        if ocr_left != x2:
            text_x = ocr_left
            logging.info(f"Using the leftmost OCR text coordinate: {text_x}")
        else:
            text_x = x1 + padding
            logging.info(f"Falling back to the default margin: {text_x}")
        text_y = y1 + (height + text_height) // 2
        if text_x + text_width > x2 - padding:
            text_x = x2 - text_width - padding
            if text_x < x1 + padding:
                text_x = x1 + padding
                while text and (text_x + text_width > x2 - padding):
                    text = text[:-1]
                    text_size = cv2.getTextSize(text + "...", font, font_scale, thickness)[0]
                    text_width, text_height = text_size[0], text_size[1]
                text = text + "..." if text else "Text too long"

        text_color = get_text_color(region_img)
        cv2.putText(
            modified_img,
            text,
            (text_x, text_y),
            font,
            font_scale,
            text_color,
            thickness,
            cv2.LINE_AA
        )
        return modified_img

    img = get_cv2image(imgpath)
    if img is None:
        print(f"Failed to read image: {imgpath}")
        return None

    imgsize=get_image_size(imgpath)
    views = get_class(imgsize,xml_path, class_list=['EditText'], exact_match=False)
    if not views:
        return None

    modified_list = []
    for v in views:
        region = v['bounds']
        x1,y1,x2,y2 = region
        modified_img = fill(img, region, text)
        if modified_img is not None:
            ssim_threshold = 1
            ssim=compute_ssim(modified_img[y1:y2, x1:x2], img[y1:y2, x1:x2])
            logging.info(f"SSIM = {ssim}")
            if ssim < ssim_threshold:
                modified_list.append({'region': region, 'modified_img': modified_img, 'text': text})

    return modified_list

def wrap_text(text, font, font_scale, thickness, max_width):
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        test_line = ' '.join(current_line)
        (text_width, _), _ = cv2.getTextSize(test_line, font, font_scale, thickness)
        if text_width > max_width:
            if len(current_line) > 1:
                current_line.pop()
                lines.append(' '.join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
        if word == words[-1] and current_line:
            lines.append(' '.join(current_line))

    line_dimensions = [
        cv2.getTextSize(line, font, font_scale, thickness) for line in lines
    ]
    return lines, line_dimensions


def move_widget(imgpath, xml_path):
    modified_list=[]
    img = get_cv2image(imgpath)
    if img is None:
        print(f"Failed to read image: {imgpath}")
        return None
    screen_width,screen_height=get_image_size(imgpath)
    screen_area=screen_width * screen_height
    text_views=[]
    icon_views=[]
    other_views=[]
    imgsize=get_image_size(imgpath)
    views = get_class(imgsize,xml_path, class_list=None, exact_match=False)
    for v in views:

        if v['class'] == 'android.widget.EditText'or v['class'] == 'android.widget.TextView':
            text_views.append(v)
        elif v['class'] == 'android.widget.ImageView' or v['class'] == 'android.widget.Button':
            icon_views.append(v)
        elif v['area'] < screen_area/4:
            other_views.append(v)

    candidate_views = text_views + icon_views + other_views
    if not candidate_views:
        return None
    
    def get_newxy(source_region, target_region):
        tgt_x1, tgt_y1, tgt_x2, tgt_y2 = target_region
        src_x1, src_y1, src_x2, src_y2 = source_region
        src_width = src_x2 - src_x1
        src_height = src_y2 - src_y1
        src_area = src_width * src_height
        src_midx=(src_x1 + src_x2) // 2
        src_midy=(src_y1 + src_y2) // 2
        
        tgt_width = tgt_x2 - tgt_x1
        tgt_height = tgt_y2 - tgt_y1
        tgt_area = tgt_width * tgt_height
        tgt_midx=(tgt_x1 + tgt_x2) // 2
        tgt_midy=(tgt_y1 + tgt_y2) // 2

        rand_dx = random.randint(-tgt_width // 2, tgt_width // 2)
        rand_dy = random.randint(-tgt_height // 2, tgt_height // 2)
        init_x1 = tgt_midx - src_width // 2 + rand_dx
        init_y1 = tgt_midy - src_height // 2 + rand_dy
        init_x2 = init_x1 + src_width
        init_y2 = init_y1 + src_height
        if init_x1 < 0:
            init_x2 += (-init_x1)
            init_x1 = 0
        if init_x2 > img_width:
            delta = init_x2 - img_width
            init_x1 -= delta
            init_x2 = img_width

        if init_y1 < 0:
            init_y2 += (-init_y1)
            init_y1 = 0
        if init_y2 > img_height:
            delta = init_y2 - img_height
            init_y1 -= delta
            init_y2 = img_height
        if init_x1 < 0 or init_y1 < 0 or init_x2 > img_width or init_y2 > img_height:
            logging.error(f"New coordinates are outside image bounds: ({init_x1}, {init_y1}, {init_x2}, {init_y2})")
            return None
        return init_x1, init_y1, init_x2, init_y2


    mutate=False
    for _ in range(5):
        is_overlapping = True
        img_height, img_width = img.shape[:2]

        source_weights = [10] * len(icon_views) + [3] * len(text_views)+ [1] * len(other_views)
        source_region_selected = random.choices(candidate_views, weights=source_weights, k=1)[0]
        target_weights = [10] * len(text_views) + [3] * len(icon_views)+ [1] * len(other_views)
        target_region_selected = random.choices(candidate_views, weights=target_weights, k=1)[0]
        source_region = source_region_selected['bounds']
        src_x1, src_y1, src_x2, src_y2 = source_region
        if source_region_selected['bounds'] != target_region_selected['bounds'] and \
            0 <= src_x1 < src_x2 <= img_width and 0 <= src_y1 < src_y2 <= img_height: 
            is_overlapping = False
            src_img = img[src_y1:src_y2, src_x1:src_x2].copy()
            target_region = target_region_selected['bounds']

            modified_img = cv2.cvtColor(img.copy(), cv2.COLOR_BGR2BGRA)

            fill_color = get_border_color(img, source_region)
            cv2.rectangle(modified_img, (src_x1, src_y1), (src_x2, src_y2), fill_color + (255,), -1)

            text= None
            if source_region_selected['class'] in ['android.widget.EditText', 'android.widget.TextView']:
                text = source_region_selected.get('text', None)
                logging.info(f'Extracted text: {text}')
            if text and text.strip():
                text = text.strip()
                font = cv2.FONT_HERSHEY_SIMPLEX
                font_scale = 1.2
                thickness = 2

                src_width = src_x2 - src_x1
                lines, line_dims = wrap_text(text, font, font_scale, thickness, src_width)

                total_w = max([
                    line_dim[0][0]
                    for line_dim in line_dims
                ])
                line_spacing=5
                total_h = sum([
                    line_dim[0][1] + line_dim[1] + line_spacing
                    for line_dim in line_dims
                ])
                total_baseline = max([
                    line_dim[1]
                    for line_dim in line_dims
                ])
                
                text_region=(0,0,total_w,total_h)
                new_region= get_newxy(text_region, target_region)
                if new_region:
                    new_x1, new_y1, new_x2, new_y2 = new_region
                else: 
                    print(f"No suitable new position found; skipping")
                    continue

                text_color = get_text_color(src_img)
                line_h = total_h // len(lines)
                for i, line in enumerate(lines,start=1):
                    text_x = new_x1
                    text_y = int(new_y1 + line_h*i - total_baseline)
                    cv2.putText(
                        modified_img,
                        line,
                        (text_x, text_y),
                        font,
                        font_scale,
                        text_color,
                        thickness,
                        cv2.LINE_AA
                    )     
                
            else:
                new_region = get_newxy(source_region, target_region)
                if new_region:
                    new_x1, new_y1, new_x2, new_y2 = new_region
                else:
                    print(f"No suitable new position found; skipping")
                    continue

                alpha_value=random.choice([0.6, 1])
                src_bgra = convert_transparent(src_img, alpha_value)

                moveto_regionimg = modified_img[new_y1:new_y2, new_x1:new_x2]
                alpha = src_bgra[:, :, 3] / 255.0
                alpha_inv = 1.0 - alpha
                for c in range(3):
                    moveto_regionimg[:, :, c] = (alpha * src_bgra[:, :, c] + alpha_inv * moveto_regionimg[:, :, c]).astype(np.uint8)
                moveto_regionimg[:, :, 3] = 255
            
            modified_img = cv2.cvtColor(modified_img, cv2.COLOR_BGRA2BGR)
            
            tgt_x1, tgt_y1, tgt_x2, tgt_y2 = target_region
            overlap_x1=min(new_x1,tgt_x1)
            overlap_x2=max(new_x2,tgt_x2)
            overlap_y1=min(new_y1,tgt_y1)
            overlap_y2=max(new_y2,tgt_y2)
            overlap_region =(overlap_x1,overlap_y1,overlap_x2,overlap_y2)
           
            ssim_threshold = 0.99
            ssim=compute_ssim(modified_img[overlap_y1:overlap_y2, overlap_x1:overlap_x2], img[overlap_y1:overlap_y2, overlap_x1:overlap_x2])

            logging.info(f"SSIM = {ssim}")
            if ssim < ssim_threshold:
                mutate=True
                break

    if is_overlapping:
        return None
    
    if not mutate:
        return None

    new_region = (new_x1, new_y1, new_x2, new_y2)
    modified_list.append({'region':overlap_region,'modified_img':modified_img})

    return modified_list


def clip_widget(imgpath, xml_path):
    modified_list = []
    img = get_cv2image(imgpath)
    if img is None:
        print(f"Failed to read image: {imgpath}")
        return None
    screen_width, screen_height = get_image_size(imgpath)
    screen_area = screen_width * screen_height
    other_views = []
    imgsize=get_image_size(imgpath)
    views = get_class(imgsize,xml_path, class_list=None, exact_match=False)
    for v in views:
        if v['area'] < screen_area / 4:
            other_views.append(v)
    candidate_views = other_views
    if not candidate_views:
        return None

    weights = [1] * len(other_views)
    if len(candidate_views) != len(weights):
        print(f"Error: candidate_views length ({len(candidate_views)}) does not match weights length ({len(weights)})")
        return None
    
    mutate=False
    for i in range(len(candidate_views)):
        widget_to_zoom = random.choices(candidate_views, weights=weights, k=1)[0]
        original_region = widget_to_zoom['bounds']
        x1, y1, x2, y2 = original_region
        src_width = x2 - x1
        src_height = y2 - y1
        src_midx = (x1 + x2) // 2
        src_midy = (y1 + y2) // 2
        modified_img = img.copy()
        clip_type=random.choice([0,1,2,3])
        if clip_type == 0:
            logging.info(f"clip_type=top-half")
            back_x1 = x1
            back_x2 = x2
            back_y1 = y1
            back_y2 = src_midy
        elif clip_type == 1:
            logging.info(f"clip_type=bottom-half")
            back_x1 = x1
            back_x2 = x2
            back_y1 = src_midy
            back_y2 = y2
        elif clip_type == 2:
            logging.info(f"clip_type=left-half")
            back_x1 = x1
            back_x2 = src_midx
            back_y1 = y1
            back_y2 = y2
        elif clip_type == 3:
            logging.info(f"clip_type=right-half")
            back_x1 = src_midx
            back_x2 = x2
            back_y1 = y1
            back_y2 = y2
            
        backcolor=get_most_common_color(modified_img[y1:y2,x1:x2])
        aroundcolor=get_border_color(img,original_region)
        cv2.rectangle(
            modified_img,
            pt1=(back_x1, back_y1),
            pt2=(back_x2, back_y2),
            color=aroundcolor,
            thickness=-1
        )
         
        if widget_to_zoom['class'] in ['android.widget.EditText','android.widget.TextView']:
 
            ocr_text_str= widget_to_zoom['text'].strip()
            logging.info(f"ocr_text_str: {ocr_text_str}")

            modi_ocr= pytesseract.image_to_data(
                modified_img[y1:y2, x1:x2],
                lang='eng',
                config='--psm 6',
                output_type=pytesseract.Output.DICT
            )
            
            modi_text_list=[]
            for i in range(len(modi_ocr['text'])):
                modi_text=modi_ocr['text'][i].strip()
                if modi_text.strip() != "":
                    logging.info(f"Text: '{modi_text}', confidence: {modi_ocr['conf'][i]}")
                if modi_text.strip() != "" and modi_ocr['conf'][i] > 20 :
                    modi_text_list.append(modi_text.strip())
            modi_text_str = " ".join(modi_text_list)
            logging.info(f"modi_text_str: {modi_text_str}")
            ssim=compute_ssim(modified_img[y1:y2, x1:x2], img[y1:y2, x1:x2])
            logging.info(f"SSIM = {ssim}")

            if modi_text_str and ocr_text_str and modi_text_str != ocr_text_str:
                logging.info(f"mutate=true")
                mutate=True
                break
            else:
                logging.info(f"pass")
            
        else:
            ssim_threshold = 0.9
            ssim=compute_ssim(modified_img[y1:y2, x1:x2], img[y1:y2, x1:x2])
            logging.info(f"SSIM = {ssim}")

            if ssim < ssim_threshold:
                mutate=True
                break
        
    if not mutate:
        logging.error("Change is too small; skipping")
        return None

    new_region = (x1, y1, x2, y2)
    modified_list.append({'region':new_region,'modified_img':modified_img})
    return modified_list

def delete_widget(imgpath, xml_path):
    img = get_cv2image(imgpath)
    if img is None:
        logging.error(f"Failed to read image: {imgpath}")
        return None

    xml_data = read_file(xml_path)
    root = ET.fromstring(xml_data)
    screen_width, screen_height = get_image_size(imgpath)
    screen_area = screen_width * screen_height

    other_views = []
    imgsize=get_image_size(imgpath)
    views = get_class(imgsize,xml_path, class_list=None, exact_match=False)
    for v in views:
        if v['class'] in ['android.widget.EditText']:
            continue
        if v['area'] < screen_area / 4:
            other_views.append(v)

    candidate_views = other_views
    if not candidate_views:
        return None
    
    weights = [1] * len(other_views)
    if len(candidate_views) != len(weights):
        logging.error(f"Error: candidate_views length ({len(candidate_views)}) does not match weights length ({len(weights)})")
        return None
    
    modified_list = []
    mutate=False
    for v in range(len(candidate_views)):
        widget_to_delete = random.choices(candidate_views, weights=weights, k=1)[0]
        delete_region = widget_to_delete['bounds']
        x1, y1, x2, y2 = delete_region
        modified_img = img.copy()
        fill_color = get_border_color(img, delete_region)
        cv2.rectangle(modified_img, (x1, y1), (x2, y2), fill_color, -1)
        
        ssim_threshold = 0.99
        ssim=compute_ssim(modified_img[y1:y2, x1:x2], img[y1:y2, x1:x2])
        logging.info(f"SSIM = {ssim}")
        if ssim < ssim_threshold:
            mutate=True
            break

    if not mutate:
        return None

    modified_list.append({'region':delete_region,'modified_img':modified_img})
    return modified_list

def augment_one(package_dir, output_dir, reconstruct=False, model_config=None):
    def mark_augment(input_path, output_path, new_bounds, message):
        if new_bounds:
            mark_after_list = []
            mark_info = {
                'bounds': new_bounds,
                'message': message,
                'color': 'red',
                'shape': 'rectangle'
            }
            mark_after_list.append(mark_info)
            mark_shape(input_path, output_path, mark_after_list)

    def copy_pcorrect(screenshot_path, output_subdir, package_name):
        if screenshot_path.endswith('_landscape.png'):
            src_path = screenshot_path.replace('landscape', 'portrait')
        elif screenshot_path.endswith('_portrait.png'):
            src_path = screenshot_path.replace('portrait', 'landscape')
        else:
            logging.error('Error: filename contains neither landscape nor portrait')
            return
        tgt_path = os.path.join(output_subdir, package_name, os.path.basename(src_path))
        os.makedirs(os.path.dirname(tgt_path), exist_ok=True)
        shutil.copy(src_path, tgt_path)

        tgt_screenshotpath = os.path.join(output_subdir, package_name, os.path.basename(screenshot_path))
        shutil.copy(screenshot_path, tgt_screenshotpath)
        return tgt_path
    
    def make_augment():
        output_subdir = os.path.join(output_dir, bugtype)
        if screenshot_path.endswith('_portrait.png'):
            orientation='portrait'
        elif screenshot_path.endswith('_landscape.png'):
            orientation='landscape'
        else:
            logging.error('Error: filename contains neither portrait nor landscape')
            return

        if not (not reconstruct and os.path.exists(os.path.join(output_subdir, package_name))):
            if bugtype == 'layout-overlap':
                modified_list = move_widget(screenshot_path, xml_path)
            elif bugtype == 'layout-clip':
                modified_list = clip_widget(screenshot_path, xml_path)
            elif bugtype == 'layout-miss':
                modified_list = delete_widget(screenshot_path, xml_path)
            elif bugtype == 'direction-mismatch':
                modified_list = rotate_image(screenshot_path, xml_path)
            elif bugtype == 'state-loseinput':
                modified_list = fill_text(screenshot_path, xml_path, model_config=model_config)
            else:
                logging.error('Error: unmatched bug type')

            if modified_list:
                for i, item in enumerate(modified_list):
                    modified_img = item['modified_img']
                    new_bounds = item['region']
                    savepath = os.path.join(output_subdir, package_name, f"{filename}_{bugtype}_{i}.png")
                    markpath=savepath.replace(".png", "_mark.png")

                    if os.path.dirname(savepath) :  
                        os.makedirs(os.path.dirname(savepath), exist_ok=True)
                    if not cv2.imwrite(savepath, modified_img):
                        logging.error(f"Failed to save image to {savepath}")
                        return None

                    mark_augment(savepath, markpath, new_bounds, bugtype)
                    tgt_path=copy_pcorrect(screenshot_path, output_subdir, package_name)
                    logging.info(f"savepath={savepath},bounds={new_bounds},tgt_path={tgt_path}")

                    image_dict={}
                    if orientation == 'portrait':
                        image_dict['portrait'] = savepath
                        image_dict['landscape'] = tgt_path
                        
                    elif orientation == 'landscape':
                        image_dict['portrait'] = tgt_path
                        image_dict['landscape'] = savepath

                    data_list.append({
                        'images': image_dict,
                        'defect': {'bug':True, 'type': bugtype,'image':orientation, 'bbox_2d': new_bounds}
                    })    
        
    data_list = []
    for name in os.listdir(package_dir):

        if name.endswith('.png'):
            screenshot_path = os.path.join(package_dir, name)
            xml_path = os.path.join(package_dir, name.replace('.png', '.xml'))
            filename = os.path.splitext(os.path.basename(name))[0]
            package_name=os.path.basename(package_dir)
            type_list=['layout-overlap', 'layout-clip', 'layout-miss', 'direction-mismatch','state-loseinput']
            for bugtype in type_list:
                make_augment()
            
    return data_list


def augment(input_dir, output_dir,metapath, reconstruct=False, model_config=None):

    for package_name in tqdm(os.listdir(input_dir)):
        package_dir = os.path.join(input_dir, package_name)
        datalist=augment_one(package_dir, output_dir, reconstruct, model_config=model_config)
        if datalist:
            append_jsonl(metapath, datalist)
            


