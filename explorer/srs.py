from __future__ import annotations
import json
import logging
from typing import List,Union
import uiautomator2 as u2
import os
from graphviz import Digraph

from explorer import State,click_closeapp,click_permision
from explorer.mark import get_markinfo, mark_action, mark_shape
from utils import get_hashes, save_screenshot,get_curtime, get_image_size, save_hierachy
from .action import Action
from .utg import ActivityNode, UIGraph, UIStateEdge, UIStateNode


class SRS:
    def __init__(self, state: UIStateNode, srs: List[Union[UIStateEdge, Action, str]],srs_type='srs'):
        self.srs_type=srs_type
        self.state = state 
        self.orientation = 'p' 
        self.p_state = None 
        self.l_state = None 
        self.p2_state = None
        self.plan_srs = srs
        self.actual_srs=[] 
        self.execute=False 
        self.id = self.generate_id() 
        
    def generate_id(self):
        data={
            'state_portrait': self.state.to_dict(),
            'srs': [
                edge.to_dict() if hasattr(edge, 'to_dict') else edge
                for edge in self.plan_srs
            ],
        }
        return get_hashes(json.dumps(data, sort_keys=True, ensure_ascii=False))

    def to_dict(self):
        serializable_actual_srs = []
        for item in self.actual_srs:
            if isinstance(item, tuple) and len(item) == 2:
                s, a = item
                
                if hasattr(s, 'to_dict'):
                    s_data = s.to_dict()
                else:
                    s_data = str(s)
                    
                if hasattr(a, 'to_dict'):
                    a_data = a.to_dict()
                else:
                    a_data = str(a) 
                    
                serializable_actual_srs.append((s_data, a_data))
            else:
                serializable_actual_srs.append(str(item))

        return {
            'srs_type':self.srs_type,
            'id': self.id,
            'state': self.state.to_dict(),
            'p_state': self.p_state.to_dict() if self.p_state else None, 
            'l_state': self.l_state.to_dict() if self.l_state else None,
            'p2_state': self.p2_state.to_dict() if self.p2_state else None,
            'actual_srs': serializable_actual_srs, 
            'plan_srs': [
                edge.to_dict() if hasattr(edge, 'to_dict') else edge
                for edge in self.plan_srs
            ],
            'execute': self.execute,
        }

    def rematch_action(self,device:u2.Device,action:Action,out_dir):
        def match_once():  
            if action.action_type in ['home','back','main'] or action.action_type.lower().__contains__('activity'):
                logging.info(f"Directly returning non-widget action: {action.action_type}")    
                return action
            
            logging.info(f"Trying to match action: {action}")
            maybe_actions=[]
            for a in candidate_actions:

                if not action.widget:
                    logging.info("unexpected action: has no widget but not a global type")
                    continue
                
                if action.widget.resource_id and a.widget.resource_id == action.widget.resource_id:
                    new_action=Action(
                        action_type=action.action_type,
                        widget=a.widget,
                    )
                    logging.info(f"Success Rematch action by resource-id: {action.widget.resource_id}")
                    return new_action
                
                elif action.widget.classname and a.widget.classname == action.widget.classname \
                    and action.widget.package and a.widget.package == action.widget.package:
                    if action.widget.text and a.widget.text == action.widget.text :
                        new_action=Action(
                            action_type=action.action_type,
                            widget=a.widget,
                        )
                        logging.info(f"Success Rematch action by classname + text: action.widget.classname={action.widget.classname}, action.widget.text={action.widget.text}, action.widget.hint={action.widget.hint}, action.widget.content_desc={action.widget.content_desc}")
                        return new_action
                    elif action.widget.hint and a.widget.hint == action.widget.hint:
                        new_action=Action(
                            action_type=action.action_type,
                            widget=a.widget,
                        )
                        logging.info(f"Success Rematch action by classname + hint: action.widget.classname={action.widget.classname}, action.widget.text={action.widget.text}, action.widget.hint={action.widget.hint}, action.widget.content_desc={action.widget.content_desc}")
                        return new_action
                    elif action.widget.content_desc and a.widget.content_desc == action.widget.content_desc:
                        new_action=Action(
                            action_type=action.action_type,
                            widget=a.widget,
                        )
                        logging.info(f"Success Rematch action by classname + content_desc: action.widget.classname={action.widget.classname}, action.widget.text={action.widget.text}, action.widget.hint={action.widget.hint}, action.widget.content_desc={action.widget.content_desc}")
                        return new_action
                    
                    elif action.widget.text==a.widget.text=='' \
                        and action.widget.hint==a.widget.hint=='' \
                        and action.widget.content_desc==a.widget.content_desc=='' \
                        and action.widget.naf == a.widget.naf \
                        and action.widget.index==a.widget.index \
                        and action.widget.focusable==a.widget.focusable \
                        and action.widget.focused==a.widget.focused \
                        and action.widget.checked==a.widget.checked \
                        and action.widget.actions==a.widget.actions \
                        and action.widget.checkable==a.widget.checkable \
                        and action.widget.package==a.widget.package \
                        and action.widget.password==a.widget.password \
                        and action.widget.selected==a.widget.selected \
                        and action.widget.drawing_order==a.widget.drawing_order \
                        and action.widget.display_id==a.widget.display_id:
                        
                        maybe_actions.append(Action(
                            action_type=action.action_type,
                            widget=a.widget,
                        ))
                       
                        
            logging.info(f"Rematch by all attrib, found {len(maybe_actions)} candidates") 
            if len(maybe_actions)==1:  
                logging.info(f"Success Rematch one action by all attribs exclude text,hint,content_desc") 
                return maybe_actions[0]   
            
            elif len(maybe_actions) > 1:
                def get_xpath_tail(xpath_str, n=2):
                    if not xpath_str:
                        return ""
                    return "/".join(xpath_str.split("/")[-n:])
                
                target_xpath = action.widget.xpath
                tail=2
                target_tail = get_xpath_tail(target_xpath,tail)
                
                for candidate in maybe_actions:
                    candidate_xpath = candidate.widget.xpath
                    
                    if target_xpath and candidate_xpath == target_xpath:
                        logging.info(f"Success Rematch by full XPath: {candidate_xpath}")
                        return candidate
                    
                    if target_tail and get_xpath_tail(candidate_xpath) == target_tail:
                        logging.info(f"Success Rematch by suffix-{tail} XPath: {target_tail}, full XPath: {candidate_xpath}")
                        return candidate
                    
                logging.info("XPath filtering in maybe_actions failed (no exact XPath match inside candidates).")            
            
            logging.info("No match found")
            return None
                
     

        logging.info("Trying first match…")
        new_state=State(device,out_dir=os.path.join(out_dir,'index',f"{self.srs_type}_{self.id}"),save_state=True)
        candidate_actions=new_state.get_candidate_actions()
        logging.info(f"get_candidate_actions: {new_state.ui_info.get('interactive_widgets', [])}")

        new_action = match_once()
        if new_action:
            self.actual_srs.append((new_state,new_action))
            return new_action

        if self.orientation=='p':
            logging.info("Match failed. Portrait, no scrolling to search.")
            return None
        
        
        logging.info("First match failed. Start scrolling down to search…")         
        scroll_cnt=5 
        for _ in range(scroll_cnt):

            last_state=new_state
            scrolled = False
            for a in candidate_actions:
                if a.action_type=='scroll_up':
                    scroll_action=Action(
                            action_type=a.action_type,
                            widget=a.widget,
                        )
                    scroll_action.execute(device)
                    self.actual_srs.append((last_state,scroll_action))
                    scrolled = True
                    
                    ac=click_closeapp(device)
                    ap=click_permision(device)
                    
                    new_state=State(device,out_dir=os.path.join(out_dir,'index',f"{self.srs_type}_{self.id}"),save_state=True)
                    if last_state.id==new_state.id: 
                        logging.info(f"Scroll to bottom. Failed to Match for action {action}")
                        return None
                    else:
                        break
                    
            if not scrolled:
                logging.info("No scrollable widget found. Stop matching.")
                break        
                    
            candidate_actions=new_state.get_candidate_actions()
            logging.info(f"get_candidate_actions: {new_state.ui_info.get('interactive_widgets', [])}")
            new_action = match_once()
            if new_action:
                self.actual_srs.append((new_state,new_action))
                return new_action
        
        logging.info(f"Failed to Match for action {action}")
        return None
    
    def execute_srs(self, device: u2.Device, out_dir='todetect_pairs'):
        flag=True
        for index, step in enumerate(self.plan_srs,1):
            ac=click_closeapp(device)
            ap=click_permision(device)
            action = None
            logging.info(f"Executing step {index}/{len(self.plan_srs)}: {step}")
            logging.info(f"current activity: {device.app_current().get('activity')}") 
            if isinstance(step, Action):
                logging.info(f"Executing rotation action: {step.action_type}")
                new_state=State(device,out_dir=os.path.join(out_dir,'index',f"{self.srs_type}_{self.id}"),save_state=True)
                before=device.orientation
                action=step
                self.actual_srs.append((new_state,action))
                action.execute(device)
                after=device.orientation
                self.orientation=after
                if before == after:
                    logging.info('ERROR: orientation not change')
                    flag= False
                    break
            elif isinstance(step, UIStateEdge):
                
                action=self.rematch_action(device,step.action,out_dir)
                if not action:
                    logging.info("Error: cannot rematch action, stop executing srs")
                    flag= False
                    break
                
                action.execute(device)
                if self.orientation == 'l' and device.orientation == 'p':
                    rotate_action=Action('rotate_left')
                    new_state=State(device,out_dir=os.path.join(out_dir,'index',f"{self.srs_type}_{self.id}"),save_state=True)
                    self.actual_srs.append((new_state,rotate_action))
                    logging.info(f"Re-rotate to landscape after action {action.action_type if hasattr(action, 'action_type') else action} execution")
                    rotate_action.execute(device)
                
            elif step == 'screenshot': 
                logging.info("Executing taking screenshot and saving hierarchy...")
                new_state=State(device,out_dir=os.path.join(out_dir,'index',f"{self.srs_type}_{self.id}"),save_state=True)
                self.actual_srs.append((new_state,'screenshot'))
                
                start_path=os.path.join(out_dir,f"{self.srs_type}_{self.id}_start")
                save_screenshot(start_path+'.png', device)
                save_hierachy(start_path+'.xml', device.dump_hierarchy())
                state_p=State(device,out_dir=os.path.join(out_dir,'index',f"{self.srs_type}_{self.id}"),save_state=False)
                self.p_state=UIStateNode(state_p, ActivityNode(device.app_current().get('activity')))
                self.p_state.state.screenshot_path = start_path+'.png'
                self.p_state.state.hierachy_path = start_path+'.xml'
     
            else:
                logging.info(f"Unsupported type: {type(step)} in srs")
        
        for s,a in self.actual_srs:
            if a=='screenshot':
                mark_action(a,s.screenshot_path,s.screenshot_path.replace('.png','_screenshot.png'))
            else:
                mark_action(a,s.screenshot_path,s.screenshot_path.replace('.png','_mark.png'))

        if not flag:
            logging.info(f"Fail to execute SRS, srs_type = {self.srs_type}\n")
            return False
        
        end_path=os.path.join(out_dir,f"{self.srs_type}_{self.id}_end")
        save_screenshot(end_path+'.png', device)
        save_hierachy(end_path+'.xml', device.dump_hierarchy())
        state_l=State(device,out_dir=os.path.join(out_dir,'index',self.id),save_state=False)
        self.l_state=UIStateNode(state_l, ActivityNode(device.app_current().get('activity')))

        self.l_state.state.screenshot_path = end_path+'.png'
        self.l_state.state.hierachy_path = end_path+'.xml'

        rotate_back_action = Action('rotate_natural')
        rotate_back_state = State(device,out_dir=os.path.join(out_dir,'index',f"{self.srs_type}_{self.id}"),save_state=True)
        self.actual_srs.append((rotate_back_state, rotate_back_action))
        rotate_back_action.execute(device)
        self.orientation = device.orientation

        p2_path=os.path.join(out_dir,f"{self.srs_type}_{self.id}_p2")
        save_screenshot(p2_path+'.png', device)
        save_hierachy(p2_path+'.xml', device.dump_hierarchy())
        state_p2=State(device,out_dir=os.path.join(out_dir,'index',f"{self.id}_p2"),save_state=False)
        self.p2_state=UIStateNode(state_p2, ActivityNode(device.app_current().get('activity')))
        self.p2_state.state.screenshot_path = p2_path+'.png'
        self.p2_state.state.hierachy_path = p2_path+'.xml'

        logging.info(f"Succeed to execute SRS, srs_type = {self.srs_type}\n")
        return True

    @staticmethod
    def get_special_srs(utg: UIGraph, state: UIStateNode) -> List[SRS]:
        srses= [SRS(state, [],'state')]

        srses=SRS.rotated_srses(srses) 
        srses=SRS.integrated_srses(srses, utg)  
        return srses

    @staticmethod
    def get_new_srses(utg: UIGraph, edge: UIStateEdge) -> List[SRS]:
        cycles=SRS.get_new_cycles(utg, edge)
        srses=SRS.extract_srses(cycles,utg.package)
        srses=SRS.rotated_srses(srses)  
        srses=SRS.integrated_srses(srses, utg)  
        return srses

    @staticmethod
    def integrated_srses(srses:list[SRS],utg:UIGraph) -> List[SRS]:
        integrated = []
        for srs in srses:
            integrated.append(
                SRS(state=srs.state,
                srs=utg.get_sequence_from_start(srs.state) + ['screenshot'] + srs.plan_srs,
                srs_type=srs.srs_type,
            ))
        logging.info(f"Integrated {len(integrated)} SRSes with start sequences")
        return integrated
    
    @staticmethod
    def rotated_srses(srses: list[SRS]) -> List[SRS]:
        rotated_srses=[]
        for srs in srses:
            for i in range(len(srs.plan_srs)+1):
                c_srs=srs.plan_srs.copy()
                c_srs.insert(i, Action('rotate_left') )
                rotated_srses.append(SRS(srs.state, c_srs,srs.srs_type))

        logging.info(f"Generate {len(rotated_srses)} rotated SRSes from {len(srses)} original SRSes")
        return rotated_srses
    
    @staticmethod
    def extract_srses(cycles:List[List[UIStateEdge]],package) -> List[SRS]:
        srses=[]
        for c in cycles:
            for i in range(len(c)-1):
                if c[i].from_state.package != package: 
                    continue
                srs= SRS(c[i].from_state, c[i:]+c[:i])
                srses.append(srs)

        logging.info(f"Extracted {len(srses)} SRSes from {len(cycles)} cycles")
        return srses


    @staticmethod
    def get_new_cycles(utg: UIGraph, new_edge: UIStateEdge) -> List[List[UIStateEdge]]:

        results = []

        start_id = new_edge.from_state.id
        to_id = new_edge.to_state.id

        if start_id == to_id:
            logging.info("The new edge is a self-loop; no new cycles to find.")
            return results

        stack = [(to_id, [], {to_id})]

        while stack:
            current_id, path, visited = stack.pop()

            for e in utg.adjacency.get(current_id, []):
                next_id = e.to_state.id

                if next_id == start_id:
                    loop_path = [new_edge] + path + [e]
                    results.append(loop_path)

                elif next_id not in visited:
                    stack.append((
                        next_id,
                        path + [e],
                        visited | {next_id} 
                    ))
        logging.info(f"Found {len(results)} new cycles containing the new edge {new_edge.id}")
        return results
    


    @staticmethod
    def draw_srses(srses: List[SRS], out_dir='explorer/uigraph'):
        if len(srses) == 0:
            logging.info("No SRSes to draw.")
            return None
        
        dot = Digraph(comment='SRS Graph')
        dot.attr(rankdir='LR') 
        dot.attr(compound='true') 
        dot.attr(dpi='300')
        
        for i, srs in enumerate(srses):
            with dot.subgraph(name=f'cluster_{i}') as c:
                c.attr(label=f'SRS #{i} (ID: {srs.id[:6]})') 
                c.attr(style='dashed', color='grey') 
                
                def get_unique_id(obj_id):
                    return f"srs{i}_{obj_id}"

                start_node_real_id = srs.state.id
                first_step = srs.plan_srs[0] if srs.plan_srs else None
                
                actual_start_id = start_node_real_id
                if isinstance(first_step, UIStateEdge):
                    actual_start_id = first_step.from_state.id

                srs_state_unique_id = get_unique_id(srs.state.id)
                c.node(srs_state_unique_id, label=str(srs.state.id), shape='box', style='filled', fillcolor='lightblue')
                
                if actual_start_id != srs.state.id:
                    actual_start_unique_id = get_unique_id(actual_start_id)
                    c.node(actual_start_unique_id, label=str(actual_start_id), shape='box') 
                    last_node_id = actual_start_unique_id
                else:
                    last_node_id = srs_state_unique_id
                    
                    
                for step_index, step in enumerate(srs.plan_srs, 1):
                    edge_label = str(step_index)
                    
                    if isinstance(step, UIStateEdge):
                        to_state_id = step.to_state.id
                        current_node_id = get_unique_id(to_state_id)
                        
                        c.node(current_node_id, label=str(to_state_id), shape='box')
                        
                        c.edge(last_node_id, current_node_id, label=f"{step_index}: {step.action.action_type}")
                        
                        last_node_id = current_node_id

                    elif isinstance(step, Action):
                        action_node_id = get_unique_id(f"action_{step_index}")
                        
                        c.node(action_node_id, label=step.action_type, shape='ellipse', style='filled', fillcolor='lightgrey')
                        
                        c.edge(last_node_id, action_node_id, label=str(step_index))
                        
                        last_node_id = action_node_id
                    
                    elif step == 'screenshot':
                        shot_id = get_unique_id(f"shot_{step_index}")
                        c.node(shot_id, label="Screenshot", shape='note')
                        c.edge(last_node_id, shot_id, style='dotted')
                        last_node_id = shot_id

        if not os.path.exists(out_dir):
            os.makedirs(out_dir)
            
        output_path = os.path.join(out_dir, f'srs_graph_{get_curtime()}')
        path = dot.render(output_path, format='png', view=False)
        
        logging.info(f'SRS Graph saved to {path}')
        return path