import json
import logging
from time import sleep
import uiautomator2 as u2

from utils.apk_util import adb_start
from .ui import Widget
from utils import get_hashes
ACTION_SPACE = [
    'click', 
    'long_click', 
    'type', 
    'scroll_up',
    'scroll_down', 
    'scroll_left', 
    'scroll_right', 
    
    'main', 

    'home', 
    'back',
    'finished',

    'rotate_left',
    'rotate_right',
    'rotate_upsidedown',
    'rotate_natural'
]

class Action:
    def __init__(self, action_type, widget:Widget=None, position=None, input='default_input',
                 package=None, act_name=None):
        if action_type in ['click','long_click','type'] and not position and not widget:
            raise ValueError("need position/widget")
        elif action_type.__contains__('scroll') and not widget:
            raise ValueError("need widget")
        elif action_type.lower().__contains__('activity') and not package and not act_name:
            raise ValueError("need package / act_name")
        elif action_type.lower().__contains__('main') and not package:
            raise ValueError("need package")
        
        self.action_type = action_type
        self.widget = widget
        self.position = position 
        self.input = input
        self.package = package
        self.act_name = act_name
        self.id = self.generate_id() 

   
    def generate_id(self):
        data={
            'action_type': self.action_type, 
            'widget': self.widget.to_dict() if self.widget else None, 
            'position': self.position, 
            'input': self.input,
            'package':self.package,
            'act_name':self.act_name
            }
        return get_hashes(json.dumps(data, sort_keys=True, ensure_ascii=False))


    def execute(self,d:u2.Device):

        if self.action_type == 'click':
            if self.widget:
                x1,y1,x2,y2 = self.widget.bounds
                cx,cy = (x1+x2)//2, (y1+y2)//2
                d.click(cx, cy)
            elif self.position: 
                d.click(self.position)
            else:
                logging.info("Error: need position / widget。")
                return False
            
        elif self.action_type == 'long_click':
            if self.widget:
                x1,y1,x2,y2 = self.widget.bounds
                cx,cy = (x1+x2)//2, (y1+y2)//2
                d.long_click(cx, cy)
            elif self.position: 
                d.long_click(self.position)
            else:
                logging.info("Error: need position / widget。")
                return False
            
        elif self.action_type == 'type':
            if self.widget:
                safe_text = self.input.replace(" ", "%s")
                d.shell(f'input text "{safe_text}"')
                d.press("back") 

            elif self.position: 
                d.click(self.position)
                d.send_keys(self.input,clear=True)
                d.press("back") 
            else:
                logging.info("Error: need position / widget。")
                return False
            
        elif self.action_type == 'scroll_up':
            if self.widget:
                x1, y1, x2, y2 = self.widget.bounds
                start_x = (x1 + x2) // 2
                start_y = y2 - (y2-y1)//4  
                end_x = start_x
                end_y = y1 + (y2-y1)//4 
                d.swipe(start_x, start_y, end_x, end_y, 0.2)
            else:
                logging.info("Error: need widget")
                return False
        elif self.action_type == 'scroll_down':
            if self.widget:
                x1, y1, x2, y2 = self.widget.bounds
                start_x = (x1 + x2) // 2
                start_y = y1 + (y2-y1)//4
                end_x = start_x
                end_y = y2 - (y2-y1)//4
                d.swipe(start_x, start_y, end_x, end_y, 0.2)
            else:
                logging.info("Error: need widget")
                return False
        elif self.action_type == 'scroll_left':
            if self.widget:
                x1, y1, x2, y2 = self.widget.bounds
                start_y = (y1 + y2) // 2
                start_x = x2 - (x2-x1)//4
                end_y = start_y
                end_x = x1 + (x2-x1)//4
                d.swipe(start_x, start_y, end_x, end_y, 0.2)

            else:
                logging.info("Error: need widget")
                return False
        elif self.action_type == 'scroll_right':
            if self.widget:
                x1, y1, x2, y2 = self.widget.bounds
                start_y = (y1 + y2) // 2
                start_x = x1 + (x2-x1)//4
                end_y = start_y
                end_x = x2 - (x2-x1)//4
                d.swipe(start_x, start_y, end_x, end_y, 0.2)

            else:
                logging.info("Error: need widget")
                return False
            
        elif self.action_type == 'home':
            d.press("home")
        elif self.action_type == 'back':
            d.press("back")
        elif self.action_type == 'finished':
            logging.info('finished') 

        elif self.action_type=='main':
            d.app_start(self.package)

        elif self.action_type.lower().__contains__('activity'):
            adb_start(self.package, self.act_name)

        elif self.action_type == 'rotate_left':
            d.set_orientation('l')
        elif self.action_type == 'rotate_right':
            d.set_orientation("r")
        elif self.action_type == 'rotate_upsidedown':
            d.set_orientation("u")
        elif self.action_type == 'rotate_natural':
            d.set_orientation("n")
        
        sleep(2)  
        logging.info(f"Executed action: {self}")
        return True

        
        
    def __repr__(self):
        return f"Action(action_type={self.action_type}, widget={self.widget}), position={self.position}, input={self.input}"
    def to_dict(self): 
        return {'id':self.id,'action_type': self.action_type, 
                'widget': self.widget.to_dict() if self.widget else None, 'position': self.position if self.position else None, 
                'input': self.input if self.input else None,}
