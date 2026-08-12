from datetime import datetime
import hashlib
import json
import logging
import os
import time
import uiautomator2 as u2
import xml.etree.ElementTree as ET

from .ui import Widget
from utils import save_hierachy, save_screenshot,get_hashes,get_curtime,parse_bounds
from .action import Action


class State:
    def __init__(self, device:u2.Device,out_dir='out_curstate',save_state=True) -> None:
        self.device=device
        self.id, self.ui_info=self.get_ui_info()
        if self.id is None or self.ui_info is None:
            self.activity_name = None
            self.screenshot_path = None
            self.hierachy_path = None
        else:
            self.activity_name = self.ui_info['state_dict']['activity']
            if save_state:
                self.screenshot_path, self.hierachy_path= self.save_curstate(out_dir)
            else:
                self.screenshot_path = None
                self.hierachy_path = None
    
    def generate_id(self):
        data= {
            'ui_info': {

                'interactive_widgets': [w.to_dict() for w in self.ui_info.get('interactive_widgets', [])]
            },
        }
        return get_hashes(json.dumps(data, sort_keys=True, ensure_ascii=False))

    def save_curstate(self, out_dir):
        timestamp = get_curtime()
        screenshot_path=save_screenshot(f"{out_dir}/{timestamp}_{self.activity_name}_{self.id}.png", self.device)
        hierachy_path=save_hierachy(f"{out_dir}/{timestamp}_{self.activity_name}_{self.id}.xml", self.device.dump_hierarchy())
        return screenshot_path,hierachy_path
    
    def get_candidate_actions(self) -> list[Action]:
        actions = []
        if self.ui_info:
            for widget in self.ui_info.get('interactive_widgets', []):
                for action_type in widget.actions:
                    if action_type in ['type']:
                        input_val = "default_input" 
                        action = Action(action_type=action_type, widget=widget, input=input_val)
                    elif action_type in ['click', 'long_click', 'scroll_up', 'scroll_down']:
                        action = Action(action_type=action_type, widget=widget)
                    actions.append(action)
                
        if not actions:
            actions.append(Action(action_type='main',package=self.ui_info['state_dict']['package']))
            actions.append(Action(action_type='back')) 
            
        return actions


    def get_ui_info(self) -> dict:
        xml_str = None
        for _ in range(5):
            try:
                xml_str = self.device.dump_hierarchy()
                if xml_str and "<hierarchy" in xml_str:
                    try:
                        root = ET.fromstring(xml_str)
                        if len(list(root)) > 0:
                            break
                    except:
                        pass
            except Exception:
                pass
            time.sleep(0.5)

        if not xml_str:
            return None, None

        self._cached_xml = xml_str
        cur_package = self.device.app_current().get('package') 
        cur_activity=self.device.app_current().get('activity')
        logging.info(f'cur_package:{cur_package}')
        logging.info(f'cur_activity:{cur_activity}')

        def get_interactive_widgets():
            interactive_elements = self.device.xpath('//*[@clickable="true" or @long-clickable="true" or @checkable="true" or @scrollable="true"]').all()
            interactive_widgets = []
            state_widgets=[]

            for element in interactive_elements:
                if element.attrib.get('enabled', 'false') == 'false':
                    continue
                if element.attrib.get('visible-to-user', 'true') == 'false':
                    continue

                resource_id=element.attrib.get('resource-id', '')
                classname=element.info.get('className', '')
                bounds=parse_bounds(element.attrib.get('bounds', ''))
                hint=element.attrib.get('hint', '')
                text=element.attrib.get('text', '')
                content_desc=element.attrib.get('content-desc','')
                checked=element.attrib.get('checked','')
                checkable=element.attrib.get('checkable', '')
                focusable = element.attrib.get('focusable', '')
                focused = element.attrib.get('focused', '')        
                password = element.attrib.get('password', '')
                selected = element.attrib.get('selected', '')   
                index = element.attrib.get('index', '')     
                naf = element.attrib.get('NAF', '')  
                drawing_order = element.attrib.get('drawing-order', '')
                display_id = element.attrib.get('display-id', '')
                        
                actions = []

                if element.attrib.get('clickable', 'false') == 'true':
                    actions.append('click')
                if element.attrib.get('checkable', 'false') == 'true':
                    if element.attrib.get('clickable', 'false') == 'false':
                        logging.info(f"Warning: {element.attrib.get('resource-id', '')} is checkable but not clickable.")
                if element.attrib.get('long-clickable', 'false') == 'true':
                    actions.append('long_click')
                if element.attrib.get('scrollable', 'false') == 'true':
                    actions.append('scroll_up')
                    actions.append('scroll_down')
                if classname == 'android.widget.EditText':
                    actions.append('type')
                if classname == 'android.widget.ImageView' or classname == 'android.widget.VideoView':
                    pass

                if actions: 
                    xml_node = element.elem

                    if not text:
                        for child in xml_node.iter():
                            if child is not xml_node:
                                child_text = child.attrib.get("text")
                                if child_text:
                                    text = child_text
                                    break

                    if not hint:
                        for child in xml_node.iter():
                            if child is not xml_node:
                                child_hint = child.attrib.get("hint")
                                if child_hint:
                                    hint = child_hint
                                    break

                    if not content_desc:
                        for child in xml_node.iter():
                            if child is not xml_node:
                                child_desc = child.attrib.get("content-desc")
                                if child_desc:
                                    content_desc = child_desc
                                    break


                xpath = self.element_to_xpath(element)
                widget_info=Widget(device=self.device,package=cur_package,resource_id=resource_id,classname=classname,
                        bounds=bounds,hint=hint,text=text,content_desc=content_desc,checked=checked,actions=actions,xpath=xpath,
                        checkable=checkable,naf=naf,index=index,focusable=focusable,focused=focused,password=password,selected=selected,
                        drawing_order=drawing_order,display_id=display_id)
                interactive_widgets.append(widget_info)
            return interactive_widgets
        
        def get_all_widgets():
            all_elements = self.device.xpath('//*').all()
            visible_widgets = []
            for element in all_elements:
                if element.attrib.get('package', '')=='com.android.systemui': 
                    continue
                if element.attrib.get('visible-to-user', 'true') == 'false':
                    continue
                widget_data = dict(element.attrib)
                visible_widgets.append(widget_data)        
            return visible_widgets   
                
        all_widgets= get_all_widgets()
        state_dict={
            'package': cur_package,
            'activity': cur_activity,
            'widgets': all_widgets
        }
        state_text = json.dumps(state_dict)
        state_id= get_hashes(state_text)
        
        interactive_widgets= get_interactive_widgets()    

        ui_info = {
            'state_dict': state_dict,
            'interactive_widgets': interactive_widgets,
        }

        return state_id, ui_info    
    

    def element_to_xpath(self, element) -> str:
        try:
            node = element.elem 
            xpath_segments = []
            
            while node is not None:
                parent = node.getparent()
                
                if parent is None:
                    xpath_segments.insert(0, node.tag)
                    break
                
                index = 1
                for sibling in node.itersiblings(preceding=True):
                    if sibling.tag == node.tag:
                        index += 1
                
                xpath_segments.insert(0, f"{node.tag}[{index}]")
                
                node = parent
            
            return "/" + "/".join(xpath_segments)
            
        except Exception as e:
            logging.error(f"Generate XPath failed: {e}")
            return ""


    def __repr__(self):
        return f"State(id={self.id}, ui_info={self.ui_info}, activity_name={self.activity_name}, \
            screenshot_path={self.screenshot_path}, hierachy_path={self.hierachy_path})"
    
    def to_dict(self):
        return {
            'state_id': self.id,
            'ui_info': {            
                'state_dict': self.ui_info.get('state_dict', {}), 
                'interactive_widgets': [w.to_dict() for w in self.ui_info.get('interactive_widgets', [])]
            },
            'screenshot_path': self.screenshot_path,
            'hierachy_path': self.hierachy_path,
        }