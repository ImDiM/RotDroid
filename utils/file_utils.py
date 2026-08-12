import base64
import csv
from datetime import datetime
import io
import shutil
import cv2
import pandas as pd
import os
import time
import json
from typing import List, Dict, Union
from PIL import Image
import json
import tqdm
from uiautomator2 import Device

def read_json(file_path: str) -> Union[Dict, List[Dict]]:
    if not os.path.exists(file_path):
        print(f"no exist: {file_path}")
        return None
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file) 
    return data

def write_json(file_path: str, content: Union[Dict, List[Dict]]):
    with open(file_path,'w', encoding='utf-8')as file:
        json.dump(content,file,ensure_ascii=False,indent=4)


def read_jsonl(file_path: str) -> List[Dict]:
    if not os.path.exists(file_path):
        print(f"no exist: {file_path}")
        return None
    data = []
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            if line.strip() != '':
                data.append(json.loads(line))

    return data


def write_jsonl(file_path: str, data: Union[List[Union[Dict,List]], Dict]=''):
    if type(data) == dict: 
        data = [data]
    if os.path.dirname(file_path) :  
        os.makedirs(os.path.dirname(file_path), exist_ok=True)  
    with open(file_path, 'w', encoding='utf-8') as file:
        for line in data:
            line = json.dumps(line, ensure_ascii=False)
            file.write(line + '\n')

def clear_jsonl(file_path: str):
    if os.path.dirname(file_path) :  
        os.makedirs(os.path.dirname(file_path), exist_ok=True)  
    with open(file_path, 'w', encoding='utf-8') as file:
        pass

def append_jsonl(file_path: str, data: Union[List[Dict], Dict]):
    if type(data) == dict:
        data = [data]
    if os.path.dirname(file_path) :  
        os.makedirs(os.path.dirname(file_path), exist_ok=True)  
    with open(file_path, 'a', encoding='utf-8') as file:
        for line in data:
            line = json.dumps(line, ensure_ascii=False)
            file.write(line + '\n')


def readfile_to_list(file_path: str='urls.xml',encoding='utf-8') -> List[str]:
    urls = []
    with open(file_path, 'r', encoding=encoding) as file:
        for line in file:
            if line.strip() != '':
                urls.append(line.strip())
    return urls

def read_file(file_path: str, encoding='utf-8') -> str:
    with open(file_path, 'r', encoding=encoding) as file:
        content = file.read()
    return content

def write_file(file_path: str, data: List[str]):
    if os.path.dirname(file_path) :  
        os.makedirs(os.path.dirname(file_path), exist_ok=True) 
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(data)

def read_excel(file_path: str) -> List[Dict]:
    if not os.path.exists(file_path):
        print(f"no exist: {file_path}")
        return None

    df = pd.read_excel(file_path, sheet_name='Sheet1')
    data = df.to_dict(orient='records')
    return data

def write_excel(file_path: str, data: List[Dict]):
    if os.path.dirname(file_path) :  
        os.makedirs(os.path.dirname(file_path), exist_ok=True) 
    df = pd.DataFrame(data)
    df.to_excel(file_path, index=False, sheet_name='Sheet1')


def write_csv(file_path: str, header:Union[List[str], str],data: Union[List[Dict], Dict]):
    if type(data) == dict: 
        data = [data]
    if type(header) == str: 
        header = [header]
    if os.path.dirname(file_path) :  
        os.makedirs(os.path.dirname(file_path), exist_ok=True) 
    with open(file_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=header)
        writer.writeheader()
        writer.writerows(data)

def read_csv(file_path: str) -> List[Dict]:
    if not os.path.exists(file_path):
        print(f"no exist: {file_path}")
        return None
    with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        data = [row for row in reader]
        return data


def get_github_token(token_file):
    github_token=''
    if os.path.exists(token_file):
        token = read_json(token_file)
        github_token=token.get('github')
        return github_token
    else:
        return ''
    
def get_token(name):
    token_file='configs/token.json'
    if os.path.exists(token_file):
        data = read_json(token_file)
        token=data.get(name)
        return token
    else:
        return ''

def get_cv2image(path, grayscale=False):
    if grayscale:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    else:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Image not found at path: {path}")
    return img
  
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')
       
    
def get_image_size(image_path):
    with Image.open(image_path) as img:
        width, height = img.size
    return width, height

def save_hierachy(filepath,data):
    if os.path.dirname(filepath) :
        os.makedirs(os.path.dirname(filepath), exist_ok=True) 
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(data)
    return filepath

def save_screenshot(filepath,d:Device):
    if os.path.dirname(filepath) :
        os.makedirs(os.path.dirname(filepath), exist_ok=True)  
    d.screenshot(filepath)
    return filepath

def clear_dir(directory):
    try:
        if os.path.exists(directory):
            shutil.rmtree(directory)
        os.makedirs(directory, exist_ok=True)
    except Exception as e:
        print(f"fail {directory}: {e}")
        
    print(f"have cleared: {directory}")

def count_files_in_directory(directory):
    file_count = 0
    for item in os.listdir(directory):
        if os.path.isfile(os.path.join(directory, item)):
            file_count += 1
    return file_count

def get_curtime():
    return datetime.now().strftime("%Y%m%d%H%M%S")

