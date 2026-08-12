import os
from typing import Union
import logging
from graphviz import Digraph
from collections import deque

from .state import State
from utils import write_json,write_jsonl
from .action import Action


class ActivityNode:
    def __init__(self, name):
        self.id = name 
        self.ui_states = set()
        self.visit_count = 0   

    def __repr__(self):
        return f"ActivityNode(id={self.id}, visit_count={self.visit_count})"
    def to_dict(self):
        return {
            'id': self.id,
            'visit_count': self.visit_count,
            'ui_states': [state.id for state in self.ui_states] 
        }
        
class UIStateNode:
    def __init__(self, state:State,activity:ActivityNode) -> None:
        self.package=state.ui_info['state_dict']['package']
        self.state=state
        self.id=self.state.id  
        self.visit_count = 0   
        self.activity = activity
        self.activity.ui_states.add(self)

    def __repr__(self):
        return f"UIStateNode(id={self.id}, state={self.state}, activity={self.activity}, visit_count={self.visit_count})"
    def to_dict(self):
        return {
            'id': self.id,
            'state_info': self.state.to_dict(), 
            'activity': self.activity.id,
            'visit_count': self.visit_count,
        }
        
class ActivityEdge:
    def __init__(self, from_act: ActivityNode, to_act: ActivityNode):
        self.from_act = from_act
        self.to_act = to_act
        self.id= f"{from_act.id}->{to_act.id}"
        self.visit_count = 0   

    def __repr__(self):
        return f"ACtivityEdge(id={self.id}, from_act.id={self.from_act.id}, to_act.id={self.to_act.id})"
    def to_dict(self):
        return {
            'id': self.id,
            'from_act': self.from_act.id,
            'to_act': self.to_act.id,
            'visit_count': self.visit_count
        }
        
class UIStateEdge:
    def __init__(self, from_state: UIStateNode, to_state: UIStateNode, action: Action) -> None:
        self.from_state = from_state
        self.to_state = to_state
        self.action = action
        self.id= f"{from_state.id}->{to_state.id}:{action.id}"
        self.visit_count = 0  

    def __repr__(self):
        return f"StateEdge(id={self.id}, from_state.id={self.from_state.id}, action={self.action}, to_state.id={self.to_state.id})"
    def to_dict(self):
        return {
            'id': self.id,
            'from_state': self.from_state.id,
            'to_state': self.to_state.id,
            'action': self.action.to_dict(),
            'visit_count': self.visit_count
        }
        
