import logging
import random
import uiautomator2 as u2
from .state import State
from .action import Action
from .utg import UIGraph, UIStateNode
def click_permision(device:u2.Device):
    state=  State(device,'',False)      
    for a in state.get_candidate_actions():
        if a.action_type=='click' and a.widget and a.widget.text in ['Allow','While using the app']:
            logging.info(f'Click permission {a.widget.text}')
            a.execute(device)
            return state,a
    return None

def click_closeapp(device:u2.Device):
    state=  State(device,'',False)      
    for a in state.get_candidate_actions():
        if a.action_type=='click' and a.widget and a.widget.resource_id== 'android:id/aerr_close' :
            logging.info(f'Click Close app {a.widget.resource_id}')
            a.execute(device)
            return state,a
    return None

class Explorer:
    def __init__(self, device:u2.Device, utg:UIGraph, out_dir='out') -> None:
        self.device = device
        self.out_dir = out_dir
        self.utg = utg
        self.pairs = []

    def explore(self, state: State, **kwargs) -> Action:
        raise NotImplementedError("Subclasses should implement this method.")
    

class RandomExplorer(Explorer):
    def __init__(self, device:u2.Device, utg:UIGraph, out_dir='out_heuristic') -> None:
        super().__init__( device, utg, out_dir)
    

    def explore(self,state:State):
        candidate_actions = state.get_candidate_actions()
        if not candidate_actions:
            logging.info(f"No valid actions available for state {state.id}")
            return None
        
        action = random.choice(candidate_actions)
        flag=action.execute(self.device) 
        if flag:
            logging.info("action executed successfully")
        else:
            logging.info("action execution failed")

        return action

    


class HeuristicExplorer(Explorer):
    def __init__(self, device:u2.Device, utg:UIGraph, out_dir='out_heuristic') -> None:
        super().__init__( device, utg, out_dir)
    

    def explore(self,state:State):
        candidate_actions = state.get_candidate_actions()
        if not candidate_actions:
            logging.info(f"No valid actions available for state {state.id}")
            return None
        






                
        action = random.choice(candidate_actions)
        flag=action.execute(self.device)  
        if flag:
            logging.info("action executed successfully")
        else:
            logging.info("action execution failed")



        
        return action

    def reward(self,):

        return 0
    
    
