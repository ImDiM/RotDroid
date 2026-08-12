import json
import os
import random
import pandas as pd
from sklearn.model_selection import train_test_split
from PIL import Image
from utils import read_jsonl, write_json,append_jsonl,read_json,get_smart_bbox
from configs import DEFECT_PROMPT,class_multi_prompt,class_2_prompt
from utils.file_utils import get_image_size, write_jsonl

def construct_right(input_dir,metapath):
    for package_name in (os.listdir(input_dir)):
        package_dir = os.path.join(input_dir, package_name)
        data_list = []
        for name in os.listdir(package_dir):
            if name.endswith('_portrait.png'):
                p_screenshot_path = os.path.join(package_dir, name)
                l_screenshot_path = p_screenshot_path.replace('_portrait.png','_landscape.png')
                data_list.append({
                    'images': {'portrait': p_screenshot_path, 'landscape': l_screenshot_path},
                    'defect': {'bug': False, 'type': None, 'image': None, 'bbox_2d': None}
                })    
        
        if data_list:
            append_jsonl(metapath, data_list)
    
    
def round_bbox(bbox, decimals=4):
    if bbox is None or not isinstance(bbox, list):
        return bbox
    return [round(x, decimals) if isinstance(x, (int, float)) else x for x in bbox]


def resize_images(input_dir, output_dir, ratio=2/3):
    if ratio <= 0:
        raise ValueError("Compression ratio must be greater than zero.")
    print(f"Checking input_dir: {input_dir}")
    print(f"Exists: {os.path.exists(input_dir)}, Is dir: {os.path.isdir(input_dir)}")
    for root, _, files in os.walk(input_dir):
        print(f"Processing directory: {root}")
        for filename in files:
            if filename.lower().endswith('.png'):
                input_path = os.path.join(root, filename)
                relative_path = os.path.relpath(input_path, input_dir)
                output_path = os.path.join(output_dir, relative_path)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                with Image.open(input_path) as image:
                    width = max(1, int(image.width * ratio))
                    height = max(1, int(image.height * ratio))
                    resized_img = image.resize((width, height), Image.Resampling.LANCZOS)
                    resized_img.save(output_path, optimize=True)


def get_projects(projs_dir):
    projects = []
    for project in os.listdir(projs_dir):
        project_path = os.path.join(projs_dir, project)
        if os.path.isdir(project_path):
            projects.append(project)
    return projects

def split_projects(projects, train_ratio, val_ratio, test_ratio, random_state):
    project_count = len(projects)
    train_size = int(project_count * train_ratio)
    val_size = int(project_count * val_ratio)
    test_size = project_count - train_size - val_size
    sizes = [train_size, val_size, test_size]
    ratios = [train_ratio, val_ratio, test_ratio]
    if any(ratio > 0 and size == 0 for ratio, size in zip(ratios, sizes)):
        for index, ratio in enumerate(ratios):
            if ratio > 0 and sizes[index] == 0:
                donor = max(range(3), key=lambda item: sizes[item])
                if sizes[donor] > 1:
                    sizes[donor] -= 1
                    sizes[index] = 1
        shuffled = list(projects)
        random.Random(random_state).shuffle(shuffled)
        train_end = sizes[0]
        val_end = train_end + sizes[1]
        return shuffled[:train_end], shuffled[train_end:val_end], shuffled[val_end:]
    train_projects, remaining_projects = train_test_split(
        projects,
        train_size=train_size,
        random_state=random_state,
    )
    if val_size == 0:
        return train_projects, [], remaining_projects
    if test_size == 0:
        return train_projects, remaining_projects, []
    val_projects, test_projects = train_test_split(
        remaining_projects,
        train_size=val_size,
        random_state=random_state,
    )
    return train_projects, val_projects, test_projects

