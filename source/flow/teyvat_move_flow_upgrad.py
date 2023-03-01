from source.util import *
from source.common import flow_state as ST, timer_module, static_lib
import source.flow.flow_code as FC
from source.funclib import big_map, generic_lib
from source.manager import scene_manager, posi_manager, asset
from source.interaction.interaction_core import itt
from source.controller import teyvat_move_controller
from funclib.err_code_lib import ERR_PASS, ERR_STUCK
from source.funclib import scene_lib, movement
from source.interaction.minimap_tracker import tracker
from source.flow.flow_template import FlowConnector, FlowController, FlowTemplate, EndFlowTenplate

IN_MOVE = 0
IN_FLY = 1
IN_WATER = 2
IN_CLIMB = 3


class TeyvatMoveFlowConnector(FlowConnector):
    def __init__(self):
        super().__init__()
        self.tmc = teyvat_move_controller.TeyvatMoveController()
        self.checkup_stop_func = None
        self.stop_rule = 0
        self.tmc.set_stop_rule(self.stop_rule)
        self.jump_timer = timer_module.Timer()
        self.current_state = ST.INIT_TEYVAT_TELEPORT
        self.target_posi = [0, 0]
        self.reaction_to_enemy = 'RUN'
        self.motion_state = IN_MOVE

        self.MODE = "PATH"
        self.path_list = []
        self.path_index = 0
        self.to_next_posi_offset = 1.0*5 # For CVAT's low precision
        self.special_keys_posi_offset = 1.5

        self.priority_waypoints = load_json("priority_waypoints.json", default_path='assets')
        self.priority_waypoints_array = []
        for i in self.priority_waypoints:
            self.priority_waypoints_array.append(i["position"])
        self.priority_waypoints_array = np.array(self.priority_waypoints_array)
    
    def reset(self):
        self.tmc.reset_err_code()
        self.current_state = ST.INIT_TEYVAT_TELEPORT
        self.target_posi = [0, 0]
        self.motion_state = IN_MOVE


    

    

class TeyvatTeleport(FlowTemplate):
    def __init__(self, upper:TeyvatMoveFlowConnector):
        super().__init__(upper, flow_id=ST.INIT_TEYVAT_TELEPORT, next_flow_id=ST.INIT_TEYVAT_MOVE)
        self.upper = upper

    def state_init(self):
        self.upper.tmc.set_parameter(self.upper.target_posi)
        self._next_rfc()

    def state_before(self):
        scene_lib.switch_to_page(scene_manager.page_main, self.upper.checkup_stop_func)
        self._next_rfc()

    def state_in(self):
        """
        这个代码是垃圾 之后大地图坐标识别模块接入之后要重写
        """
        curr_posi = tracker.get_position()
        scene_lib.switch_to_page(scene_manager.page_bigmap, self.upper.checkup_stop_func)
        # Obtain the coordinates of the transmission anchor closest to the target coordinates
        tw_posi = big_map.nearest_big_map_tw_posi(curr_posi, self.upper.target_posi, self.upper.checkup_stop_func, include_gs=True, include_dm=True) # 获得距离目标坐标最近的传送锚点坐标 
        tw_posi2 = big_map.nearest_big_map_tw_posi(curr_posi, self.upper.target_posi, self.upper.checkup_stop_func, include_gs=False, include_dm=True) # 获得距离目标坐标最近的传送锚点坐标 
        if list(tw_posi) != list(tw_posi2):
            check_mode = 0 # Statues of the seven
        else:
            check_mode = 1 # Teleport Waypoint
        if len(tw_posi)==0:
            logger.info(t2t("获取传送锚点失败，正在重试"))
            big_map.reset_map_size()
        itt.move_and_click([tw_posi[0], tw_posi[1]])
        # global_itt.delay(0.2)
        # global_itt.left_click()
        # global_itt.delay(0.6)
        temporary_timeout_1 = timer_module.TimeoutTimer(25)
        while 1:
            if self.upper.checkup_stop_func():
                break
            
            if itt.appear_then_click(asset.bigmap_tp) : break
            if check_mode == 1:
                logger.debug("tp to tw")
                itt.appear_then_click(asset.CSMD)
            else:
                logger.debug("tp to ss")
                itt.appear_then_click(asset.QTSX)
            if temporary_timeout_1.istimeout():
                scene_lib.switch_to_page(scene_manager.page_bigmap, self.upper.checkup_stop_func)
                itt.move_and_click([tw_posi[0], tw_posi[1]])
                temporary_timeout_1.reset()
            time.sleep(0.5)

        itt.move_and_click([posi_manager.tp_button[0], posi_manager.tp_button[1]], delay=1)
        
        while not itt.get_img_existence(asset.ui_main_win):
            if self.upper.checkup_stop_func():
                break
            time.sleep(1)
        while tracker.in_excessive_error:
            if self.upper.checkup_stop_func():
                break
            time.sleep(1)
        self._next_rfc()

    def state_after(self):
        """也是垃圾"""
        scene_lib.switch_to_page(scene_manager.page_main, self.upper.checkup_stop_func)
        time.sleep(2)
        curr_posi = tracker.get_position()
        scene_lib.switch_to_page(scene_manager.page_bigmap, self.upper.checkup_stop_func)
        tw_posi = big_map.nearest_teyvat_tw_posi(curr_posi, self.upper.target_posi, self.upper.checkup_stop_func)
        p1 = euclidean_distance(self.upper.target_posi, tw_posi)
        p2 = euclidean_distance(self.upper.target_posi, curr_posi)
        if p1 < p2:
            scene_lib.switch_to_page(scene_manager.page_main, self.upper.checkup_stop_func)
            itt.delay(1)
            self.rfc = FC.BEFORE
        else:
            self._next_rfc()

    def state_end(self):
        scene_lib.switch_to_page(scene_manager.page_main, self.upper.checkup_stop_func)
        return super().state_end()

