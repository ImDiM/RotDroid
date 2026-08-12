
import argparse
import json
import logging
import math
import random
import subprocess
from time import sleep, time
import os
import adbutils
import uiautomator2 as u2
from typing import List,Union
from collections import Counter, defaultdict


from explorer  import UIStateEdge, UIStateNode,ActivityNode, state, RandomExplorer
from utils import EmulatorLauncher,get_package,save_hierachy, config_log, \
    save_screenshot,append_jsonl,encode_image, read_jsonl,get_image_size

from explorer import HeuristicExplorer,State,Action,UIGraph, SRS,click_permision,click_closeapp
from utils.apk_util import install_app, A11Y_SERVICES,  disable_accessibility_services, whitelist_battery_optimization
from utils.file_utils import clear_dir
from explorer import mark_shape,get_markinfo

from finetune import extract_defect_info
from models import ModelFactory, VLMMessager

from configs import class_2_prompt,class_multi_prompt


def parse_args():
    parser = argparse.ArgumentParser(description="Run RotationDroid exploration.")
    parser.add_argument("--apks-dir", default="apks", help="Directory containing APK/XAPK files.")
    parser.add_argument("--apk-list-file", default=None, help="Text file that contains one APK/XAPK path per line.")
    parser.add_argument("--out-dir", default="out_rotdroid_test")
    parser.add_argument("--device-names", nargs=2, default=["Pixel_6a_API_33", "Pixel_6a_API_33_2"])
    parser.add_argument("--android-port", nargs=2, default=["5554", "5556"])
    parser.add_argument("--algo", default="random")
    parser.add_argument("--iter-cnt", type=int, default=15000)
    parser.add_argument("--srs-ratio", type=float, default=0.1)
    parser.add_argument("--app-time-limit-minutes", type=float, default=30.0)
    parser.add_argument("--blacklist-path", default="configs/package_blacklist.jsonl")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--save-filename", default="detect_result.jsonl")
    parser.add_argument("--log-file", default="logger/rotdroid_test")
    parser.add_argument("--model-name", default="model-rotvl8b")
    parser.add_argument("--model-base-url")
    parser.add_argument("--model-api-key")
    parser.add_argument("--temperature", type=float, default=0.2)
    parser.add_argument("--max-token", type=int, default=500)
    return parser.parse_args()


def resolve_apk_path(raw_path: str, apk_list_file: str) -> str:
    if os.path.isabs(raw_path):
        return raw_path

    list_dir = os.path.dirname(os.path.abspath(apk_list_file))
    direct_candidate = os.path.abspath(os.path.join(list_dir, raw_path))
    if os.path.exists(direct_candidate):
        return direct_candidate

    return os.path.abspath(os.path.join(os.path.dirname(list_dir), raw_path))


def collect_apk_paths(apks_dir: str, apk_list_file=None) -> List[str]:
    if apk_list_file:
        apk_paths = []
        with open(apk_list_file, "r", encoding="utf-8") as f:
            for line in f:
                raw_path = line.strip()
                if not raw_path or raw_path.startswith("#"):
                    continue
                apk_path = resolve_apk_path(raw_path, apk_list_file)
                if apk_path.endswith('.apk') or apk_path.endswith('.xapk'):
                    apk_paths.append(apk_path)
        return apk_paths

    apk_paths = []
    for apk_name in os.listdir(apks_dir):
        apk_path = os.path.join(apks_dir, apk_name)
        if apk_path.endswith('.apk') or apk_path.endswith('.xapk'):
            apk_paths.append(apk_path)
    return apk_paths


