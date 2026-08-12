import os
from typing import Dict
import xml.etree.ElementTree as ET
import subprocess
import time
import shutil
import adbutils
import uiautomator2 as u2
from models.model import BaseModel 
from utils import get_package,count_files_in_directory
from utils.apk_util import adb_start,get_activity_names,extract_apk, grant_permissions, pack_apk, restart_emulator,set_extractNativeLibs
from utils.file_utils import read_jsonl,append_jsonl, clear_jsonl, read_file, save_hierachy, save_screenshot, write_jsonl
from utils.log_utils import config_log
import logging

    
def get_layout(apk_dir, activity_name):
    logging.info('activity_name: '+activity_name)
    layout_file = find_static_layout(apk_dir, activity_name)
    if layout_file:
        return 'static',layout_file
    layout_file = find_dynamic_layout(apk_dir, activity_name)
    if layout_file:
        return 'dynamic',layout_file
    else:
        logging.info(f"Layout file {activity_name} does not exist")
        return None,None
    
    
def find_dynamic_layout(apk_dir, activity_name):
    
    return None

def find_static_layout(apk_dir, activity_name):
    logging.info('find_static_layout ...')
    base_dirs = [d for d in os.listdir(apk_dir) if d.startswith("smali")]
    for base_dir in base_dirs:
        smali_file = os.path.join(apk_dir, base_dir, activity_name.replace(".", "/") + ".smali")
        if os.path.exists(smali_file):
            logging.info('smali_filepath: '+smali_file)
            content=read_file(smali_file)
            if 'R$layout;->' not in content:
                logging.info(f"{smali_file} contains no static UI")
                return None
            layout_filename=content.split('R$layout;->')[1].split(':I')[0]+'.xml'
            layout_file = os.path.join(apk_dir, "res", "layout", layout_filename)
            logging.info(f"layout_filepath: {layout_file}")
            if os.path.exists(layout_file):
                return [layout_file]
            else:
                logging.info(f"Static layout file {layout_file} does not exist")
                return None


def capture_pair(activity_name, output_dir, device:u2.Device,package):
    logging.info(f"activity: {activity_name}")
    success=adb_start(package,activity_name)
    success = device.app_wait(package, timeout=20)
    if success:
        logging.info("Application started successfully")
    else:
        logging.info("Application failed to start")
        
    current_app = device.app_current()
    logging.info(f"current_app: {current_app}")    
    if current_app["activity"].startswith('.'):
        current_app["activity"] = current_app["package"] + current_app["activity"]
    
    if current_app and current_app["package"] == package and current_app["activity"] == activity_name:
        logging.info("Activity started successfully")
        device.set_orientation('n')
        time.sleep(5)
        portrait_path = os.path.join(output_dir, f"{activity_name}_portrait")
        save_screenshot(portrait_path+'.png',device)
        save_hierachy(portrait_path+'.xml',device.dump_hierarchy())
        print(f"Saved portrait screenshot: {portrait_path}")
        device.set_orientation('l')
        time.sleep(5)
        landscape_path = os.path.join(output_dir, f"{activity_name}_landscape")
        save_screenshot(landscape_path+'.png',device)
        save_hierachy(landscape_path+'.xml',device.dump_hierarchy())
        print(f"Saved landscape screenshot: {landscape_path}")
        success=True

    else:
        logging.info("Activity failed to start")
        success=False
    device.app_stop(package)
    return success

