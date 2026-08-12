from typing import Dict, List

from utils.file_utils import encode_image

class Messager:
    def __init__(self) -> None:
        self.messages=[]

    def clear_message(self):
        self.messages=[]

    def add_message(self,messages:List[Dict[str, str]]):
        if type(messages) == dict:
            messages = [messages]
        self.messages.extend(messages)

    def add_user(self,text):
        m = {"role": "user","content": text }
        self.add_message(m)
        
    def add_system(self,text):
        m = {"role": "system","content": text }
        self.add_message(m)

    def add_assistant(self,text):
        m = {"role": "assistant","content": text }
        self.add_message(m)

    def min_message(self,cnt=8):
        if len(self.messages)>cnt:
            self.messages=self.messages[-cnt:]

    def print_message(self):
        for m in self.messages:
            print(m)

class VLMMessager(Messager): 
    def __init__(self) -> None:
        super().__init__()
    

    def construct_prompt(self,imgpaths:List[str],text:str,min_pixels=4*28*28,max_pixels=16384*28*28,detail:str='high'):
        img_urls=[]
        for imgpath in imgpaths:
            img_base64 = encode_image(imgpath)
            img_urls.append({   "type": "image_url",
                                "min_pixels": min_pixels,
                                "max_pixels": max_pixels,
                                "image_url": {
                                    "url":  f"data:image/png;base64,{img_base64}",

                                }})
            
        message=[            
        {
            "role": "user",
            "content": [{"type": "text", "text": text}],
        }
        ]
        message[0]["content"].extend(img_urls)
        
        return message

    
    def add_user(self,imgpaths:List[str],text:str,detail:str='high'):
        message = self.construct_prompt(imgpaths,text,detail)
        self.add_message(message)

    def reset_prompt(self,system_text:str,user_text:str,imgpaths:List[str],detail:str='high'):
        system_m = [{"role": "system","content": system_text }]
        user_m=self.construct_prompt(imgpaths,user_text,detail)
        return system_m.extend(user_m)