class TeyvatMoveCommon():
    def __init__(self):
        self.motion_state = IN_MOVE

    def switch_motion_state(self):
        if itt.get_img_existence(asset.motion_climbing):
            self.motion_state = IN_CLIMB
        elif itt.get_img_existence(asset.motion_flying):
            self.motion_state = IN_FLY
        elif itt.get_img_existence(asset.motion_swimming):
            self.motion_state = IN_WATER
        else:
            self.motion_state = IN_MOVE
    
class TeyvatMove_Automatic(FlowTemplate, TeyvatMoveCommon):
    def __init__(self, upper: TeyvatMoveFlowConnector):
        FlowTemplate.__init__(self, upper, flow_id=ST.INIT_TEYVAT_MOVE, next_flow_id=ST.END_TEYVAT_MOVE_PASS)
        TeyvatMoveCommon.__init__(self)
        self.upper = upper

    def _calculate_next_priority_point(self, currentp, targetp):
        float_distance = 35
        # 计算当前点到所有优先点的曼哈顿距离
        md = manhattan_distance_plist(currentp, self.upper.priority_waypoints_array)
        nearly_pp_arg = np.argsort(md)
        # 计算当前点到距离最近的50个优先点的欧拉距离
        nearly_pp = self.upper.priority_waypoints_array[nearly_pp_arg[:50]]
        ed = euclidean_distance_plist(currentp, nearly_pp)
        # 将点按欧拉距离升序排序
        nearly_pp_arg = np.argsort(ed)
        nearly_pp = nearly_pp[nearly_pp_arg]
        # 删除距离目标比现在更远的点
        fd = euclidean_distance_plist(targetp, nearly_pp)
        c2t_distance = euclidean_distance(currentp, targetp)
        nearly_pp = np.delete(nearly_pp, (np.where(fd+float_distance >= (c2t_distance) )[0]), axis=0)
        # 获得最近点
        if len(nearly_pp) == 0:
            return targetp
        closest_pp = nearly_pp[0]
        '''加一个信息输出'''
        # print(currentp, closest_pp)
        return closest_pp

    def state_init(self):
        self.upper.tmc.continue_threading()
        return super().state_init()

    def state_in(self):
        self.switch_motion_state()
        
        self.current_posi = tracker.get_position()
        p1 = self._calculate_next_priority_point(self.current_posi, self.upper.target_posi)
        # print(p1)
        movement.change_view_to_posi(p1, self.upper.checkup_stop_func)
        if (not static_lib.W_KEYDOWN):
            itt.key_down('w')
            
        if len(tracker.history_posi) >= 29:
            p1 = tracker.history_posi[0][1:]
            p2 = tracker.history_posi[-1][1:]
            if euclidean_distance(p1,p2)<=30:
                logger.warning("检测到移动卡住，正在退出")
                self._set_nfid(ST.END_TEYVAT_MOVE_STUCK)
                self._next_rfc()
        
        if self.upper.stop_rule == 0:
            if euclidean_distance(self.upper.target_posi, tracker.get_position())<=10:
                logger.info(t2t("已到达目的地附近，本次导航结束。"))
                itt.key_up('w')
                self._set_nfid(ST.END_TEYVAT_MOVE_PASS)
                self._next_rfc()
        elif self.upper.stop_rule == 1:
            if generic_lib.f_recognition():
                self._set_nfid(ST.END_TEYVAT_MOVE_PASS)
                self._next_rfc()
                logger.info(t2t("已到达F附近，本次导航结束。"))
                itt.key_up('w')
            
        if self.motion_state == IN_CLIMB:
            jump_dt = 5
        elif self.motion_state == IN_MOVE:
            jump_dt = 2
        else:
            jump_dt = 99999
        if self.upper.jump_timer.get_diff_time() >= jump_dt:
            self.upper.jump_timer.reset()
            itt.key_press('spacebar')
            time.sleep(0.3)
            itt.key_press('spacebar') # fly