class UIGraph:
    def __init__(self,package):
        self.package=package
        self.activities = {}
        self.states     = {}
        self.state_edges = {}
        self.act_edges = {}
        self.adjacency = {}
        self.reverse_adjacency = {}
        self.start_state= None  

    def add_activity(self, name) -> Union[ActivityNode, bool]:
        is_new=False
        if name not in self.activities:
            self.activities[name] = ActivityNode(name)
            is_new=True
        self.activities[name].visit_count += 1
        return self.activities[name],is_new

    def add_state(self, state:State) -> Union[ UIStateNode, bool]:
        is_new = False
        if state is None or state.id is None or state.ui_info is None:
            return None, False
        
        activity,_ = self.add_activity(state.activity_name)
        if state.id not in self.states:
            self.states[state.id] = UIStateNode(state,activity)
            is_new = True
            if self.start_state is None:
                self.start_state = self.states[state.id] 
        self.states[state.id].visit_count += 1
        return self.states[state.id],is_new

    def add_stateedge(self, from_state:UIStateNode, to_state:UIStateNode, action:Action) ->  Union[ UIStateEdge, bool]:
        is_new = False
        if not from_state and to_state:
            logging.info('start node is None')
            return None,False
        if from_state is None or to_state is None:
            return None, False

        if from_state.id is None or to_state.id is None:
            return None, False
        if action is None or action.id is None:
            logging.info('action is None')
            return None, False
        
        edge_id = f"{from_state.id}->{to_state.id}:{action.id}"
        e = UIStateEdge(from_state, to_state, action)
        if edge_id not in self.state_edges:
            self.state_edges[edge_id] = e
            is_new = True

        if from_state.id not in self.adjacency:
            self.adjacency[from_state.id] = []
        self.adjacency[from_state.id].append(e)

        if to_state.id not in self.reverse_adjacency:
            self.reverse_adjacency[to_state.id] = []
        self.reverse_adjacency[to_state.id].append(e)

        self.state_edges[edge_id].visit_count += 1
        return self.state_edges[edge_id], is_new

    def add_actedge(self, from_act:ActivityNode, to_act:ActivityNode) -> Union[ActivityEdge, bool]:
        is_new=False
        edge_id=f"{from_act.id}->{to_act.id}"
        if edge_id not in self.act_edges:
            e = ActivityEdge(from_act, to_act)
            self.act_edges[edge_id]=e
            is_new=True
        self.act_edges[edge_id].visit_count+=1
        return self.act_edges[edge_id],is_new
    
    def get_adjacent_stateedges(self, state_id) -> list[UIStateEdge]:
        return self.adjacency.get(state_id, [])

    def get_sequence_from_start(self, target_state: UIStateNode) -> list[UIStateEdge]:
        if self.start_state is None or target_state is None:
            return []

        visited = set()
        parent = {}

        queue = deque()
        queue.append(self.start_state)
        visited.add(self.start_state.id)

        while queue:
            current = queue.popleft()
            if current.id == target_state.id:
                break

            for edge in self.adjacency.get(current.id, []):
                next_state = edge.to_state
                if next_state.id not in visited:
                    visited.add(next_state.id)
                    parent[next_state.id] = (current.id, edge)
                    queue.append(next_state)

        sequence = []
        current_id = target_state.id
        while current_id != self.start_state.id:
            if current_id not in parent:
                return []  
            prev_id, edge = parent[current_id]
            sequence.append(edge)
            current_id = prev_id

        sequence.reverse()
        return sequence

    
    def save_graph(self, out_dir='explorer/uigraph'):
        os.makedirs(out_dir, exist_ok=True)

        activities_list = [node.to_dict() for node in self.activities.values()]
        write_jsonl(os.path.join(out_dir, 'activities.jsonl'), activities_list)

        states_list = [node.to_dict() for node in self.states.values()]
        write_jsonl(os.path.join(out_dir, 'states.jsonl'), states_list)

        edges_list = [edge.to_dict() for edge in self.state_edges.values()]
        write_jsonl(os.path.join(out_dir, 'edges.jsonl'), edges_list)

        summary = {
            'activities': len(activities_list),
            'states': len(states_list),
            'edges': len(edges_list)
        }
        write_json(os.path.join(out_dir, 'summary.json'), summary)
      
    def draw_graph(self, out_dir='explorer/uigraph'):
        os.makedirs(out_dir, exist_ok=True)
        dot = Digraph(comment='UI Graph')

        for state_node in self.states.values():
            label = f"{state_node.id}, \nActivity: {state_node.activity.id},\nVisits: {state_node.visit_count}"
            dot.node(state_node.id, label=label)

        for edge in self.state_edges.values():
            label = f"{edge.action.action_type}, Visits: {edge.visit_count}"
            if edge.action.widget:
                if edge.action.widget.text:
                    label_txt= 'text:'+edge.action.widget.text
                elif edge.action.widget.hint:
                    label_txt= 'hint:'+edge.action.widget.hint
                elif edge.action.widget.content_desc:
                    label_txt= 'content_desc:'+edge.action.widget.content_desc
                else:
                    label_txt= 'classname:'+edge.action.widget.classname
                label = f"{edge.action.action_type}, {label_txt}, Visits: {edge.visit_count}"
            dot.edge(edge.from_state.id, edge.to_state.id, label=label)

        output_path = os.path.join(out_dir, 'uigraph')
        path = dot.render(output_path, format='png', view=False)
        logging.info(f'UI Graph save to {path}')
        return path
    
    def draw_graph_with_png(self, out_dir='explorer/uigraph'):
        os.makedirs(out_dir, exist_ok=True)
        dot = Digraph(comment='UI Graph')

        dot.attr('node', shape='box', style='rounded')

        for state_node in self.states.values():
            screenshot = state_node.state.screenshot_path
            screenshot = os.path.abspath(screenshot).replace("\\", "/")
            fallback_label = f"{state_node.id}, Activity: {state_node.activity.id}, \nVisits: {state_node.visit_count}"

            dot.node(
                state_node.id,
                label=fallback_label,
                image=screenshot if screenshot and os.path.exists(screenshot) else "",
                labelloc="b", 
                imagescale="true",
                fixedsize="false"
            )

        for edge in self.state_edges.values():
            label = f"{edge.action.action_type}, Visits: {edge.visit_count}"
            if edge.action.widget:
                if edge.action.widget.text:
                    label_txt= 'text:'+edge.action.widget.text
                elif edge.action.widget.hint:
                    label_txt= 'hint:'+edge.action.widget.hint
                elif edge.action.widget.content_desc:
                    label_txt= 'content_desc:'+edge.action.widget.content_desc
                else:
                    label_txt= 'classname:'+edge.action.widget.classname
                label = f"{edge.action.action_type}, {label_txt}, Visits: {edge.visit_count}"
            dot.edge(edge.from_state.id, edge.to_state.id, label=label)

        output_path = os.path.join(out_dir, 'uigraph_withpng')
        path = dot.render(output_path, format='png', view=False)
        logging.info(f'UI Graph saved to {path}')
        return path
    
    def draw_grouped(self, out_dir='explorer/uigraph'):
        dot = Digraph('UIGraph')
        dot.attr('graph', splines='true')

        by_activity = {}
        for st in self.states.values():
            by_activity.setdefault(st.activity.id, []).append(st)

        for act_name, states in by_activity.items():
            with dot.subgraph(name=f'cluster_{act_name}') as c:
                c.attr(label=act_name, style='dashed', color='gray')
                for st in states:
                    label = f"{st.id}\n Visits:{st.visit_count}"
                    c.node(st.id, label=label)

        for edge in self.state_edges.values():
            label = f"{edge.action.action_type}, Visits: {edge.visit_count}"
            if edge.action.widget:
                if edge.action.widget.text:
                    label_txt= 'text:'+edge.action.widget.text
                elif edge.action.widget.hint:
                    label_txt= 'hint:'+edge.action.widget.hint
                elif edge.action.widget.content_desc:
                    label_txt= 'content_desc:'+edge.action.widget.content_desc
                else:
                    label_txt= 'classname:'+edge.action.widget.classname
                label = f"{edge.action.action_type}, {label_txt}, Visits: {edge.visit_count}"
            dot.edge(edge.from_state.id, edge.to_state.id, label=label)

        path = dot.render(os.path.join(out_dir, 'grouped_graph'), format='png', view=False)
        return path
            
    def draw_grouped_with_png(self, out_dir='explorer/uigraph'):
        os.makedirs(out_dir, exist_ok=True)
        dot = Digraph('UIGraph')
        dot.attr('graph', splines='true')

        by_activity = {}
        for st in self.states.values():
            by_activity.setdefault(st.activity.id, []).append(st)

        for act_name, states in by_activity.items():
            safe_name = act_name.replace('.', '_').replace('/', '_')

            with dot.subgraph(name=f'cluster_{safe_name}') as c:
                c.attr(label=act_name, style='dashed', color='gray')

                for st in states:
                    screenshot = st.state.screenshot_path
                    screenshot = os.path.abspath(screenshot).replace("\\", "/")

                    if screenshot and os.path.exists(screenshot):
                        c.node(
                            st.id,
                            label=f"{st.id}\nVisits:{st.visit_count}",
                            image=screenshot,
                            labelloc="b",     
                            shape="box",
                            imagescale="true",
                            fixedsize="false"
                        )
                    else:
                        c.node(
                            st.id,
                            label=f"{st.id}\nVisits:{st.visit_count}",
                            shape="box"
                        )

        for edge in self.state_edges.values():
            label = f"{edge.action.action_type}, Visits: {edge.visit_count}"
            if edge.action.widget:
                if edge.action.widget.text:
                    label_txt= 'text:'+edge.action.widget.text
                elif edge.action.widget.hint:
                    label_txt= 'hint:'+edge.action.widget.hint
                elif edge.action.widget.content_desc:
                    label_txt= 'content_desc:'+edge.action.widget.content_desc
                else:
                    label_txt= 'classname:'+edge.action.widget.classname
                label = f"{edge.action.action_type}, {label_txt}, Visits: {edge.visit_count}"
            dot.edge(edge.from_state.id, edge.to_state.id, label=label)

        path = dot.render(os.path.join(out_dir, 'grouped_graph_with_png'),
                          format='png', view=False)
        return path