def get_distributed_cnt(data):
    bug_count=0
    right_count=0
    overlap_count=0
    clip_count=0
    miss_count=0
    direction_count=0
    state_count=0
    portrait_count=0
    landscape_count=0

    for d in data:
        if d['defect']['bug']:
            bug_count += 1
            if d['defect']['type'] == 'layout-overlap':
                overlap_count += 1
            elif d['defect']['type'] == 'layout-clip':
                clip_count += 1
            elif d['defect']['type'] == 'layout-miss':
                miss_count += 1
            elif d['defect']['type'] == 'direction-mismatch':   
                direction_count += 1
            elif d['defect']['type'] == 'state-loseinput':    
                state_count += 1
                
            if d['defect']['image'] == 'portrait':
                portrait_count += 1
            elif d['defect']['image'] == 'landscape':
                landscape_count += 1
        else:
            right_count += 1
   
    print(f"bug_count: {bug_count}, right_count: {right_count}, overlap_count: {overlap_count}, clip_count: {clip_count}, miss_count: {miss_count}, direction_count: {direction_count}, state_count: {state_count}, portrait_count: {portrait_count}, landscape_count: {landscape_count}")
    
    return {
        "bug_count": bug_count,
        "right_count": right_count,
        "overlap_count": overlap_count,
        "clip_count": clip_count,
        "miss_count": miss_count,
        "direction_count": direction_count,
        "state_count": state_count,
        "portrait_count": portrait_count,
        "landscape_count": landscape_count
    }

def get_balanced_data(data):
    right_count=get_distributed_cnt(data)['right_count']
    
    balanced_data=[]
    bug_all = [x for x in data if x['defect']['bug']]
    
    state_p=[x for x in bug_all  if x['defect']['type'] =='state-loseinput' and x['defect']['image'] =='portrait']
    overlap_p=[x for x in bug_all  if x['defect']['type'] =='layout-overlap' and x['defect']['image'] =='portrait']
    clip_p=[x for x in bug_all  if x['defect']['type'] =='layout-clip' and x['defect']['image'] =='portrait']
    miss_p=[x for x in bug_all  if x['defect']['type'] =='layout-miss' and x['defect']['image'] =='portrait']
    direction_p=[x for x in bug_all  if x['defect']['type'] =='direction-mismatch' and x['defect']['image'] =='portrait']
   
    state_l=[x for x in bug_all  if x['defect']['type'] =='state-loseinput' and x['defect']['image'] =='landscape']
    overlap_l=[x for x in bug_all  if x['defect']['type'] =='layout-overlap' and x['defect']['image'] =='landscape']
    clip_l=[x for x in bug_all  if x['defect']['type'] =='layout-clip' and x['defect']['image'] =='landscape']
    miss_l=[x for x in bug_all  if x['defect']['type'] =='layout-miss' and x['defect']['image'] =='landscape']
    direction_l=[x for x in bug_all  if x['defect']['type'] =='direction-mismatch' and x['defect']['image'] =='landscape']

    state_p_cnt=len(state_p)
    overlap_p_cnt=len(overlap_p)
    clip_p_cnt=len(clip_p)
    miss_p_cnt=len(miss_p)
    direction_p_cnt=len(direction_p)
    
    state_l_cnt=len(state_l)
    overlap_l_cnt=len(overlap_l)
    clip_l_cnt=len(clip_l)
    miss_l_cnt=len(miss_l)
    direction_l_cnt=len(direction_l)
    
    half_type_cnt=min(state_p_cnt,overlap_p_cnt,clip_p_cnt,miss_p_cnt,direction_p_cnt,
                      state_l_cnt,overlap_l_cnt,clip_l_cnt,miss_l_cnt,direction_l_cnt,
                      int(right_count/10))
    half_cnt=half_type_cnt*10
    print(f"half_type_cnt: {half_type_cnt}, half_cnt: {half_cnt}")
    if half_type_cnt == 0:
        random.shuffle(data)
        return data
    
    right_samples=random.sample([x for x in data if not x['defect']['bug']],half_cnt)

    state_p_samples=random.sample([x for x in state_p if x['defect']['type'] =='state-loseinput'],half_type_cnt)
    overlap_p_samples=random.sample([x for x in overlap_p if x['defect']['type'] =='layout-overlap'],half_type_cnt)
    clip_p_samples=random.sample([x for x in clip_p if x['defect']['type'] =='layout-clip'],half_type_cnt)
    miss_p_samples=random.sample([x for x in miss_p if x['defect']['type'] =='layout-miss'],half_type_cnt)
    direction_p_samples=random.sample([x for x in direction_p if x['defect']['type'] =='direction-mismatch'],half_type_cnt)
    
    state_l_samples=random.sample([x for x in state_l if x['defect']['type'] =='state-loseinput'],half_type_cnt)
    overlap_l_samples=random.sample([x for x in overlap_l if x['defect']['type'] =='layout-overlap'],half_type_cnt)
    clip_l_samples=random.sample([x for x in clip_l if x['defect']['type'] =='layout-clip'],half_type_cnt)
    miss_l_samples=random.sample([x for x in miss_l if x['defect']['type'] =='layout-miss'],half_type_cnt)
    direction_l_samples=random.sample([x for x in direction_l if x['defect']['type'] =='direction-mismatch'],half_type_cnt)
    
    
    balanced_data.extend(right_samples)
    
    balanced_data.extend(state_p_samples)
    balanced_data.extend(overlap_p_samples)
    balanced_data.extend(clip_p_samples)
    balanced_data.extend(miss_p_samples)
    balanced_data.extend(direction_p_samples)
    
    balanced_data.extend(state_l_samples)
    balanced_data.extend(overlap_l_samples)
    balanced_data.extend(clip_l_samples)
    balanced_data.extend(miss_l_samples)
    balanced_data.extend(direction_l_samples)    
    
    balanced_portriat_cnt=sum(1 for x in balanced_data if x['defect']['image'] == 'portrait')
    balanced_landscape_cnt=sum(1 for x in balanced_data if x['defect']['image'] == 'landscape')
    print(f"balanced_portriat_cnt: {balanced_portriat_cnt}, balanced_landscape_cnt: {balanced_landscape_cnt}")
    random.shuffle(balanced_data)
    
    return balanced_data