def collect_one(device_id,apkpath,output_fdir,
                apktool_jar='apktool.jar',repack_apk=False,recapture=False):
    device = u2.connect(device_id)
    apk_name=os.path.basename(apkpath)
    logging.info(f"Processing {apk_name}")

    notice={'position':'','error':''}
    a_data={
        'index':None,
        'apk':apk_name,
        'package':None,
        'activity':None,
        'notice':notice
    }     
           
    output_source = os.path.join(output_fdir,'source',apk_name.split('.apk')[0])
    modified_apk = os.path.join(output_fdir,'apk',apk_name)
    capture_dir = os.path.join(output_fdir,'capture',apk_name.split('.apk')[0])
    manifest_path=os.path.join(output_source,"AndroidManifest.xml")

    if not os.path.exists(output_fdir):
        os.makedirs(output_fdir)
    if not os.path.exists(output_source):
        os.makedirs(output_source)
    if not extract_apk(apkpath, output_source, apktool_jar, reextract=False):
        a_data['notice']['position'] = 'Error extracting APK'
        return a_data
    activities,package = get_activity_names(manifest_path)
    if package:
        capture_dir = os.path.join(output_fdir,'capture',package)
        a_data['package']=package
        
    if not os.path.exists(capture_dir):
        os.makedirs(capture_dir)

    set_extractNativeLibs(manifest_path)
    logging.info(f"Found {len(activities)} activities: {activities}")
    file_count=count_files_in_directory(capture_dir)
    aligned_apk=pack_apk(output_source,modified_apk, apktool_jar,repack=repack_apk)
    if not aligned_apk:
        logging.error(f"Error building and signing APK")
        a_data['notice']['position'] = 'Error packing APK'
        return a_data

    if not recapture and file_count == len(activities) * 4:
        logging.info("Screenshots and hierachys already captured, skipping capture")
    else:
        try:
            device.app_uninstall(package)
            device.app_install(aligned_apk) 
            logging.info(f"Installed {package}")
        except Exception as e:
            logging.error(f"Error installing {package}: {e}")
            a_data['notice']['position'] = 'Error installing APK'
            a_data['notice']['error'] = str(e)
            return a_data

        if not grant_permissions(package,manifest_path):
            logging.error(f"Error granting permissions for {package}")
            return a_data
        logging.info(f"Granted permissions for {package}")
        success_cnt=0
        success_activities=[]
        fail_cnt=0
        fail_activities=[]
        for activity in activities:
            retry_count = 0
            while retry_count < 2:
                try:
                    if not capture_pair(activity, capture_dir, device, package):
                        pass
                    else:
                        success_cnt += 1
                        success_activities.append(activity)
                    break
                
                except (u2.exceptions.HTTPError, u2.exceptions.AdbShellError,adbutils.errors.AdbError) as e:
                    logging.error(f"Connection error while capturing {activity}: {e}")
                    device_id=restart_emulator(device_id)
                    device = u2.connect(device_id)
                    print(f"New device ID: {device_id}")
                    retry_count += 1
                    if retry_count == 2:
                        fail_cnt += 1
                        fail_activities.append(activity)
                        a_data['notice']['position'] = 'Error during capture, connection error'
                        a_data['notice']['error'] = str(e)
    
        logging.info(f"success_cnt: {success_cnt}, fail_cnt: {fail_cnt}")
        logging.info(f"success_activities: {success_activities}")
        logging.info(f"fail_activities: {fail_activities}")
        device.app_uninstall(package)
        logging.info(f"Uninstalled {package}")

    activity_info=[]
    count_withlayout=0
    for a in activities:
        type,layout_path=get_layout(output_source,a)
        if layout_path:
            count_withlayout += 1
        activity_info.append({ a: {'type':type,'layout_path':layout_path }})

    a_data={
        'index':None,
        'apk':apk_name,
        'package':package,
        'activity':{
            'count':len(activities),
            'count_withlayout':count_withlayout,
            'info':activity_info,
        },
        'notice':notice
    }
    return a_data
    

def collect_all(device_id, apks_dir,output_fdir,metadata_path='projects.jsonl', apktool_jar='apktool.jar',repack_apk=False,recapture=False):
    meta=read_jsonl(metadata_path)
    print('File loaded')
    i=meta[-1]['index'] if len(meta)>0 else -1
    logging.info(f"continue from {i+1}")
    for index,apk_name in enumerate(os.listdir(apks_dir)):
        if index<=i:
            continue
        if index%150==0 and index!=0:
            restart_emulator(device_id)
            logging.info(f"processed {index} APKs, restart emulator")
        
        if not apk_name.endswith('.apk'):
            continue
        
        apkpath = os.path.join(apks_dir, apk_name)
        a_data=collect_one(device_id,apkpath,output_fdir,
                            apktool_jar,repack_apk,recapture)
        a_data['index']=index
            
        append_jsonl(metadata_path,a_data)
        logging.info(f"apk {apk_name} saved successfully!")
        print(a_data)
        
    logging.info(f"all {len(os.listdir(apks_dir))} APKs modified successfully!")
