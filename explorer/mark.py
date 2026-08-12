import logging
import math
from typing import Dict, List, Union
from PIL import Image, ImageDraw, ImageFont
import os

from explorer.action import Action
from utils  import get_image_size, get_size,parse_bounds


def draw_arrow(draw, start, end, color, width=3, arrow_size=20):
    draw.line([start, end], fill=color, width=width)
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    left_angle = angle + math.pi / 6
    right_angle = angle - math.pi / 6
    left_point = (
        end[0] - arrow_size * math.cos(left_angle),
        end[1] - arrow_size * math.sin(left_angle)
    )
    right_point = (
        end[0] - arrow_size * math.cos(right_angle),
        end[1] - arrow_size * math.sin(right_angle)
    )
    draw.line([end, left_point], fill=color, width=width)
    draw.line([end, right_point], fill=color, width=width)

def get_markinfo(bounds,message='',color='red',shape='rectangle'):
    return {'bounds':bounds,'message':message,'color':color,'shape':shape}


def mark_shape(input_path, output_path=None, mark_list: Union[List[Dict], Dict]=[]):
    image = Image.open(input_path)
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("simhei.ttf", 32)  
    except IOError:
        font = ImageFont.load_default() 

    if type( mark_list ) == dict:
        mark_list = [mark_list]
    if len(mark_list) == 0:
        return None
    
    for m in mark_list:
        x1, y1, x2, y2 = m['bounds']
        left = min(x1, x2)
        top = min(y1, y2)
        right = max(x1, x2)
        bottom = max(y1, y2)
        
        message = m['message']
        color=m['color']
        if m['shape']=='point':
            radius = 6
            midx=(left+right)//2
            midy=(top+bottom)//2

            draw.ellipse((midx - radius, midy - radius, midx + radius, midy + radius), fill=color, )
            draw.point((midx, midy), fill=color)
            draw.text((midx, midy + 10), message, fill=color, font=font)
        elif m['shape']=='rectangle':
            if left == right and top == bottom:
                r = 10
                draw.ellipse([left-r, top-r, right+r, bottom+r], outline=color, width=3)
            else:
                draw.rectangle([left, top, right, bottom], outline=color, width=3)
            draw.text((left, top - 30), message, fill=color, font=font)
        elif m['shape']=='line': 
            draw_arrow(draw, (left, top), (right, bottom), color)
            draw.text(( (left+right)/2, (top+ bottom)/2 ), message, fill=color, font=font)
        elif m['shape']=='text':
            draw.text(( (left+right)/2, (top+ bottom)/2 ), message, fill=color, font=font)
        else:
            print('mark shape error')
            return None
        
    if output_path:
        if os.path.dirname(output_path) :  
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
        image.save(output_path)
        
    return image

def mark_action(action:Action,input_path:str,output_path:str):
    mark_l=[]
    color='green'
    mark_info=None
    if action:
        if action == 'screenshot':
            w,h=get_image_size(input_path) 
            action_b=[0,0,w,h] 
            mark_info=get_markinfo(action_b,action,color,'point')
            
        elif action.action_type in ['main','home', 'back'] or action.action_type .__contains__('rotate'):
            w,h=get_image_size(input_path) 
            action_b=[0,0,w,h] 
            mark_info=get_markinfo(action_b,action.action_type,color,'point')
        elif action.action_type in  ['click', 'long_click', 'type']:
            if action.widget:
                action_b=action.widget.bounds
            elif action.position:
                action_b=[action.position[0],action.position[1],action.position[0],action.position[1]]
            else:
                logging.info('Error: no position')
            mark_info=get_markinfo(action_b,action.action_type,color,'point')
        elif action.action_type in  ['scroll_up', 'scroll_down']:
            if action.widget:
                action_b=action.widget.bounds
            elif action.position:
                action_b=[action.position[0],action.position[1],action.position[0],action.position[1]]
            else:
                logging.info('Error: no position')
            mark_info=get_markinfo(action_b,action.action_type,color,'point')
        else:
            logging.info('Error: error action')
            logging.info(action)
            
        if mark_info:
            mark_l.append(mark_info)
    else:
        logging.info(f'No action executed in SRS, no mark added.')

    mark_shape(input_path,output_path, mark_l)
    