def connect_device_with_retry(serial: str, boot_timeout: int = 180, retries: int = 6, retry_interval: int = 5):
    logging.info(f"[{serial}] Waiting for stable device connection...")
    subprocess.run(['adb', '-s', serial, 'wait-for-device'], check=True, timeout=boot_timeout)

    start_time = time()
    while time() - start_time < boot_timeout:
        try:
            boot_completed = subprocess.check_output(
                ['adb', '-s', serial, 'shell', 'getprop', 'sys.boot_completed'],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            package_ready = subprocess.check_output(
                ['adb', '-s', serial, 'shell', 'pm', 'path', 'android'],
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
            if boot_completed == '1' and package_ready.startswith('package:'):
                break
        except subprocess.CalledProcessError:
            pass
        sleep(2)
    else:
        raise RuntimeError(f"[{serial}] Android framework did not become ready within {boot_timeout}s")

    subprocess.run(['adb', '-s', serial, 'shell', 'input', 'keyevent', '82'], check=False, capture_output=True)
    sleep(2)

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            logging.info(f"[{serial}] Attempting uiautomator2 connection ({attempt}/{retries})...")
            device = u2.connect(serial)
            _ = device.info
            logging.info(f"[{serial}] uiautomator2 is ready.")
            return device
        except (u2.exceptions.ConnectError, u2.exceptions.LaunchUiAutomationError, adbutils.errors.AdbError, RuntimeError) as exc:
            last_error = exc
            logging.warning(f"[{serial}] uiautomator2 not ready yet: {exc}")
            sleep(retry_interval)

    raise RuntimeError(f"[{serial}] Failed to start uiautomator2 after {retries} attempts: {last_error}")




def rotdroid(model_config, apks_dir,
             device_names=['Medium_Phone_API_31','Medium_Phone_API_31_2'],android_port=['5554','5556'],
             algo='heuristic',iter_cnt=15, srs_ratio=1, 
             app_time_limit_minutes=30,
             apk_list_file=None,
             blacklist_path:List[str]=[],clear=False,
             out_dir='out_rotdroid', save_filename='detect_result.jsonl'):
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)    
        
    if clear:
        clear_dir(out_dir)
        
    emulator_explore = None
    emulator_pairs = None

    if os.path.exists(blacklist_path):
        package_blacklist = [entry['package'] for entry in read_jsonl(blacklist_path)]
    else:
        package_blacklist = []

    try:
        emulator_explore=EmulatorLauncher(device_name=device_names[0], android_port=android_port[0],gpu_mode='swiftshader_indirect') 
        emulator_pairs=EmulatorLauncher(device_name=device_names[1], android_port=android_port[1],gpu_mode='swiftshader_indirect') 
        sleep(8)
        
        device = connect_device_with_retry(f"emulator-{android_port[0]}")
        device_srs = connect_device_with_retry(f"emulator-{android_port[1]}")
        sleep(3)

        disable_accessibility_services(device)
        disable_accessibility_services(device_srs)
        sleep(2)  
        
        apk_paths = collect_apk_paths(apks_dir, apk_list_file)
        logging.info(f"Loaded {len(apk_paths)} apk paths for exploration.")
        for apk_path in apk_paths:
            try:
                apk_name = os.path.basename(apk_path)
                package_name,main_activity = get_package(apk_path)
                
                if package_name in package_blacklist:
                    logging.info(f"Package {package_name} is in the blacklist, skipping...")
                    continue
                
                if package_name in os.listdir(out_dir):
                    if os.path.exists(os.path.join(out_dir,package_name,'utg')):
                        logging.info(f"Package {package_name} already explored, skipping...")
                        continue
                    else:
                        clear_dir(os.path.join(out_dir,package_name))
                        
                logging.info(f"\n\nExploring package: {package_name} from {apk_name}")
                
                
                try:
                    install_app(f"emulator-{android_port[0]}", apk_path)
                    install_app(f"emulator-{android_port[1]}", apk_path)
                
                except Exception as e:
                    error_msg = str(e)
                    logging.error(f"[{package_name}] install failure, skip : {error_msg}")
                    
                    blacklist_entry = {
                        "package": package_name,
                        "reason": f"adb install failure: {error_msg}"
                    }
                    
                    os.makedirs(os.path.dirname(blacklist_path), exist_ok=True)
                    append_jsonl(blacklist_path, blacklist_entry)
                    logging.info(f"add {package_name} to blacklist {blacklist_path}")

                    continue

                sleep(3)
                logging.info(f"{package_name} install success")
                whitelist_battery_optimization(device, package_name)
                whitelist_battery_optimization(device_srs, package_name)
                
                device.app_start(package_name)
                sleep(3)
                logging.info(package_name+' app start')
                sleep(2)

                last_state = None    
                action= Action(action_type='main',package=package_name)
                utg=UIGraph(package_name)


                if algo == 'heuristic':
                    explorer = HeuristicExplorer(device=device, utg=utg, out_dir=os.path.join(out_dir,'heuristic'))
                elif algo == 'random':
                    explorer = RandomExplorer(device=device, utg=utg, out_dir=os.path.join(out_dir,'random'))
                else: 
                    raise ValueError(f"Unsupported algorithm: {algo}.")
                
                unfocus_cnt=0
                no_newstate_cnt=0
                last_state_cnt=0
                stop_threshold=5
                app_start_time = time()
                app_time_limit_seconds = app_time_limit_minutes * 60
                
                pairs_dir=os.path.join(out_dir,package_name,'pairs')

                for i in range(iter_cnt):
                    if time() - app_start_time >= app_time_limit_seconds:
                        logging.info(f"App {package_name} reached time limit: {app_time_limit_minutes} minutes, stop exploration.")
                        break

                    if device.app_current().get('package')!= package_name:
                        unfocus_cnt += 1
                        if device.app_current().get('package') in A11Y_SERVICES:
                            disable_accessibility_services()
                        if device.app_current().get('package') == 'com.google.android.permissioncontroller':
                            click_permision(device)
                            
                    else:
                        click_closeapp(device)
                        unfocus_cnt=0
                    
                    cur_state=  State(device,os.path.join(out_dir,package_name,'curstate'))      
                    cur_statenode,is_newstate=utg.add_state(cur_state)
                    edge,new_edge=utg.add_stateedge(last_state,cur_statenode, action)
                    
                    if len(utg.states)==last_state_cnt:
                        no_newstate_cnt +=1
                        logging.info(f"no_newstate_cnt={no_newstate_cnt}")
                    else:
                        no_newstate_cnt=0
                                            
                    pair_filename='pairs.jsonl'
                    state_cnt, srs_cnt,success_srs_cnt=construct_pairs(device=device, device_srs=device_srs, apk_path=apk_path,package=package_name,
                                    cur_state=cur_statenode,edge=edge, is_newstate=is_newstate,new_edge=new_edge,
                                    action=action, utg=utg,ratio=srs_ratio,
                                    output_dir=pairs_dir, pair_filename=pair_filename)
                    logging.info(f"iter_i={i}: state_cnt: {state_cnt}, srs_cnt: {srs_cnt}, success_srs_cnt: {success_srs_cnt}\n")

                    if unfocus_cnt >=3 or device.app_current().get('package')=='com.google.android.apps.nexuslauncher':
                        logging.info(f"App {package_name} lost focus, execute main...")
                        action=Action(action_type='main',package=package_name)
                        action.execute(device)
                    else:
                        action = explorer.explore(cur_state)

                    last_state=cur_statenode
                    last_state_cnt=len(utg.states)

                    candidate_actions = cur_state.get_candidate_actions()
                    mark_l=[]
                    for a in candidate_actions:
                        color='blue'

                        if a.action_type in ['main','home', 'back']:
                            w,h=get_image_size(cur_state.screenshot_path) 
                            action_b=[0,0,w,h] 
                            mark_info=get_markinfo(action_b,a.action_type,color,'point')
                        elif a.action_type in  ['click', 'long_click', 'scroll_up', 'scroll_down','type']:
                            if a.widget:
                                action_b=a.widget.bounds
                            elif a.position:
                                action_b=[a.position[0],a.position[1],a.position[0],a.position[1]]
                            else:
                                logging.info('Error: no position')
                            mark_info=get_markinfo(action_b,a.action_type,color,'rectangle')
                        else:
                            logging.info('Error: error action')
                            logging.info(a)
                        mark_l.append(mark_info)

                    color='green'
                    if action:
                        if action.action_type in ['main','home', 'back']:
                            w,h=get_image_size(cur_state.screenshot_path) 
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

                        mark_l.append(mark_info)
                    else:
                        logging.info('No action executed in explorer')

                    mark_shape(cur_state.screenshot_path,cur_state.screenshot_path.replace('.png','_mark.png'), mark_l)
                
                succ_pair_filename='success_pairs.jsonl'
                have_success=merge_pairs_in_package(package_dir=os.path.join(out_dir,package_name),output_path=os.path.join(pairs_dir,succ_pair_filename))
                if have_success:
                    detect_pairs(model_config=model_config, pairs_jpath=os.path.join(pairs_dir,succ_pair_filename),
                                pairs_index=0, save_jpath=os.path.join(pairs_dir,save_filename))
                else:
                    logging.info(f"No successful pairs for package {package_name}, skip detect_pairs.")

                utg.save_graph(os.path.join(out_dir,package_name,'utg'))                                                                                                                                                                                                                                                   
                utg.draw_graph(os.path.join(out_dir,package_name,'utg'))
                utg.draw_graph_with_png(os.path.join(out_dir,package_name,'utg'))
                utg.draw_grouped(os.path.join(out_dir,package_name,'utg'))
                utg.draw_grouped_with_png(os.path.join(out_dir,package_name,'utg'))

                device.app_stop(package_name)
                logging.info(package_name+' app stop on device')
                device.app_uninstall(package_name) 
                sleep(3)
                logging.info(package_name+' app uninstall on device')

                device_srs.app_stop(package_name)
                logging.info(package_name+' app stop on device_srs')
                device_srs.app_uninstall(package_name) 
                sleep(3)
                logging.info(package_name+' app uninstall on device_srs')

            except (u2.exceptions.ConnectError, adbutils.errors.AdbError, ConnectionError, RuntimeError) as e:
                logging.error(f"{package_name} exception: {e}")
                logging.info(f"restart simulator ...")

                emulator_explore.restart()
                emulator_pairs.restart()
                sleep(10)
                
                device = connect_device_with_retry(f"emulator-{android_port[0]}")
                device_srs = connect_device_with_retry(f"emulator-{android_port[1]}")
                sleep(3)

                disable_accessibility_services(device)
                disable_accessibility_services(device_srs)
                sleep(2)  
                continue 


    except (RuntimeError, EnvironmentError, KeyboardInterrupt) as e:
        logging.error(f": {e}")

    finally:
        sleep(60)
        if emulator_explore:
            logging.info("close simulator...")
            emulator_explore.stop()
        if emulator_pairs:
            logging.info("close simulator...")
            emulator_pairs.stop()



def construct_pairs(device:u2.Device,device_srs:u2.Device, apk_path, package:str,
                    cur_state:UIStateNode,edge:UIStateEdge,
                    is_newstate:bool,new_edge:bool, 
                    action:Action, utg:UIGraph, ratio,
                    output_dir:str='out_detectpairs',pair_filename='detectpairs.jsonl'):
    wait_t=2
    pairs_jpath = os.path.join(output_dir, pair_filename)
    state_cnt=0
    success_srs_cnt=0
    srses=[]
    if new_edge : 
        if is_newstate and cur_state.package == package:
            logging.info(f"New state detected: {cur_state.id}")  
            srses = SRS.get_special_srs(utg, cur_state)
            state_cnt +=1
        else: 
            logging.info(f"New edge detected: {edge.id}")     
            srses = SRS.get_new_srses(utg, edge)
       
        if len(srses)==0:
            logging.info(f"No SRS generated for edge {edge.id}")
            return (state_cnt, 0,0)
        
        target_count = math.ceil(len(srses) * ratio)
        target_count = min(target_count, len(srses))
        original_count = len(srses)
        srses = random.sample(srses, target_count)
        
        logging.info(f"Randomly selected {target_count}/{original_count} srses (ratio={ratio})")
        logging.info(f"len of srses={len(srses)}")
        SRS.draw_srses(srses, os.path.join(output_dir, 'srs_graph'))
        success_srses= []
        pairs_jpath= os.path.join(output_dir, pair_filename)

        package_name,activity = get_package(apk_path)

        for index,srs in enumerate(srses,1):
            logging.info(f'Execute SRS {index}/{len(srses)}, id={srs.id}')
            try:
                device_srs.app_start(package_name)
                sleep(2)
                logging.info(package_name+' app start')
                srs.execute = srs.execute_srs(device_srs, output_dir)
                if srs.execute:
                    success_srses.append(srs)
            except Exception as e:
                logging.info(f"Error occurred while executing SRS {srs.id}: {e}")
            finally:
                append_jsonl(pairs_jpath, srs.to_dict())

                device_srs.app_stop(package_name) 
                logging.info(package_name+' app stop')
                device_srs.app_clear(package_name) 
                logging.info(package_name+' app clear')
                sleep(2)

        success_srs_cnt = len(success_srses)
        logging.info(f"Sucessfully saved {len(srses)} pairs SRS to {pairs_jpath}")

    return (state_cnt, len(srses),success_srs_cnt)

def merge_pairs_in_package(package_dir='out_rotdroid/package',output_path='success_pairs.jsonl'):

    merged_data = {} 
    success_cnt = 0
    fail_cnt = 0

    if not os.path.isdir(package_dir): 
        return False
        
    pairs_jsonl = os.path.join(package_dir, 'pairs', 'pairs.jsonl')

    if not os.path.exists(pairs_jsonl):
        logging.info(f"lack of pairs.jsonl: {package_dir}") 
        return False

    data_list = read_jsonl(pairs_jsonl) 
    for d in data_list:
        if not d.get('execute', False):
            fail_cnt += 1
            continue  
        
        success_cnt += 1
        
        p_id = d.get("p_state", {}).get("id")
        l_id = d.get("l_state", {}).get("id")
        if not p_id or not l_id:
            logging.info(f"skip: {d}")
            continue

        p_screen = d.get("p_state", {}).get("state_info", {}).get("screenshot_path")
        l_screen = d.get("l_state", {}).get("state_info", {}).get("screenshot_path")
        if not p_screen or not l_screen:
            logging.info(f"skip: {d}")
            continue

        pair_key = f"{p_id}_{l_id}"
        
        current_ptype = d.get('srs_type', 'unknown') 

        if pair_key not in merged_data:
            d['srs_type'] = [current_ptype] 
            merged_data[pair_key] = d
        else:
            existing_srs_types = merged_data[pair_key]['srs_type']
            if current_ptype not in existing_srs_types:
                existing_srs_types.append(current_ptype)
            if not merged_data[pair_key].get("p2_state") and d.get("p2_state"):
                merged_data[pair_key]["p2_state"] = d["p2_state"]

    if os.path.exists(output_path):
        os.remove(output_path)

    for final_d in merged_data.values():
        append_jsonl(output_path, final_d)
    
    logging.info(f"save {len(merged_data)} unique pairs to {output_path}")
    if len(merged_data) == 0:
        return False
    
    return True



IGNORED_WIDGET_KEYS = {
    "index",
    "focused",
    "drawing-order",
    "display-id",
    "bounds",
}


def normalize_widget(widget: dict) -> dict:
    bounds_raw = widget.get("bounds", "")
    left = top = right = bottom = 0
    if isinstance(bounds_raw, str) and bounds_raw.startswith("[") and "][" in bounds_raw:
        try:
            first, second = bounds_raw[1:-1].split("][")
            left, top = [int(x) for x in first.split(",")]
            right, bottom = [int(x) for x in second.split(",")]
        except Exception:
            left = top = right = bottom = 0

    norm = {
        "type": widget.get("class", ""),
        "position": [left, top],
        "size": [max(0, right - left), max(0, bottom - top)],
    }

    for key, value in widget.items():
        if key in IGNORED_WIDGET_KEYS:
            continue
        if key == "class":
            norm["class"] = value
        else:
            norm[key] = value
    return norm


def similar_key(widget: dict):
    return (
        widget.get("type", ""),
        tuple(widget.get("position", [0, 0])),
        tuple(widget.get("size", [0, 0])),
    )


def equivalent_key(widget: dict) -> str:
    return json.dumps(widget, sort_keys=True, ensure_ascii=False)


def compare_state_dicts(start_state: dict, end_state: dict) -> dict:
    start_state_dict = (
        start_state.get("state_info", {}).get("ui_info", {}).get("state_dict")
        or start_state.get("state_info", {}).get("state_dict")
        or {}
    )
    end_state_dict = (
        end_state.get("state_info", {}).get("ui_info", {}).get("state_dict")
        or end_state.get("state_info", {}).get("state_dict")
        or {}
    )

    start_widgets = [
        normalize_widget(widget)
        for widget in start_state_dict.get("widgets", [])
    ]
    end_widgets = [
        normalize_widget(widget)
        for widget in end_state_dict.get("widgets", [])
    ]

    start_buckets = defaultdict(list)
    end_buckets = defaultdict(list)

    for widget in start_widgets:
        start_buckets[similar_key(widget)].append(widget)
    for widget in end_widgets:
        end_buckets[similar_key(widget)].append(widget)

    extra = []
    missing = []
    wrong = []

    all_keys = set(start_buckets) | set(end_buckets)
    for key in all_keys:
        start_bucket = start_buckets.get(key, [])
        end_bucket = end_buckets.get(key, [])

        if not start_bucket:
            extra.extend(end_bucket)
            continue
        if not end_bucket:
            missing.extend(start_bucket)
            continue

        start_counter = Counter(equivalent_key(widget) for widget in start_bucket)
        end_counter = Counter(equivalent_key(widget) for widget in end_bucket)
        matched_counter = start_counter & end_counter

        for eq_key, count in list(matched_counter.items()):
            start_counter[eq_key] -= count
            end_counter[eq_key] -= count
            if start_counter[eq_key] == 0:
                del start_counter[eq_key]
            if end_counter[eq_key] == 0:
                del end_counter[eq_key]

        remaining_start = []
        remaining_end = []
        for eq_key, count in start_counter.items():
            remaining_start.extend([json.loads(eq_key)] * count)
        for eq_key, count in end_counter.items():
            remaining_end.extend([json.loads(eq_key)] * count)

        wrong_pair_count = min(len(remaining_start), len(remaining_end))
        for i in range(wrong_pair_count):
            wrong.append(
                {
                    "start_widget": remaining_start[i],
                    "end_widget": remaining_end[i],
                    "scope": remaining_start[i].get("type", ""),
                }
            )

        missing.extend(remaining_start[wrong_pair_count:])
        extra.extend(remaining_end[wrong_pair_count:])

    summary = Counter()
    for widget in extra:
        summary[("Extra", widget.get("type", ""))] += 1
    for widget in missing:
        summary[("Missing", widget.get("type", ""))] += 1
    for item in wrong:
        summary[("Wrong", item.get("scope", ""))] += 1

    return {
        "bug": bool(extra or missing or wrong),
        "extra": extra,
        "missing": missing,
        "wrong": wrong,
        "summary": [
            {"mode": mode, "scope": scope, "count": count}
            for (mode, scope), count in sorted(summary.items())
        ],
    }


def run_llm_image_compare(model, msger, model_config, left_screenshot, right_screenshot) -> dict:
    result = {
        "size_match": False,
        "bug": "",
        "image": "",
        "type": "",
        "bbox_2d": [],
        "reply": "",
        "detail_reply": "",
    }

    start_w, start_h = get_image_size(left_screenshot)
    end_w, end_h = get_image_size(right_screenshot)
    if not (start_w == end_h and start_h == end_w):
        logging.info(
            f"The dimensions do not meet expectations, left={left_screenshot}, right={right_screenshot}, "
            f"start_w={start_w}, start_h={start_h}, end_w={end_w}, end_h={end_h}"
        )
        return result

    result["size_match"] = True
    messages = msger.construct_prompt([left_screenshot, right_screenshot], class_2_prompt)
    logging.info(f'img_path: left_screenshot={left_screenshot},right_screenshot={right_screenshot}')
    logging.info(f'prompt: {class_2_prompt}')
    reply = model.generate_chat(
        messages=messages,
        temperature=model_config['temperature'],
        max_tokens=model_config['max_token']
    )['output']
    result["reply"] = reply
    logging.info(f'reply: {reply}')

    bug_result = extract_defect_info(reply)
    if not bug_result:
        logging.warning("Failed to extract defect information from the response.")
        return result

    result['bug'] = bug_result.get('bug', '')
    if result['bug'] is True:
        messages = msger.construct_prompt([left_screenshot, right_screenshot], class_multi_prompt)
        logging.info(f'img_path: left_screenshot={left_screenshot},right_screenshot={right_screenshot}')
        logging.info(f'prompt: {class_multi_prompt}')
        detail_reply = model.generate_chat(
            messages=messages,
            temperature=model_config['temperature'],
            max_tokens=model_config['max_token']
        )['output']
        result["detail_reply"] = detail_reply
        logging.info(f'reply: {detail_reply}')
        detail_result = extract_defect_info(detail_reply)
        if detail_result:
            result['image'] = detail_result.get('image', '')
            result['type'] = detail_result.get('type', '')
            result['bbox_2d'] = detail_result.get('bbox_2d', [])

    return result

def detect_pairs(model_config, pairs_jpath='out_rotdroid/detectpairs/pairs_todetect.jsonl',pairs_index=0,
                save_jpath='out_rotdroid/detectpairs/detect_result.jsonl'):

    model=ModelFactory.api_model(model_config)
    msger=VLMMessager()

    data=read_jsonl(pairs_jpath)
    for d in data[pairs_index:]:
        new_d={}
        new_d['srs_type']=d['srs_type']
        new_d['id']=d['id']
        p_state = d.get('p_state') or {}
        l_state = d.get('l_state') or {}
        p2_state = d.get('p2_state') or {}

        p_screenshot = p_state.get("state_info", {}).get("screenshot_path")
        l_screenshot = l_state.get("state_info", {}).get("screenshot_path")
        p2_screenshot = p2_state.get("state_info", {}).get("screenshot_path")

        if not p_screenshot or not l_screenshot or not os.path.exists(p_screenshot) or not os.path.exists(l_screenshot):
            logging.warning(f"no exist: p_screenshot={p_screenshot}, l_screenshot={l_screenshot}")
            continue
        
        new_d['p_screenshot']=p_screenshot
        new_d['l_screenshot']=l_screenshot
        new_d['p2_screenshot']=p2_screenshot

        new_d['p_l_compare'] = run_llm_image_compare(model, msger, model_config, p_screenshot, l_screenshot)

        if p2_screenshot and os.path.exists(p2_screenshot):
            new_d['p2_l_compare'] = run_llm_image_compare(model, msger, model_config, p2_screenshot, l_screenshot)
        else:
            new_d['p2_l_compare'] = {
                "size_match": False,
                "bug": "",
                "image": "",
                "type": "",
                "bbox_2d": [],
                "reply": "",
                "detail_reply": "",
            }

        new_d['p_p2_state_compare'] = compare_state_dicts(p_state, p2_state)
        append_jsonl(save_jpath, new_d)
    


if __name__ == "__main__":
    args = parse_args()
    config_log(args.log_file, clear=False)

    model_config = {
        "name": args.model_name,
        "base_url": args.model_base_url,
        "api_key": args.model_api_key,
        "temperature": args.temperature,
        "max_token": args.max_token,
    }

    logged_args = vars(args).copy()
    logged_config = model_config.copy()
    if logged_args.get("model_api_key"):
        logged_args["model_api_key"] = "***"
    if logged_config.get("api_key"):
        logged_config["api_key"] = "***"
    logging.info("CLI args: %s", json.dumps(logged_args, ensure_ascii=False, sort_keys=True))
    logging.info("model_config: %s", json.dumps(logged_config, ensure_ascii=False, sort_keys=True))

    rotdroid(
        model_config,
        apks_dir=args.apks_dir,
        apk_list_file=args.apk_list_file,
        out_dir=args.out_dir,
        device_names=args.device_names,
        android_port=args.android_port,
        algo=args.algo,
        iter_cnt=args.iter_cnt,
        srs_ratio=args.srs_ratio,
        app_time_limit_minutes=args.app_time_limit_minutes,
        blacklist_path=args.blacklist_path,
        clear=args.clear,
        save_filename=args.save_filename,
    )