class TeyvatMove_FollowPath(FlowTemplate, TeyvatMoveCommon):
    def __init__(self, upper: TeyvatMoveFlowConnector):
        FlowTemplate.__init__(self, upper, flow_id=ST.INIT_TEYVAT_MOVE, next_flow_id=ST.END_TEYVAT_MOVE_PASS)
        TeyvatMoveCommon.__init__(self)

        self.upper = upper
        self.curr_path_index = 0
        self.special_key_points = None
        
        self.curr_path = []
        self.curr_path_index = 0
        
    def _exec_special_key_points(self):
        ret_list = []
        for i in self.upper.path_list[self.upper.path_index]["special_keys"]:
            ret_list.append(i["position"])
        self.special_key_points = ret_list
    
    def _do_special_key(self, curr_posi):
        """执行special key

        Args:
            curr_posi (_type_): _description_
        """
        if self.special_key_points == None:
            self._exec_special_key_points()
        if quick_euclidean_distance_plist(curr_posi, self.special_key_points).min() <= self.upper.special_keys_posi_offset:
            for i in self.upper.path_list[self.upper.path_index]["special_keys"]:
                if euclidean_distance(i["position"], curr_posi) <= self.upper.special_keys_posi_offset:
                    itt.key_press(i["key_name"])
    
    def state_before(self):
        self.curr_path = self.upper.path_list[self.upper.path_index]["position_list"]
        self.curr_path_index = 0
        itt.key_down('w')
        self._next_rfc()
    
    def state_in(self):
        target_posi = self.curr_path[self.curr_path_index]["position"]
        curr_posi = tracker.get_position()
        if euclidean_distance(target_posi, curr_posi) <= self.upper.to_next_posi_offset:
            if len(self.curr_path) - 1 > self.curr_path_index:
                self.curr_path_index += 1
                logger.debug(f"index {self.curr_path_index} posi {self.curr_path[self.curr_path_index]}")
            else:
                logger.info("path end")
                self._next_rfc()
        self._do_special_key(curr_posi)
        movement.change_view_to_posi(target_posi, stop_func = self.upper.checkup_stop_func)
        
            
    def state_after(self):
        if self.upper.path_list[self.upper.path_index]["is_activate_pickup"] == False:
            self.next_flow_id = self.flow_id
        else:
            pass
        if len(self.upper.path_list)-1 > self.upper.path_index:
            self.upper.path_index += 1
        else:
            logger.info("all path end")
        self._next_rfc()

class TeyvatMoveStuck(EndFlowTenplate):
    def __init__(self, upper: FlowConnector):
        super().__init__(upper, flow_id=ST.END_TEYVAT_MOVE_STUCK, err_code_id=ERR_STUCK)

class TeyvatMovePass(EndFlowTenplate):
    def __init__(self, upper: FlowConnector):
        super().__init__(upper, flow_id=ST.END_TEYVAT_MOVE_PASS, err_code_id=ERR_PASS)

class TeyvatMoveFlowController(FlowController):
    def __init__(self):
        super().__init__(flow_connector = TeyvatMoveFlowConnector(), current_flow_id = ST.INIT_TEYVAT_TELEPORT)
        self.flow_connector = self.flow_connector # type: TeyvatMoveFlowConnector
        self._add_sub_threading(self.flow_connector.tmc)
        self.get_while_sleep = self.flow_connector.get_while_sleep

        self.append_flow(TeyvatTeleport(self.flow_connector))
        if False:
            self.append_flow(TeyvatMove_Automatic(self.flow_connector))
        else:
            self.append_flow(TeyvatMove_FollowPath(self.flow_connector))
        
        self.append_flow(TeyvatMoveStuck(self.flow_connector))
        self.append_flow(TeyvatMovePass(self.flow_connector))

    def reset(self):
        self.flow_connector.reset()
    
    def get_working_statement(self):
        return not self.pause_threading_flag
    
    def set_target_posi(self, tp:list):
        self.flow_connector.target_posi = tp

    def set_parameter(self,
                      stop_rule:int = None,
                      target_posi:list = None,
                      MODE:str = None,
                      to_next_posi_offset:float = None,
                      special_keys_posi_offset:float = None
                      ):
        if stop_rule != None:
            self.flow_connector.stop_rule = stop_rule
        if target_posi != None:
            self.flow_connector.target_posi = target_posi
        if MODE != None:
            self.flow_connector.MODE = MODE
        if to_next_posi_offset != None:
            self.flow_connector.to_next_posi_offset = to_next_posi_offset
        if special_keys_posi_offset != None:
            self.flow_connector.special_keys_posi_offset = special_keys_posi_offset
        