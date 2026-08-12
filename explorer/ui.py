import logging
import uiautomator2 as u2

class Widget:
    def __init__(self,device:u2.Device, package='', resource_id='', classname='', 
                 bounds=[], text='', hint='', content_desc='',checked='',xpath='',actions=[],
                 checkable='',naf='',index='',focusable='',focused='',password='',selected='',
                 drawing_order='',display_id=''):
        self.device=device
        self.package=package
        self.resource_id = resource_id
        self.classname = classname
        
        if bounds and len(bounds) == 4:
            x1, y1, x2, y2 = bounds
            
            left = min(x1, x2)
            top = min(y1, y2)
            right = max(x1, x2)
            bottom = max(y1, y2)

            w, h = device.window_size()

            safe_left = max(0, min(left, w))
            safe_top = max(0, min(top, h))
            safe_right = max(0, min(right, w))
            safe_bottom = max(0, min(bottom, h))

            self.bounds = [safe_left, safe_top, safe_right, safe_bottom]
        else:
            logging.warning(f"Widget bounds format error: {bounds}")
            self.bounds = bounds  
            
        self.text = text 
        self.hint = hint
        self.content_desc=content_desc 
        self.checked=checked
        self.actions=actions 
        self.selector=self.get_selector()  
        self.xpath=xpath

        self.checkable=checkable
        self.naf = naf
        self.index   =index
        self.focusable = focusable
        self.focused =   focused   
        self.password = password
        self.selected =  selected
        self.drawing_order =drawing_order
        self.display_id = display_id



    def get_selector(self) -> u2.UiObject:
        selector_kwargs = {}
        if self.resource_id:
            selector_kwargs['resourceId'] = self.resource_id
        if self.classname:
            selector_kwargs['className'] = self.classname
        if self.text:
            selector_kwargs['text'] = self.text
        if self.content_desc:
            selector_kwargs["description"] = self.content_desc 
        if not selector_kwargs:
            raise ValueError("Widget must have at least one identifier: resource_id, classname, text or hint.")

        return self.device(**selector_kwargs)
    
    def __repr__(self):
        return f"Widget(package={self.package}, resource_id={self.resource_id}, classname={self.classname}, bounds={self.bounds}, \
            text={self.text}, hint={self.hint}, content_desc={self.content_desc}, checked={self.checked}, actions={self.actions}, \
            checkable={self.checkable},naf={self.naf},index={self.index},focusable={self.focusable},focused={self.focused},\
            password={self.password},selected={self.selected},drawing_order={self.drawing_order},display_id={self.display_id}, \
            xpath={self.xpath} )"

    def to_dict(self):
        return {
            'package': self.package,
            'resource_id': self.resource_id,
            'classname': self.classname,
            'bounds': self.bounds,
            'text': self.text,
            'hint': self.hint,
            'content_desc': self.content_desc,
            'checked': self.checked,
            'checkable':self.checkable,
            'naf' : self.naf,
            'index'   :self.index,
            'focusable' : self.focusable,
            'focused' :   self.focused   ,
            'password' : self.password,
            'selected' :  self.selected,
            'drawing_order' :self.drawing_order,
            'display_id' : self.display_id,
            'actions': self.actions, 
            'xpath': self.xpath,

        }
        