def get_balanced_multiclass(data):
    balanced_data=[]
    bug_all = [x for x in data if x['defect']['bug']]
    
    state_p=[x for x in bug_all  if x['defect']['type'] =='state-loseinput' and x['defect']['image'] =='portrait']
    overlap_p=[x for x in bug_all  if x['defect']['type'] =='layout-overlap' and x['defect']['image'] =='portrait']
    clip_p=[x for x in bug_all  if x['defect']['type'] =='layout-clip' and x['defect']['image'] =='portrait']
    miss_p=[x for x in bug_all  if x['defect']['type'] =='layout-miss' and x['defect']['image'] =='portrait']
    direction_p=[x for x in bug_all  if x['defect']['type'] =='direction-mismatch' and x['defect']['image'] =='portrait']
   
    state_l=[x for x in bug_all  if x['defect']['type'] =='state-loseinput' and x['defect']['image'] =='landscape']
    overlap_l=[x for x in bug_all  if x['defect']['type'] =='layout-overlap' and x['defect']['image'] =='landscape']
    clip_l=[x for x in bug_all  if x['defect']['type'] =='layout-clip' and x['defect']['image'] =='landscape']
    miss_l=[x for x in bug_all  if x['defect']['type'] =='layout-miss' and x['defect']['image'] =='landscape']
    direction_l=[x for x in bug_all  if x['defect']['type'] =='direction-mismatch' and x['defect']['image'] =='landscape']

    state_p_cnt=len(state_p)
    overlap_p_cnt=len(overlap_p)
    clip_p_cnt=len(clip_p)
    miss_p_cnt=len(miss_p)
    direction_p_cnt=len(direction_p)
    
    state_l_cnt=len(state_l)
    overlap_l_cnt=len(overlap_l)
    clip_l_cnt=len(clip_l)
    miss_l_cnt=len(miss_l)
    direction_l_cnt=len(direction_l)
    
    half_type_cnt=min(state_p_cnt,overlap_p_cnt,clip_p_cnt,miss_p_cnt,direction_p_cnt,
                      state_l_cnt,overlap_l_cnt,clip_l_cnt,miss_l_cnt,direction_l_cnt,)
    bug_cnt=half_type_cnt*10
    print(f"half_type_cnt: {half_type_cnt}, bug_cnt: {bug_cnt}")
    if half_type_cnt == 0:
        random.shuffle(data)
        return data
    
    state_p_samples=random.sample([x for x in state_p if x['defect']['type'] =='state-loseinput'],half_type_cnt)
    overlap_p_samples=random.sample([x for x in overlap_p if x['defect']['type'] =='layout-overlap'],half_type_cnt)
    clip_p_samples=random.sample([x for x in clip_p if x['defect']['type'] =='layout-clip'],half_type_cnt)
    miss_p_samples=random.sample([x for x in miss_p if x['defect']['type'] =='layout-miss'],half_type_cnt)
    direction_p_samples=random.sample([x for x in direction_p if x['defect']['type'] =='direction-mismatch'],half_type_cnt)
    
    state_l_samples=random.sample([x for x in state_l if x['defect']['type'] =='state-loseinput'],half_type_cnt)
    overlap_l_samples=random.sample([x for x in overlap_l if x['defect']['type'] =='layout-overlap'],half_type_cnt)
    clip_l_samples=random.sample([x for x in clip_l if x['defect']['type'] =='layout-clip'],half_type_cnt)
    miss_l_samples=random.sample([x for x in miss_l if x['defect']['type'] =='layout-miss'],half_type_cnt)
    direction_l_samples=random.sample([x for x in direction_l if x['defect']['type'] =='direction-mismatch'],half_type_cnt)
    
    balanced_data.extend(state_p_samples)
    balanced_data.extend(overlap_p_samples)
    balanced_data.extend(clip_p_samples)
    balanced_data.extend(miss_p_samples)
    balanced_data.extend(direction_p_samples)
    
    balanced_data.extend(state_l_samples)
    balanced_data.extend(overlap_l_samples)
    balanced_data.extend(clip_l_samples)
    balanced_data.extend(miss_l_samples)
    balanced_data.extend(direction_l_samples)    
    
    balanced_portriat_cnt=sum(1 for x in balanced_data if x['defect']['image'] == 'portrait')
    balanced_landscape_cnt=sum(1 for x in balanced_data if x['defect']['image'] == 'landscape')
    print(f"balanced_portriat_cnt: {balanced_portriat_cnt}, balanced_landscape_cnt: {balanced_landscape_cnt}")
    random.shuffle(balanced_data)
    
    return balanced_data


