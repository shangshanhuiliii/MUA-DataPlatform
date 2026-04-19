import datetime
import json
import logging
import os
import random
from collections import OrderedDict

import networkx as nx
from filelock import FileLock


class UTG(object):
    """
    UI Transition Graph (UTG) - A directed graph representing UI state transitions
    
    The UTG captures the navigation flow of a mobile application by modeling:
    - UI states as nodes (represented by screenshots and UI hierarchy)
    - User interactions as edges (touch, swipe, key events, etc.)
    - Transition relationships between states through events
    
    Graph Structure:
    - G: Main detailed graph where nodes are unique UI states (state_str as key)
      * Node data: {"state": DeviceState object}
      * Edge data: {"events": {event_str: {"event": Event, "id": int}}}
    - G2: Structure-based graph where nodes represent UI layout patterns (structure_str as key)
      * Node data: {"states": [list of DeviceState objects with same structure]}
      * Edge data: {"events": {event_str: {"event": Event, "id": int}}}
      * Used for simplified navigation when UI content differs but structure is same
    
    Usage Examples:
    
    Node Operations:
    - Get state object: state = utg.G.nodes[state_str]["state"]
    - Check if state exists: if state_str in utg.G.nodes()
    - Get all states with same structure: states = utg.G2.nodes[structure_str]["states"]
    - Iterate all nodes: for state_str in utg.G.nodes()
    
    Edge Operations:
    - Get events between states: events = utg.G[from_state_str][to_state_str]["events"]
    - Check if edge exists: if (from_state_str, to_state_str) in utg.G.edges()
    - Get specific event: event = utg.G[from_state_str][to_state_str]["events"][event_str]["event"]
    - Get event ID: event_id = utg.G[from_state_str][to_state_str]["events"][event_str]["id"]
    - Get outgoing edges: for to_state_str, to_state_events in utg.G[from_state_str].items()
    - Get outgoing events: for event_str, event_dict in to_state_events['events'].items()
    - Get event and ID: event = event_dict['event']; event_id = event_dict['id']
    
    Navigation:
    - Find path: path = nx.shortest_path(utg.G, source=from_state_str, target=to_state_str)
    - Get descendants: reachable = nx.descendants(utg.G, current_state_str)
    - Get navigation steps: steps = utg.get_navigation_steps(from_state, to_state)
    - Get reachable states: states = utg.get_reachable_states(current_state)
    
    Key Features:
    - Maintains two graphs: G (detailed state graph) and G2 (structure-based graph)
    - Tracks effective vs ineffective events (self-loops)
    - Supports navigation path finding between states
    - Outputs visualization data in JSON/JS format for web interface
    - Handles state clustering based on UI structure similarity
    
    The UTG is used for:
    - GUI testing and exploration
    - Automated app navigation
    - UI state coverage analysis
    - Test case generation and replay
    """

    JSON_NAME = "utg.json"
    LOCK_FILE_NAME = "utg.lockfile"
    JS_NAME = "utg.js"

    def __init__(self, output_dir, device_serial, device_model_number, device_sdk_version,
                 app_signature, app_package, app_main_activity, app_num_total_activities,
                 random_input, keep_self_loops=False):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.output_dir = output_dir
        self.device_serial = device_serial
        self.device_model_number = device_model_number
        self.device_sdk_version = device_sdk_version
        self.app_signature = app_signature
        self.app_package = app_package
        self.app_main_activity = app_main_activity
        self.app_num_total_activities = app_num_total_activities
        self.random_input = random_input
        self.keep_self_loops = keep_self_loops

        self.G = nx.DiGraph()
        self.G2 = nx.DiGraph()  # graph with same-structure states clustered

        self.transitions = []
        self.effective_event_strs = set()
        self.ineffective_event_strs = set()
        self.explored_state_strs = set()
        self.reached_state_strs = set()
        self.reached_activities = set()

        self.first_state = None
        self.last_state = None

        self.start_time = datetime.datetime.now()

        # Initialize file lock for UTG output operations
        if self.output_dir:
            lock_file_path = os.path.join(self.output_dir, self.LOCK_FILE_NAME)
            self.file_lock = FileLock(lock_file_path, timeout=10, mode=0o666)
        else:
            self.file_lock = None

    @property
    def first_state_str(self):
        return self.first_state.state_str if self.first_state else None

    def set_first_state(self, state_or_str, skip_output=False):
        """
        设置First State状态

        :param state_or_str: 状态对象或状态字符串
        :param skip_output: 是否跳过UTG输出，默认False
        :return: 设置是否成功
        """
        if not state_or_str:
            return False
        
        if isinstance(state_or_str, str):
            state_str = state_or_str
            state = self.get_state(state_str)
            if state is None:
                return False
        else:
            state = state_or_str
            state_str = state.state_str

        if state_str not in self.G.nodes():
            return False
        
        self.first_state = state
        if not skip_output:
            self.__output_utg()
        return True

    @property
    def last_state_str(self):
        return self.last_state.state_str if self.last_state else None
    
    def set_last_state(self, state_or_str, skip_output=False):
        """
        设置Last State状态

        :param state_or_str: 状态对象或状态字符串
        :param skip_output: 是否跳过UTG输出，默认False
        :return: 设置是否成功
        """
        if not state_or_str:
            return False
        
        if isinstance(state_or_str, str):
            state_str = state_or_str
            state = self.get_state(state_str)
            if state is None:
                return False
        else:
            state = state_or_str
            state_str = state.state_str

        if state_str not in self.G.nodes():
            return False
        
        self.last_state = state
        if not skip_output:
            self.__output_utg()
        return True

    @property
    def effective_event_count(self):
        return len(self.effective_event_strs)

    @property
    def ineffective_event_count(self):
        return len(self.ineffective_event_strs)

    @property
    def num_transitions(self):
        return len(self.transitions)
    
    @property
    def num_nodes(self):
        return len(self.G.nodes)

    def add_transition(self, event, old_state, new_state, skip_output=False):
        """
        添加状态转换
        
        :param event: 事件对象(InputEvent)或事件字符串(str)
        :param old_state: 源状态对象
        :param new_state: 目标状态对象
        :param skip_output: 是否跳过UTG输出，默认False
        :return: 添加是否成功
        """        
        # make sure the states are not None
        if not old_state or not new_state:
            return False

        # 支持传入 event_str 或 InputEvent 对象
        if isinstance(event, str):
            # 如果传入的是字符串，需要创建 InputEvent 对象
            event_str = event
            from .input_event import InputEvent
            event_obj = InputEvent.from_event_str(event_str, old_state)
            if event_obj is None:
                self.logger.error(f"Failed to create InputEvent from event_str: {event_str}")
                return False
        else:
            # 如果传入的是 InputEvent 对象，获取其 event_str
            event_str = event.get_event_str(old_state)
            event_obj = event

        self.transitions.append((old_state, event_obj, new_state))
        
        if old_state.state_str == new_state.state_str:
            self.ineffective_event_strs.add(event_str)
            if event_str in self.effective_event_strs:
                self.effective_event_strs.remove(event_str)
            if not self.keep_self_loops:
                # delete the transitions including the event from utg
                for new_state_str in self.G[old_state.state_str]:
                    if event_str in self.G[old_state.state_str][new_state_str]["events"]:
                        self.G[old_state.state_str][new_state_str]["events"].pop(event_str)
                return False
        else:
            self.effective_event_strs.add(event_str)

        
        # 应该在做完所有的前置检查，才添加 state
        # state 应该在第一次加入图时保存
        # 继承UTG的skip_output，会导致手动保存 UTG 的情况下
        # state 没有保存.
        self.add_node(old_state, skip_output=False)
        self.add_node(new_state, skip_output=False)
        if (old_state.state_str, new_state.state_str) not in self.G.edges():
            self.G.add_edge(old_state.state_str, new_state.state_str, events={})
        
        # 计算event_id
        if self.keep_self_loops:
            event_id = self.effective_event_count + self.ineffective_event_count
        else:
            event_id = self.effective_event_count

        self.G[old_state.state_str][new_state.state_str]["events"][event_str] = {
            "event": event_obj,
            "id": event_id
        }

        if (old_state.structure_str, new_state.structure_str) not in self.G2.edges():
            self.G2.add_edge(old_state.structure_str, new_state.structure_str, events={})
        self.G2[old_state.structure_str][new_state.structure_str]["events"][event_str] = {
            "event": event_obj,
            "id": event_id
        }

        self.last_state = new_state
        
        # 只有在不跳过输出时才调用 __output_utg
        if not skip_output:
            self.__output_utg()
        
        return True

    def remove_transition(self, event, old_state, new_state, skip_output=False):
        """
        移除状态转换
        
        :param event: 事件对象(InputEvent)或事件字符串(str)
        :param old_state: 源状态对象
        :param new_state: 目标状态对象
        :param skip_output: 是否跳过UTG输出，默认False
        :return: 移除是否成功
        """
        # 支持传入 event_str 或 InputEvent 对象
        if isinstance(event, str):
            # 如果传入的是字符串，直接使用作为 event_str
            event_str = event
        else:
            # 如果传入的是 InputEvent 对象，获取其 event_str
            event_str = event.get_event_str(old_state)
        
        # 检查转换是否存在
        if (old_state.state_str, new_state.state_str) not in self.G.edges():
            self.logger.warning(f"Transition from {old_state.state_str} to {new_state.state_str} does not exist")
            return False
        
        # 检查事件是否存在于该转换中
        events = self.G[old_state.state_str][new_state.state_str]["events"]
        if event_str not in events:
            self.logger.warning(f"Event {event_str} not found in transition from {old_state.state_str} to {new_state.state_str}")
            return False
        
        # 从主图G中移除事件
        events.pop(event_str)
        if len(events) == 0:
            self.G.remove_edge(old_state.state_str, new_state.state_str)
        
        # 从结构图G2中移除事件
        if (old_state.structure_str, new_state.structure_str) in self.G2.edges():
            g2_events = self.G2[old_state.structure_str][new_state.structure_str]["events"]
            if event_str in g2_events:
                g2_events.pop(event_str)
                if len(g2_events) == 0:
                    self.G2.remove_edge(old_state.structure_str, new_state.structure_str)
        
        # 从事件集合中移除事件
        if event_str in self.effective_event_strs:
            self.effective_event_strs.remove(event_str)
        if event_str in self.ineffective_event_strs:
            self.ineffective_event_strs.remove(event_str)
        
        # 从transitions列表中移除相关转换
        self.transitions = [
            (state_old, trans_event, state_new) for state_old, trans_event, state_new in self.transitions
            if not (state_old.state_str == old_state.state_str and 
                   state_new.state_str == new_state.state_str and 
                   trans_event.get_event_str(state_old) == event_str)
        ]
        
        if not skip_output:
            self.__output_utg()

        return True

    def update_transition(self, old_event, old_from_state, old_to_state, new_event, new_from_state, new_to_state, skip_output=False):
        """
        更新现有的状态转换，移除旧事件并添加新事件（可能在不同的状态之间）
        
        :param old_event: 要被替换的旧事件对象或事件字符串
        :param old_from_state: 旧事件的源状态对象
        :param old_to_state: 旧事件的目标状态对象
        :param new_event: 新的事件对象或事件字符串
        :param new_from_state: 新事件的源状态对象
        :param new_to_state: 新事件的目标状态对象
        :param skip_output: 是否跳过UTG输出，默认False
        """
        # 处理旧事件参数：支持传入 event_str 或 InputEvent 对象
        if isinstance(old_event, str):
            old_event_str = old_event
        else:
            old_event_str = old_event.get_event_str(old_from_state)
        
        # 处理新事件参数：支持传入 event_str 或 InputEvent 对象
        if isinstance(new_event, str):
            new_event_str = new_event
            new_event_obj = None
            # 如果传入的是字符串，需要创建 InputEvent 对象
            from .input_event import InputEvent
            new_event_obj = InputEvent.from_event_str(new_event_str, new_from_state)
            if new_event_obj is None:
                self.logger.error(f"Failed to create InputEvent from event_str: {new_event_str}")
                return False
        else:
            new_event_str = new_event.get_event_str(new_from_state)
            new_event_obj = new_event
        
        # 检查旧转换是否存在
        if (old_from_state.state_str, old_to_state.state_str) not in self.G.edges():
            self.logger.warning(f"Old transition from {old_from_state.state_str} to {old_to_state.state_str} does not exist")
            return False
            
        # 检查旧事件是否存在于该转换中
        old_events = self.G[old_from_state.state_str][old_to_state.state_str]["events"]
        if old_event_str not in old_events:
            self.logger.warning(f"Event {old_event_str} not found in transition from {old_from_state.state_str} to {old_to_state.state_str}")
            return False
        
        # 判断是否为状态转换（源状态或目标状态发生改变）
        state_changed = (old_from_state.state_str != new_from_state.state_str or 
                        old_to_state.state_str != new_to_state.state_str)
        if state_changed:
            # 状态改变：使用现有的 remove_transition 和 add_transition 方法
            # 保存旧事件的ID，用于新事件
            old_event_id = old_events[old_event_str]["id"]

            # 移除旧事件（直接传递 event_str）
            remove_result = self.remove_transition(old_event_str, old_from_state, old_to_state, skip_output=True)
            if not remove_result:
                return False

            # 添加新事件（直接传递 event_str）
            add_result = self.add_transition(new_event_str, new_from_state, new_to_state, skip_output=True)
            if not add_result:
                return False
            
            # 更新新事件的ID为旧事件的ID，保持时间顺序
            # new_event_str 在前面已经定义好了
            self.G[new_from_state.state_str][new_to_state.state_str]["events"][new_event_str]["id"] = old_event_id
            self.G2[new_from_state.structure_str][new_to_state.structure_str]["events"][new_event_str]["id"] = old_event_id
        else:
            # 状态不变：直接更新事件内容
            # new_event_str 在前面已经定义好了
            
            # 如果新旧事件字符串，只更新event就行
            if old_event_str == new_event_str:
                # 事件字符串相同，只更新事件对象
                old_events[old_event_str]["event"] = new_event_obj

                # 同步更新G2
                if (old_from_state.structure_str, old_to_state.structure_str) in self.G2.edges():
                    g2_events = self.G2[old_from_state.structure_str][old_to_state.structure_str]["events"]
                    if old_event_str in g2_events:
                        g2_events[old_event_str]["event"] = new_event_obj
            else:
                old_event_id = old_events[old_event_str]["id"]
                # 更新主图G
                old_events.pop(old_event_str)
                old_events[new_event_str] = {
                    "event": new_event_obj,
                    "id": old_event_id
                }

                # 更新结构图G2
                if (old_from_state.structure_str, old_to_state.structure_str) in self.G2.edges():
                    g2_events = self.G2[old_from_state.structure_str][old_to_state.structure_str]["events"]
                    if old_event_str in g2_events:
                        g2_events.pop(old_event_str)
                        g2_events[new_event_str] = {
                            "event": new_event_obj,
                            "id": old_event_id
                        }
                
                # 更新事件集合
                if old_event_str in self.effective_event_strs:
                    self.effective_event_strs.remove(old_event_str)
                    self.effective_event_strs.add(new_event_str)
                if old_event_str in self.ineffective_event_strs:
                    self.ineffective_event_strs.remove(old_event_str)
                    self.ineffective_event_strs.add(new_event_str)
        
        # 输出更新后的UTG
        if not skip_output:
            self.__output_utg()

        return True

    def add_node(self, state, skip_output=False):
        if not state:
            return
        if state.state_str not in self.G.nodes():
            if not skip_output and not os.path.exists(state.state_json_path):
                state.save2dir()
            self.G.add_node(state.state_str, state=state, label=[], label_meta={})
            if self.first_state is None:
                self.first_state = state

        if state.structure_str not in self.G2.nodes():
            self.G2.add_node(state.structure_str, states=[])
        self.G2.nodes[state.structure_str]['states'].append(state)

        if state.foreground_activity.startswith(self.app_package):
            self.reached_activities.add(state.foreground_activity)

    def find_branch_states(self, target):
        """
        使用支配树算法找出从目标节点开始的独占分支中的所有节点

        算法逻辑：
        1. 创建临时图，添加虚拟根节点连接到所有源节点（或直接连接目标节点）
        2. 使用 NetworkX 的 immediate_dominators 计算支配关系
        3. 构建支配树结构
        4. 从目标节点开始，获取其所有后代节点（被支配的节点）

        :param target: 目标节点，可以是 DeviceState 对象或 state_str 字符串
        :return: 需要被删除的节点集合（state_str 的 list）
        """
        # 统一处理输入参数：支持传入 state 对象或 state_str
        if isinstance(target, str):
            target_state_str = target
        else:
            target_state_str = target.state_str

        # 检查目标节点是否存在
        if target_state_str not in self.G.nodes():
            self.logger.warning(f"Target state {target_state_str} not found in UTG")
            return []

        # 1. 创建临时图并添加虚拟根节点
        temp_graph = self.G.copy()  # O(V + E)
        virtual_root = "__VIRTUAL_ROOT__"
        temp_graph.add_node(virtual_root)

        # 找到所有源节点（入度为0的节点）
        source_nodes = [node for node in temp_graph.nodes() 
                       if temp_graph.in_degree(node) == 0]  # O(V)

        if source_nodes:
            # 情况1: 有源节点，连接到所有源节点
            for source in source_nodes:
                temp_graph.add_edge(virtual_root, source)
        else:
            # 情况2: 没有源节点，直接指向目标节点
            temp_graph.add_edge(virtual_root, target_state_str)

        # 2. 计算支配树
        immediate_dominators = nx.immediate_dominators(temp_graph, virtual_root)  # O(V + E)

        # 3. 构建支配树
        dominator_tree = nx.DiGraph()
        for child, parent in immediate_dominators.items():  # O(V)
            if parent is not None:  # 跳过根节点
                dominator_tree.add_edge(parent, child)

        # 4. 获取目标节点的所有后代节点（被支配的节点）
        to_delete = nx.descendants(dominator_tree, target_state_str)  # O(V)
        to_delete.add(target_state_str)

        return list(to_delete)

    def remove_node(self, state, skip_output=False):
        """
        从UTG中移除指定的状态节点，同时删除所有与该节点相关的事件和转换

        :param state: 要移除的状态对象
        :param skip_output: 是否跳过UTG输出，默认False
        :return: 移除是否成功
        """
        if not state:
            return False
        
        state_str = state.state_str
        structure_str = state.structure_str
        
        # 检查节点是否存在于主图G中
        if state_str not in self.G.nodes():
            self.logger.warning(f"State {state_str} not found in UTG")
            return False
        
        # 收集需要移除的事件字符串，用于更新事件集合
        events_to_remove = set()
        
        # 1. 收集所有与该节点相关的事件
        # 收集该节点作为源节点的所有出边事件
        if state_str in self.G:
            for target_state_str, edge_data in self.G[state_str].items():
                for event_str in edge_data["events"].keys():
                    events_to_remove.add(event_str)
        
        # 收集该节点作为目标节点的所有入边事件
        for source_state_str in self.G.nodes():
            if source_state_str != state_str and state_str in self.G[source_state_str]:
                edge_data = self.G[source_state_str][state_str]
                for event_str in edge_data["events"].keys():
                    events_to_remove.add(event_str)
        
        # 2. 从事件集合中移除相关事件
        for event_str in events_to_remove:
            if event_str in self.effective_event_strs:
                self.effective_event_strs.remove(event_str)
            if event_str in self.ineffective_event_strs:
                self.ineffective_event_strs.remove(event_str)
        
        # 3. 从主图G中移除节点（NetworkX会自动删除相关的边）
        self.G.remove_node(state_str)
        
        # 4. 处理结构图G2
        if structure_str in self.G2.nodes():
            # 从G2节点的states列表中移除该状态
            states_list = self.G2.nodes[structure_str]['states']
            states_list = [s for s in states_list if s.state_str != state_str]
            
            if len(states_list) == 0:
                # 如果没有其他状态具有相同结构，移除G2中的节点
                self.G2.remove_node(structure_str)
            else:
                # 否则更新states列表
                self.G2.nodes[structure_str]['states'] = states_list
        
        # 5. 更新特殊状态引用
        if self.first_state and self.first_state.state_str == state_str:
            # 如果删除的是第一个状态，将first_state设为None或图中的第一个节点
            if len(self.G.nodes()) > 0:
                first_node_str = next(iter(self.G.nodes()))
                self.first_state = self.G.nodes[first_node_str]["state"]
            else:
                self.first_state = None
        
        if self.last_state and self.last_state.state_str == state_str:
            # 如果删除的是最后一个状态，将last_state设为None或图中的最后一个节点
            if len(self.G.nodes()) > 0:
                last_node_str = list(self.G.nodes())[-1]
                self.last_state = self.G.nodes[last_node_str]["state"]
            else:
                self.last_state = None
        
        # 6. 从transitions列表中移除相关转换
        self.transitions = [
            (old_state, event, new_state) for old_state, event, new_state in self.transitions
            if old_state.state_str != state_str and new_state.state_str != state_str
        ]
        
        # 7. 从reached_activities中移除（如果该活动没有其他状态）
        if state.foreground_activity.startswith(self.app_package):
            # 检查是否还有其他状态使用相同的活动
            activity_still_exists = any(
                s.foreground_activity == state.foreground_activity 
                for s in [self.G.nodes[node_str]["state"] for node_str in self.G.nodes()]
            )
            if not activity_still_exists:
                self.reached_activities.discard(state.foreground_activity)
        
        # 8. 输出更新后的UTG
        if not skip_output:
            self.__output_utg()
        
        return True

    def get_deleted_states(self):
        """
        找出states目录中存在，但在图中不存在的state。

        :return: 返回被删除的 state 对象列表
        """
        # 从图中获取当前全部节点(state_str)
        current_nodes = set(self.G.nodes())
        # 加载所有状态文件
        states_dict = self._load_device_states(self.output_dir, self.logger)
        
        # 储存删除的state对象列表
        deleted_states = [
            state_obj
            for state_str, state_obj in states_dict.items()
            if state_str not in current_nodes
        ]

        return deleted_states

    def restore_node(self, state_str, skip_output=False):
        """
        恢复被删除的节点，只恢复节点本身，不恢复边或事件

        :param state_str: 要恢复的节点 state_str
        :return: bool, 是否恢复成功
        """

        # 检查需要恢复的节点是否已经存在于主图G中
        if state_str in self.G.nodes():
            self.logger.info(f"State {state_str} already exists in UTG, skip restore")
            return True
        
        # 加载所有状态文件
        states_dict = self._load_device_states(self.output_dir, self.logger)

        # 检查需要恢复的节点是否在states_dict中
        if state_str not in states_dict:
            self.logger.warning(f"State {state_str} not found in states directory")
            return False
        
        state_obj = states_dict[state_str]

        # 添加节点到 UTG 图
        self.add_node(state_obj, skip_output=skip_output)

        return True

    def to_dict(self):
        """
        将 UTG 对象转换为 JSON 可序列化的格式
        
        :return: 包含完整 UTG 数据的字典对象
        """
        def list_to_html_table(dict_data):
            table = "<table class=\"table\">\n"
            for (key, value) in dict_data:
                table += "<tr><th>%s</th><td>%s</td></tr>\n" % (key, value)
            table += "</table>"
            return table

        utg_nodes = []
        utg_edges = []
        for state_str in self.G.nodes():
            state = self.G.nodes[state_str]["state"]
            node_labels = self.G.nodes[state_str].get("label", [])
            node_label_meta = self.G.nodes[state_str].get("label_meta", {})
            package_name = state.foreground_activity.split("/")[0]
            activity_name = state.foreground_activity.split("/")[1]
            activity_short_name = state.activity_short_name

            state_desc = list_to_html_table([
                ("package", package_name),
                ("activity", activity_name),
                ("state_str", state.state_str),
                ("structure_str", state.structure_str)
            ])
            
            # 构建 label: activity_short_name\n{label1}\n{label2}...\n<FIRST>|<LAST>
            label_parts = [activity_short_name]
            font = ""
            # 添加自定义 labels
            if node_labels:
                label_parts.extend(node_labels)
                font = "14px Arial green"
            # 添加 <FIRST> 或 <LAST> 标记
            if state.state_str == self.first_state_str:
                label_parts.append("<FIRST>")
                font = "14px Arial red"
            if state.state_str == self.last_state_str:
                label_parts.append("<LAST>")
                font = "14px Arial red"
            
            node_label = "\n".join(label_parts)

            utg_node = {
                "id": state_str,
                "shape": "image",
                "image": os.path.relpath(state.screenshot_path, self.output_dir),
                "label": node_label,
                # "group": state.foreground_activity,
                "package": package_name,
                "activity": activity_name,
                "state_str": state_str,
                "structure_str": state.structure_str,
                "title": state_desc,
                "content": "\n".join([package_name, activity_name, state.state_str, state.search_content])
            }

            if node_label_meta:
                utg_node["label_meta"] = node_label_meta

            if font:
                utg_node["font"] = font

            utg_nodes.append(utg_node)

        for state_transition in self.G.edges():
            from_state_str = state_transition[0]
            to_state_str = state_transition[1]

            events = self.G[from_state_str][to_state_str]["events"]
            event_short_descs = []
            event_list = []

            for event_str, event_info in sorted(iter(events.items()), key=lambda x: x[1]["id"]):
                event_short_descs.append((event_info["id"], event_str))
                event_list.append({
                    "event_str": event_str,
                    "event_id": event_info["id"],
                    "event_type": event_info["event"].event_type
                })

            utg_edge = {
                "from": from_state_str,
                "to": to_state_str,
                "id": from_state_str + "-->" + to_state_str,
                "title": list_to_html_table(event_short_descs),
                "label": ", ".join([str(x["event_id"]) for x in event_list]),
                "events": event_list
            }

            # # Highlight last transition
            # if state_transition == self.last_transition:
            #     utg_edge["color"] = "red"

            utg_edges.append(utg_edge)

        # 使用 OrderedDict 保证字段顺序
        utg = OrderedDict([
            ("nodes", utg_nodes),
            ("edges", utg_edges),
            ("num_nodes", len(utg_nodes)),
            ("num_edges", len(utg_edges)),
            ("num_effective_events", len(self.effective_event_strs)),
        ])
        
        # 如果 keep_self_loops == True，则添加 num_ineffective_events
        if self.keep_self_loops:
            utg["num_ineffective_events"] = len(self.ineffective_event_strs)
        
        # 继续添加其他字段
        utg.update([
            ("num_reached_activities", len(self.reached_activities)),
            ("test_date", self.start_time.strftime("%Y-%m-%d %H:%M:%S")),
            ("time_spent", (datetime.datetime.now() - self.start_time).total_seconds()),
            ("num_transitions", self.num_transitions),
            ("device_serial", self.device_serial),
            ("device_model_number", self.device_model_number),
            ("device_sdk_version", self.device_sdk_version),
            ("app_signature", self.app_signature),
            ("app_package", self.app_package),
            ("app_main_activity", self.app_main_activity),
            ("app_num_total_activities", self.app_num_total_activities),
        ])

        return utg

    def __output_utg(self):
        """
        Output current UTG to both json and js files with file lock protection
        """
        if not self.output_dir:
            return

        utg_json_path = os.path.join(self.output_dir, self.JSON_NAME)
        utg_js_path = os.path.join(self.output_dir, self.JS_NAME)

        utg_json = json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

        # Use file lock to prevent concurrent writes
        if self.file_lock:
            with self.file_lock:
                # Save as JSON file for web interface
                with open(utg_json_path, "w", encoding="utf-8") as json_file:
                    json_file.write(utg_json)

                # Save as JS file for legacy compatibility
                with open(utg_js_path, "w", encoding="utf-8") as js_file:
                    js_file.write("var utg = \n")
                    js_file.write(utg_json)
        else:
            # No lock available, write directly (backward compatibility)
            with open(utg_json_path, "w", encoding="utf-8") as json_file:
                json_file.write(utg_json)

            with open(utg_js_path, "w", encoding="utf-8") as js_file:
                js_file.write("var utg = \n")
                js_file.write(utg_json)

    def save2dir(self):
        self.__output_utg()

    def is_event_explored(self, event, state):
        event_str = event.get_event_str(state)
        return event_str in self.effective_event_strs or event_str in self.ineffective_event_strs

    def is_state_explored(self, state):
        if state.state_str in self.explored_state_strs:
            return True
        for possible_event in state.get_possible_input():
            if not self.is_event_explored(possible_event, state):
                return False
        self.explored_state_strs.add(state.state_str)
        return True

    def is_state_reached(self, state):
        if state.state_str in self.reached_state_strs:
            return True
        self.reached_state_strs.add(state.state_str)
        return False

    def get_reachable_states(self, current_state):
        reachable_states = []
        for target_state_str in nx.descendants(self.G, current_state.state_str):
            target_state = self.G.nodes[target_state_str]["state"]
            reachable_states.append(target_state)
        return reachable_states

    def get_state(self, state_str):
        """
        根据状态ID获取DeviceState对象
        
        :param state_str: 状态字符串标识符
        :return: DeviceState对象，如果不存在则返回None
        """
        if not state_str:
            return None
        
        if state_str not in self.G.nodes():
            return None
        
        return self.G.nodes[state_str]["state"]

    def set_label(self, state_or_str, labels):
        """
        为指定的状态节点设置标签
        
        :param state_or_str: DeviceState对象或state_str字符串
        :param labels: 标签列表（List[str]），用于替换节点的label属性
        :return: 设置是否成功
        """
        # 统一处理输入参数：支持传入 state 对象或 state_str
        if isinstance(state_or_str, str):
            state_str = state_or_str
        else:
            state_str = state_or_str.state_str
        
        # 检查节点是否存在
        if state_str not in self.G.nodes():
            self.logger.warning(f"State {state_str} not found in UTG")
            return False
        
        # 确保 labels 是列表类型
        if not isinstance(labels, list):
            self.logger.warning(f"Labels must be a list, got {type(labels)}")
            return False
        
        # 设置节点的 label 属性
        self.G.nodes[state_str]["label"] = labels
        
        return True

    def set_label_meta(self, state_or_str, label_meta):
        """
        为指定的状态节点设置 label_meta
        
        :param state_or_str: DeviceState对象或state_str字符串
        :param label_meta: 标签元数据字典（Dict[str, Any]）
        :return: 设置是否成功
        """
        # 统一处理输入参数：支持传入 state 对象或 state_str
        if isinstance(state_or_str, str):
            state_str = state_or_str
        else:
            state_str = state_or_str.state_str
        
        # 检查节点是否存在
        if state_str not in self.G.nodes():
            self.logger.warning(f"State {state_str} not found in UTG")
            return False
        
        # 确保 label_meta 是字典类型
        if not isinstance(label_meta, dict):
            self.logger.warning(f"label_meta must be a dict, got {type(label_meta)}")
            return False
        
        # 设置节点的 label_meta 属性
        self.G.nodes[state_str]["label_meta"] = label_meta
        
        return True

    def get_label_meta(self, state_or_str):
        """
        获取指定的状态节点的 label_meta
        
        :param state_or_str: DeviceState对象或state_str字符串
        :return: label_meta 字典（Dict[str, Any]）
        """
        if isinstance(state_or_str, str):
            state_str = state_or_str
        else:
            state_str = state_or_str.state_str
        
        if state_str not in self.G.nodes():
            return {}
        
        return self.G.nodes[state_str].get("label_meta", {})

    def get_label(self, state_or_str):
        """
        获取指定的状态节点的标签
        
        :param state_or_str: DeviceState对象或state_str字符串
        :return: label列表（List[str]）
        """
        if isinstance(state_or_str, str):
            state_str = state_or_str
        else:
            state_str = state_or_str.state_str
        
        if state_str not in self.G.nodes():
            return []
        
        return self.G.nodes[state_str]["label"]

    def get_outgoing_events(self, current_state):
        """
        Get all outgoing events from the given state
        
        :param current_state: DeviceState object to get outgoing edges from
        :return: List of (target_state, events_dict) tuples where events_dict maps event_str to event_info
        """
        if not current_state or current_state.state_str not in self.G.nodes():
            return []
        
        outgoing_events = []
        for target_state_str, edge_data in self.G[current_state.state_str].items():
            target_state = self.G.nodes[target_state_str]["state"]
            events = edge_data["events"]
            for event_str, event_dict in events.items():
                outgoing_events.append((event_dict['event'], target_state))
        
        return outgoing_events

    def get_navigation_steps(self, from_state, to_state):
        if from_state is None or to_state is None:
            return None
        try:
            steps = []
            from_state_str = from_state.state_str
            to_state_str = to_state.state_str
            state_strs = nx.shortest_path(G=self.G, source=from_state_str, target=to_state_str)
            if not isinstance(state_strs, list) or len(state_strs) < 2:
                self.logger.warning(f"Error getting path from {from_state_str} to {to_state_str}")
            start_state_str = state_strs[0]
            for state_str in state_strs[1:]:
                edge = self.G[start_state_str][state_str]
                edge_event_strs = list(edge["events"].keys())
                if self.random_input:
                    random.shuffle(edge_event_strs)
                start_state = self.G.nodes[start_state_str]['state']
                event = edge["events"][edge_event_strs[0]]["event"]
                steps.append((start_state, event))
                start_state_str = state_str
            return steps
        except Exception as e:
            self.logger.warning(f"Cannot find a path from {from_state.state_str} to {to_state.state_str}")
            return None

    # def get_simplified_nav_steps(self, from_state, to_state):
    #     nav_steps = self.get_navigation_steps(from_state, to_state)
    #     if nav_steps is None:
    #         return None
    #     simple_nav_steps = []
    #     last_state, last_action = nav_steps[-1]
    #     for state, action in nav_steps:
    #         if state.structure_str == last_state.structure_str:
    #             simple_nav_steps.append((state, last_action))
    #             break
    #         simple_nav_steps.append((state, action))
    #     return simple_nav_steps

    def get_G2_nav_steps(self, from_state, to_state):
        if from_state is None or to_state is None:
            return None
        from_state_str = from_state.structure_str
        to_state_str = to_state.structure_str
        try:
            nav_steps = []
            state_strs = nx.shortest_path(G=self.G2, source=from_state_str, target=to_state_str)
            if not isinstance(state_strs, list) or len(state_strs) < 2:
                return None
            start_state_str = state_strs[0]
            for state_str in state_strs[1:]:
                edge = self.G2[start_state_str][state_str]
                edge_event_strs = list(edge["events"].keys())
                start_state = random.choice(self.G2.nodes[start_state_str]['states'])
                event_str = random.choice(edge_event_strs)
                event = edge["events"][event_str]["event"]
                nav_steps.append((start_state, event))
                start_state_str = state_str
            if nav_steps is None:
                return None
            # return nav_steps
            # simplify the path
            simple_nav_steps = []
            last_state, last_action = nav_steps[-1]
            for state, action in nav_steps:
                if state.structure_str == last_state.structure_str:
                    simple_nav_steps.append((state, last_action))
                    break
                simple_nav_steps.append((state, action))
            return simple_nav_steps
        except Exception as e:
            return None

    @classmethod
    def load_utg(cls, utg_data_root, keep_self_loops=None, logger=None):
        """
        从 UTG 数据目录加载 UTG 对象
        
        :param utg_data_root: UTG数据根目录（包含{cls.JSON_NAME}的目录）
        :param keep_self_loops: 是否保留自循环
        :param logger: 可选的日志记录器
        :return: 加载的 UTG 对象
        """
        logger = logger or logging.getLogger(cls.__name__)
        
        # 构建 {cls.JSON_NAME} 路径
        utg_json_path = os.path.join(utg_data_root, cls.JSON_NAME)
        
        if not os.path.exists(utg_json_path):
            raise FileNotFoundError(f"{cls.JSON_NAME} not found in {utg_data_root}")
        
        lock_file_path = os.path.join(utg_data_root, cls.LOCK_FILE_NAME)
        lock = FileLock(lock_file_path, timeout=10, mode=0o666)
        with lock:
            # 1. 读取 {cls.JSON_NAME}
            with open(utg_json_path, 'r', encoding='utf-8') as f:
                utg_data = json.load(f)

            # 2. 加载状态对象
            states_dict = cls._load_device_states(utg_data_root, logger)
        
        # 3. 创建 UTG 对象
        utg = cls._create_utg_from_data(utg_data, utg_data_root, keep_self_loops)
 
        # 4. 重建图结构
        cls._rebuild_graph(utg, utg_data, states_dict, logger)
        
        return utg
    
    @classmethod
    def _create_utg_from_data(cls, utg_data, output_dir, keep_self_loops=None):
        """从 JSON 数据创建 UTG 对象"""
        # 从 JSON 数据提取构造参数
        device_serial = utg_data.get('device_serial', '')
        device_model_number = utg_data.get('device_model_number', '')
        device_sdk_version = utg_data.get('device_sdk_version', '')
        app_signature = utg_data.get('app_signature', '')
        app_package = utg_data.get('app_package', '')
        app_main_activity = utg_data.get('app_main_activity', '')
        app_num_total_activities = utg_data.get('app_num_total_activities', 0)
        
        if keep_self_loops is None:
            # 根据是否存在 num_ineffective_events 判断 keep_self_loops 设置
            keep_self_loops = 'num_ineffective_events' in utg_data
        
        # 创建 UTG 对象
        utg = cls(
            output_dir=output_dir,
            device_serial=device_serial,
            device_model_number=device_model_number,
            device_sdk_version=device_sdk_version,
            app_signature=app_signature,
            app_package=app_package,
            app_main_activity=app_main_activity,
            app_num_total_activities=app_num_total_activities,
            random_input=False,
            keep_self_loops=keep_self_loops
        )
        
        # 恢复时间信息
        test_date_str = utg_data.get('test_date', '')
        if test_date_str:
            utg.start_time = datetime.datetime.strptime(test_date_str, "%Y-%m-%d %H:%M:%S")
        
        return utg
    
    @classmethod
    def _load_device_states(cls, utg_data_root, logger):
        """加载所有状态文件"""
        from .device_state import DeviceState
        
        states_dict = {}
        states_dir = os.path.join(utg_data_root, 'states')
        
        if not os.path.exists(states_dir):
            logger.warning(f"States directory not found: {states_dir}")
            return states_dict
        
        # 遍历所有状态文件
        for filename in os.listdir(states_dir):
            if filename.startswith('state_') and filename.endswith('.json'):
                state_path = os.path.join(states_dir, filename)
                try:
                    state = DeviceState.load_from_file(state_path, output_dir=utg_data_root, logger=logger)
                    if state:
                        states_dict[state.state_str] = state
                except Exception as e:
                    logger.error(f"Failed to load state {filename}: {e}")
        
        return states_dict
    
    @classmethod
    def _rebuild_graph(cls, utg, utg_data, states_dict, logger):
        """重建图结构"""
        # 清空现有图
        utg.G.clear()
        utg.G2.clear()

        # 收集所有事件和对应的state, 按照event_id排序后重建event
        all_events = []
        for edge_data in utg_data['edges']:
            from_state_str = edge_data['from']
            to_state_str = edge_data['to']
            
            if from_state_str in states_dict and to_state_str in states_dict:
                from_state = states_dict[from_state_str]
                to_state = states_dict[to_state_str]
                
                # 收集所有事件信息
                for event_info in edge_data['events']:
                    event = cls._restore_event(event_info, from_state, logger)
                    if event:
                        event_id = event_info.get('event_id', -1)
                        all_events.append((event_id, event, from_state, to_state))
        
        # 按照event_id排序，然后依次添加转换
        # 这样保持和原始构造过程一致，让add_transition自动计算event_id
        all_events.sort(key=lambda x: x[0])
        for _, event, from_state, to_state in all_events:
            utg.add_transition(event, from_state, to_state, skip_output=True)
       
        # 添加独立节点并添加label, FIRST 和 LAST 节点
        for node_data in utg_data.get('nodes', []):
            state_str = node_data.get('id', '')
            label_str = node_data.get('label', '')
            label_parts = cls._parse_node_label(label_str)
            label_meta = node_data.get('label_meta', None)

            if state_str not in utg.G.nodes():
                utg.add_node(states_dict[state_str], skip_output=True)

            utg.set_label(state_str, label_parts)
            if isinstance(label_meta, dict):
                utg.set_label_meta(state_str, label_meta)

            if '<FIRST>' in label_str:
                utg.first_state = states_dict[state_str]
            if '<LAST>' in label_str:
                utg.last_state = states_dict[state_str]
        
    
    @classmethod
    def _restore_event(cls, event_info, from_state, logger):
        """从UTG数据恢复事件对象"""
        from .input_event import InputEvent
        
        # 使用 event_str 来恢复事件
        event_str = event_info.get('event_str', '')
        if not event_str:
            logger.error(f"Missing event_str in event_info: {event_info}")
            return None
            
        try:
            # 使用 from_event_str 方法恢复完整的事件对象，传递 from_state 以支持视图查找
            restored_event = InputEvent.from_event_str(event_str, from_state)
            if restored_event:
                logger.debug(f"Successfully restored event from event_str: {event_str}")
                return restored_event
            else:
                logger.error(f"Failed to parse event_str: {event_str}")
                return None
        except Exception as e:
            logger.error(f"Error parsing event_str '{event_str}': {e}")
            return None

    @classmethod
    def _parse_node_label(cls, label):
        """从节点标签中解析出原始的 labels"""
        # label 格式: short_activity_name\n{label1}\n{label2}...\n<FIRST>|<LAST>
        label_parts = label.split('\n')
        labels = [part for idx, part in enumerate(label_parts) if idx > 0 and part not in ['<FIRST>', '<LAST>']]
        return labels