def lf_datasets_two(bug_file, right_file, projs_dir, output_dir,
                       bug_cnt=9000,right_cnt=1900, proj_cnt=800,
                       train_ratio=0.9, val_ratio=0, test_ratio=0.1,
                       min_pixels = 4*28*28, max_pixels = 16384*28*28,
                       random_state=29,
                       save_train='lf_train_2.json',save_val='lf_val_2.json',save_test='lf_test_2.json',
):
    def convert_to_lfdata(common_data,min_pixels, max_pixels):
        lf_data=[]
        print(f"Converting common data to LlamaFactor format with min_pixels: {min_pixels}, max_pixels: {max_pixels}")
        for x in common_data:
            x['defect'].pop('type', None)
            x['defect'].pop('image', None)
            x['defect'].pop('bbox_2d', None)
            
            lf_data.append(
                {
                    'conversations':[
                        {
                            "from": "human",
                            "value": f"<image><image>{class_2_prompt}"
                        },   
                        {
                            "from": "gpt",
                            "value": '```json\n'+json.dumps(x['defect'])+'\n```'
                        } 
                    ],    
                    'images': [


                        x['images']['portrait'].replace('\\', '/'),
                        x['images']['landscape'].replace('\\', '/')
                    ]

                }
            )
        return lf_data
    random.seed(random_state)
    

    if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-6:
        raise ValueError("The train, validation, and test ratios must sum to 1.0")
    os.makedirs(output_dir, exist_ok=True)

    bug_data = read_jsonl(bug_file)
    right_data=read_jsonl(right_file)    
    all_proj = get_projects(projs_dir)
    
    if not proj_cnt:
        if len(bug_data) < bug_cnt:
            raise ValueError(f"Insufficient bug samples. Required: {bug_cnt}, available: {len(bug_data)}")
        if len(right_data) < right_cnt:
            raise ValueError(f"Insufficient normal samples. Required: {right_cnt}, available: {len(right_data)}")
        bug_data = random.sample(bug_data, bug_cnt)
        right_data = random.sample(right_data, right_cnt)
        proj_cnt = len(all_proj)
    else:
        if proj_cnt > len(all_proj):
            requested_proj_cnt = proj_cnt
            proj_cnt=len(all_proj)
            print(f"Insufficient projects. Required: {requested_proj_cnt}, available: {len(all_proj)}")
    
    select_projs = random.sample(all_proj, proj_cnt)

    all_data = bug_data + right_data
    random.shuffle(all_data)
    train_projs, val_projs, test_projs = split_projects(
        select_projs,
        train_ratio,
        val_ratio,
        test_ratio,
        random_state,
    )

    train_data = []
    val_data = []
    test_data = []

    cnt_bug_train=0
    cnt_bug_val=0
    cnt_bug_test=0
    for data in all_data:
        image_path = data['images']['portrait']
        assigned = False

        for proj in train_projs:
            if proj in image_path:
                train_data.append(data)
                if data['defect']['bug']:
                    cnt_bug_train += 1
                assigned = True
                break

        if not assigned:
            for proj in val_projs:
                if proj in image_path:
                    val_data.append(data)
                    if data['defect']['bug']:
                        cnt_bug_val += 1
                    assigned = True
                    break

        if not assigned:
            for proj in test_projs:
                if proj in image_path:
                    test_data.append(data)
                    if data['defect']['bug']:
                        cnt_bug_test += 1
                    assigned = True
                    break       
             
    train_data=get_balanced_data(train_data)   
    val_data=get_balanced_data(val_data)
    test_data=get_balanced_data(test_data)
    train_image_paths = {path for data in train_data for path in (data['images']['portrait'], data['images']['landscape'])}
    test_image_paths = {path for data in test_data for path in (data['images']['portrait'], data['images']['landscape'])}    
    has_intersection = bool(train_image_paths & test_image_paths)
    print(f"Train-test intersection: {has_intersection}")        
    assert(has_intersection==False)
    
    train_data=convert_to_lfdata(train_data, min_pixels, max_pixels)   
    val_data=convert_to_lfdata(val_data, min_pixels, max_pixels)
    test_data=convert_to_lfdata(test_data, min_pixels, max_pixels)
    
    train_file = os.path.join(output_dir, save_train)
    val_file = os.path.join(output_dir, save_val)
    test_file = os.path.join(output_dir, save_test)

    train_json=[]
    for data in train_data:
        train_json.append(data)
    val_json=[]
    for data in val_data:
        val_json.append(data)
    test_json=[]
    for data in test_data:
        test_json.append(data)

    write_json(train_file,train_json)
    write_json(val_file,val_json )
    write_json(test_file, test_json)
    stats = {
        'train_length': len(train_data),
        'val_length': len(val_data),
        'test_length': len(test_data),
        'output': {
            'train_path': train_file,
            'val_path': val_file,
            'test_path': test_file
        }
    }

    return stats


def lf_datasets_multi(bug_file, projs_dir, output_dir,
                       bug_cnt=9000, proj_cnt=800,
                       train_ratio=0.9, val_ratio=0, test_ratio=0.1,
                       min_pixels = 4*28*28, max_pixels = 16384*28*28,
                       random_state=29,
                       save_train='lf_train_multi.json',save_val = 'lf_val_multi.json', save_test = 'lf_test_multi.json',
):
    def convert_to_lfdata(common_data,min_pixels, max_pixels):
        lf_data=[]
        print(f"Converting common data to LlamaFactor format with min_pixels: {min_pixels}, max_pixels: {max_pixels}")
        for x in common_data:
            if x['defect'].get('bbox_2d'):
                x['defect'].pop('bug')
                if x['defect']['image'] == 'portrait':
                    x['defect']['bbox_2d'] = get_smart_bbox(x['defect']['bbox_2d'],x['images']['portrait'],min_pixels, max_pixels)
                elif x['defect']['image'] == 'landscape':
                    x['defect']['bbox_2d'] = get_smart_bbox(x['defect']['bbox_2d'],x['images']['landscape'],min_pixels, max_pixels)
            
            lf_data.append(
                {
                    'conversations':[
                        {
                            "from": "human",
                            "value": f"<image><image>{class_multi_prompt}"
                        },   
                        {
                            "from": "gpt",
                            "value": '```json\n'+json.dumps(x['defect'])+'\n```'
                        } 
                    ],    
                    'images': [
                        x['images']['portrait'].replace('\\', '/'),
                        x['images']['landscape'].replace('\\', '/')
                    ]
                }
            )
        return lf_data
    
    random.seed(random_state)
    if abs(train_ratio + val_ratio + test_ratio - 1.0) > 1e-6:
        raise ValueError("The train, validation, and test ratios must sum to 1.0")
    os.makedirs(output_dir, exist_ok=True)
    bug_data = read_jsonl(bug_file)
    all_proj = get_projects(projs_dir)
    
    if not proj_cnt:
        if len(bug_data) < bug_cnt:
            raise ValueError(f"Insufficient bug samples. Required: {bug_cnt}, available: {len(bug_data)}")
        bug_data = random.sample(bug_data, bug_cnt)
        proj_cnt = len(all_proj)
    else:
        if proj_cnt > len(all_proj):
            requested_proj_cnt = proj_cnt
            proj_cnt=len(all_proj)
            print(f"Insufficient projects. Required: {requested_proj_cnt}, available: {len(all_proj)}")
    
    select_projs = random.sample(all_proj, proj_cnt)
    all_data = bug_data
    random.shuffle(all_data)
    
    train_projs, val_projs, test_projs = split_projects(
        select_projs,
        train_ratio,
        val_ratio,
        test_ratio,
        random_state,
    )

    train_data = []
    val_data = []
    test_data = []

    cnt_bug_train=0
    cnt_bug_val=0
    cnt_bug_test=0
    for data in all_data:
        image_path = data['images']['portrait']
        assigned = False

        for proj in train_projs:
            if proj in image_path:
                train_data.append(data)
                if data['defect']['bug']:
                    cnt_bug_train += 1
                assigned = True
                break

        if not assigned:
            for proj in val_projs:
                if proj in image_path:
                    val_data.append(data)
                    if data['defect']['bug']:
                        cnt_bug_val += 1
                    assigned = True
                    break

        if not assigned:
            for proj in test_projs:
                if proj in image_path:
                    test_data.append(data)
                    if data['defect']['bug']:
                        cnt_bug_test += 1
                    assigned = True
                    break
             
    train_data=get_balanced_multiclass(train_data)   
    val_data=get_balanced_multiclass(val_data)
    test_data=get_balanced_multiclass(test_data)
    train_image_paths = {path for data in train_data for path in (data['images']['portrait'], data['images']['landscape'])}
    test_image_paths = {path for data in test_data for path in (data['images']['portrait'], data['images']['landscape'])}    
    has_intersection = bool(train_image_paths & test_image_paths)
    
    print(f"Train-test intersection: {has_intersection}")        
    assert(has_intersection==False)
    
    train_data=convert_to_lfdata(train_data, min_pixels, max_pixels)   
    val_data=convert_to_lfdata(val_data, min_pixels, max_pixels)
    test_data=convert_to_lfdata(test_data, min_pixels, max_pixels)
    train_file = os.path.join(output_dir, save_train)
    val_file = os.path.join(output_dir, save_val)
    test_file = os.path.join(output_dir, save_test)

    train_json=[]
    for data in train_data:
        train_json.append(data)
    val_json=[]
    for data in val_data:
        val_json.append(data)
    test_json=[]
    for data in test_data:
        test_json.append(data)

    write_json(train_file,train_json)
    write_json(val_file,val_json )
    write_json(test_file, test_json)

    stats = {
        'train_length': len(train_data),
        'val_length': len(val_data),
        'test_length': len(test_data),
        'output': {
            'train_path': train_file,
            'val_path': val_file,
            'test_path': test_file
        }
    }

    return stats


    
def ori_to_comp_jsonl(input_jsonl,output_jsonl,ratio=2/3,replace_str='output_defect',replacement_str=None):
    if ratio <= 0:
        raise ValueError("Compression ratio must be greater than zero.")
    replacement_str = replacement_str or replace_str+'_comp'
    data=read_jsonl(input_jsonl)
    new_data=[]
    for d_dict in data:
        d_dict['images']['portrait'] = d_dict['images']['portrait'].replace(replace_str,replacement_str,1)
        d_dict['images']['landscape'] = d_dict['images']['landscape'].replace(replace_str,replacement_str,1)
        bbox = d_dict['defect'].get('bbox_2d')
        if bbox:
            d_dict['defect']['bbox_2d']=[int(x*ratio) for x in bbox]
        
        new_data.append(d_dict)
    write_jsonl(output_jsonl,new_data)
    
