import logging
import shutil
from pyaxmlparser import APK
import os
from typing import Dict
import xml.etree.ElementTree as ET
import subprocess
import time
import uiautomator2 as u2
import zipfile
import tempfile

def get_package(apkPath):
    if apkPath.lower().endswith('.xapk'):
        with tempfile.TemporaryDirectory() as temp_dir:
            with zipfile.ZipFile(apkPath, 'r') as z:
                all_files = z.namelist()
                logging.info(f"Files in XAPK: {all_files}")
                apk_files = [f for f in all_files if f.lower().endswith('.apk')]
                logging.info(f"XAPK contains {len(apk_files)} APK files")
                base_apk_name = max(apk_files, key=lambda x: z.getinfo(x).file_size)
                z.extract(base_apk_name, path=temp_dir)
                target_path = os.path.join(temp_dir, base_apk_name)
                apk = APK(target_path)
                package = apk.package
                mainActivity = apk.get_main_activity()
                del apk
                return package, mainActivity

    else:
        apk = APK(apkPath)
        return apk.package, apk.get_main_activity()

def install_app(serial: str, apk_path: str):
    logging.info(f"[{serial}] Preparing to install: {os.path.basename(apk_path)}")

    try:
        if apk_path.lower().endswith('.xapk'):
            with tempfile.TemporaryDirectory() as tmpdir:
                logging.info(f"[{serial}] XAPK detected; extracting...")
                with zipfile.ZipFile(apk_path, 'r') as z:
                    z.extractall(tmpdir)
                apks = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir) if f.endswith('.apk')]              
                if not apks:
                    raise Exception("No valid APK file found in the XAPK")
                cmd = ["adb", "-s", serial, "install-multiple", "-g", "-t", "-r"] + apks
                result = subprocess.run(cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    logging.info(f"[{serial}] XAPK installed successfully")
                else:
                    raise Exception(f"ADB installation failed: {result.stderr}")
        
        else:
            cmd = ["adb", "-s", serial, "install", "-g", "-t", "-r", apk_path]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                logging.info(f"[{serial}] Standard APK installed successfully")
            else:
                raise Exception(f"ADB installation failed: {result.stderr}")

    except Exception as e:
        logging.error(f"[{serial}] Installation error: {str(e)}")
        raise e    

    
def run_command(command, cwd=None):
    logging.info(f"Running command: {' '.join(command)}")    
    try:
        result = subprocess.run(command, cwd=cwd, check=True, text=True, capture_output=True,encoding='utf-8')
        logging.info(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        logging.error(f"Error running command: {command}")
        logging.error(e.stderr)
        return False

def extract_apk(apk_path, output_dir, apktool_jar_path="apktool.jar",reextract=False):
    if os.path.exists(output_dir) and any(os.scandir(output_dir)) and not reextract:
        logging.info(f"APK already extracted: {output_dir}")
        return True
    logging.info(f"Extracting APK: {apk_path}")
    command = ["java", "-jar", apktool_jar_path, "d", apk_path, "-o", output_dir, "-f"]
    return run_command(command)

def pack_apk(source_dir, modified_apk, apktool_jar="apktool.jar",repack=False):
    aligned_apk=modified_apk.split('.apk')[0]+'_aligned'+'.apk'
    if os.path.exists(aligned_apk) and not repack:
        logging.info(f"APK already exists: {aligned_apk}")
        return aligned_apk

    if not build_apk(source_dir,modified_apk, apktool_jar):
        return False
    logging.info(f"APK built successfully to {modified_apk}")

    align_apk(modified_apk,aligned_apk)

    keystore_path = "debug.keystore"
    keystore_password = "android"
    key_alias = "androiddebugkey"
    key_password = "android"
    if not generate_keystore(keystore_path, keystore_password, key_alias, key_password):
        return False
    logging.info("Keystore generated successfully")
    if not sign_apk(aligned_apk, keystore_path, keystore_password, key_alias, key_password):
        return False
    
    logging.info(f"APK signed successfully to {aligned_apk}")
    return aligned_apk

def build_apk(source_dir, output_apk, apktool_jar_path="apktool.jar"):
    logging.info(f"Building APK: {output_apk}")
    command = ["java", "-jar", apktool_jar_path, "b", source_dir, "-o", output_apk,]
    return run_command(command)

def resolve_android_build_tool(tool):
    executable = "apksigner.bat" if os.name == "nt" and tool == "apksigner" else f"{tool}.exe" if os.name == "nt" else tool
    resolved = shutil.which(executable)
    if resolved:
        return resolved
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        sdk_root = os.environ.get(variable)
        build_tools_dir = os.path.join(sdk_root, "build-tools") if sdk_root else ""
        if not os.path.isdir(build_tools_dir):
            continue
        for version in sorted(os.listdir(build_tools_dir), reverse=True):
            candidate = os.path.join(build_tools_dir, version, executable)
            if os.path.isfile(candidate):
                return candidate
    return executable

def align_apk(input_apk, output_apk, zipalign_path=None):
    zipalign_path = zipalign_path or resolve_android_build_tool("zipalign")
    print(f"Running zipalign on {input_apk} to {output_apk}")
    command = [
        zipalign_path,
        "-f",
        "4",
        input_apk,
        output_apk
    ]
    return run_command(command)

def generate_keystore(keystore_path, keystore_password, key_alias, key_password):
    if os.path.exists(keystore_path):
        return True

    command = [
        "keytool", "-genkey", "-v",
        "-keystore", keystore_path,
        "-alias", key_alias,
        "-keyalg", "RSA",
        "-keysize", "2048",
        "-validity", "10000",
        "-storepass", keystore_password,
        "-keypass", key_password,
        "-dname", "CN=Android Debug, OU=Android, O=Google, L=Mountain View, ST=California, C=US"
    ]
    return run_command(command)


def sign_apk(apk_path, keystore_path, keystore_password, key_alias, key_password, apksigner_path=None):
    apksigner_path = apksigner_path or resolve_android_build_tool("apksigner")
    logging.info(f"Signing APK: {apk_path}")
    command = [
        apksigner_path, "sign",
        "--ks", keystore_path,
        "--ks-pass", f"pass:{keystore_password}",
        "--key-pass", f"pass:{key_password}",
        "--ks-key-alias", key_alias,
        "--out", apk_path,
        apk_path
    ]
    return run_command(command)

def adb_start(package,activity):
    command = ["adb", "shell", "am", "start", "-n", f"{package}/{activity}"]
    return run_command(command)

def is_emulator_running(device_id='emulator-5554'):
    try:
        result = subprocess.run(['adb', '-s', device_id, 'get-state'], encoding='utf-8',capture_output=True, text=True, check=True)
        return result.stdout.strip() == 'device'
    except subprocess.CalledProcessError:
        return False

def restart_emulator(device_id='emulator-5554',avd='Pixel_6a'):
    if is_emulator_running(device_id):
        subprocess.run(['adb', '-s', device_id, 'emu', 'kill'], check=True)
        logging.info(f"Stopping emulator {device_id}")
    else:
        logging.info(f"Emulator {device_id} is not running; no shutdown is needed")
    time.sleep(5)

    logging.info(f"Using AVD: {avd}")
    subprocess.Popen(['emulator', '-avd', avd], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    time.sleep(180)

    result = subprocess.run(['adb', 'devices'], capture_output=True, text=True, check=True)
    devices = [line.split('\t')[0] for line in result.stdout.strip().split('\n') if '\t' in line]
    if not devices:
        raise RuntimeError("No device detected; emulator startup failed")
    
    new_device_id = devices[0]
    logging.info(f"Emulator restarted; new device ID: {new_device_id}")
    return new_device_id
    
    
def grant_permission(package,permission):
    command=['adb', 'shell', 'pm', 'grant',package,permission]
    return run_command(command)

def add_deviceidle_whitelist(package):
    command=['adb','shell', 'dumpsys', 'deviceidle', 'whitelist' ,'+'+package]
    return run_command(command)


def whitelist_battery_optimization(device, package_name):
    logging.info(f"Whitelisting {package_name} for battery optimization...")
    device.shell(['cmd', 'deviceidle', 'whitelist', f'+{package_name}'])
    
    
def grant_permissions(package,manifest_path):
    add_deviceidle_whitelist(package)
    permissions = get_declared_permissions(manifest_path)
    logging.info(f"Granting {len(permissions)} permissions: {permissions}")
    for p in permissions:
        if not grant_permission(package,p):
            return False
    return True

def grant_all_permissions(d:u2.Device, package):
    d.app_auto_grant_permissions(package)
    
def get_declared_permissions(manifest_path,api_level=33):
    runtime_permissions = {
        "android.permission.SYSTEM_ALERT_WINDOW": 23,
        "android.permission.CAMERA": 23,
        "android.permission.ACCESS_FINE_LOCATION": 23,
        "android.permission.ACCESS_COARSE_LOCATION": 23,
        "android.permission.ACCESS_BACKGROUND_LOCATION": 29,
        "android.permission.READ_PHONE_STATE": 23,
        "android.permission.CALL_PHONE": 23,
        "android.permission.READ_CALL_LOG": 23,
        "android.permission.WRITE_CALL_LOG": 23,
        "android.permission.PROCESS_OUTGOING_CALLS": 23,
        "android.permission.READ_PHONE_NUMBERS": 26,
        "android.permission.ANSWER_PHONE_CALLS": 26,
        "android.permission.READ_EXTERNAL_STORAGE": 23,
        "android.permission.WRITE_EXTERNAL_STORAGE": 23,
        "android.permission.READ_MEDIA_IMAGES": 33,
        "android.permission.READ_MEDIA_VIDEO": 33,
        "android.permission.READ_MEDIA_AUDIO": 33,
        "android.permission.READ_MEDIA_VISUAL_USER_SELECTED": 34,
        "android.permission.POST_NOTIFICATIONS": 33,
        "android.permission.RECORD_AUDIO": 23,
        "android.permission.SEND_SMS": 23,
        "android.permission.RECEIVE_SMS": 23,
        "android.permission.READ_SMS": 23,
        "android.permission.RECEIVE_MMS": 23,
        "android.permission.RECEIVE_WAP_PUSH": 23,
        "android.permission.READ_CONTACTS": 23,
        "android.permission.WRITE_CONTACTS": 23,
        "android.permission.GET_ACCOUNTS": 23,
        "android.permission.READ_CALENDAR": 23,
        "android.permission.WRITE_CALENDAR": 23,
        "android.permission.BODY_SENSORS": 23,
        "android.permission.ACTIVITY_RECOGNITION": 29,
        "android.permission.BODY_SENSORS_BACKGROUND": 33,
        "android.permission.BLUETOOTH_SCAN": 31,
        "android.permission.BLUETOOTH_CONNECT": 31,
        "android.permission.BLUETOOTH_ADVERTISE": 31,
        "android.permission.ACCESS_MEDIA_LOCATION": 29,
        "android.permission.USE_SIP": 23,
        "android.permission.UWB_RANGING": 31,
        "android.permission.NEARBY_WIFI_DEVICES": 33,
    }
    tree = ET.parse(manifest_path)
    root = tree.getroot()
    permissions = []
    for elem in root.findall(".//uses-permission"):
        perm = elem.get("{http://schemas.android.com/apk/res/android}name")
        maxsdk=elem.get("{http://schemas.android.com/apk/res/android}maxSdkVersion")
        if maxsdk is None:
            maxsdk=float('inf')
        else:
            maxsdk = int(maxsdk)

        logging.info(f"Found permission: {perm}")
        if perm in runtime_permissions and maxsdk>=api_level >= runtime_permissions[perm] and perm.startswith("android.permission."):
            permissions.append(perm)
    logging.info(f"{len(permissions)} runtime permission: ")
    for p in permissions:
        logging.info(f" {p}")
    return permissions


A11Y_SERVICES = [
    "com.google.android.marvin.talkback",
    "com.google.android.accessibility.selecttospeak",
    "com.google.android.accessibility.accessibilitymenu",
    "com.google.android.accessibility.switchaccess"
]
def disable_accessibility_services(device):
    for pkg in A11Y_SERVICES:
        print(f"Disabling {pkg} ...")
        device.shell(f"pm disable-user {pkg} || true")

    
def get_activity_names(manifest_path,package=None):
    try:
        ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
        namespaces = {'android': 'http://schemas.android.com/apk/res/android'}
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        if package is None:
            package = root.get("package")
        if package is None:
            logging.warning("Warning: 'package' attribute is missing from the root element in AndroidManifest.xml")
            return []
       
        activities = []
        no_rotate_cnt = 0
        modified_count = 0

        for activity in root.findall(".//activity", namespaces):
            name = activity.get("{http://schemas.android.com/apk/res/android}name")
            orientation = activity.get("{http://schemas.android.com/apk/res/android}screenOrientation")
            exported=activity.get("{http://schemas.android.com/apk/res/android}exported")

            if exported != 'true':
                activity.set("{http://schemas.android.com/apk/res/android}exported", "true")
                modified_count += 1
                logging.info(f"Updated Activity {name} exported attribute to true")

            if orientation == 'portrait' or orientation =='landscape':
                logging.info(f"Activity {name} doesn't supports rotation, orientation: {orientation}")
                no_rotate_cnt+=1
                continue

            if name is None:
                logging.info(f"Warning: Activity element missing 'android:name' attribute: {ET.tostring(activity)}")
                continue  

            if name.startswith("."):  
                name = package + name
            activities.append(f"{name}") 
        logging.info(f"support rotate activities: {len(activities)}, no rotate: {no_rotate_cnt}")
        logging.info(f"exported modified count: {modified_count}")
        

        if modified_count:

            backup_path = manifest_path + ".bak"
            if not os.path.exists(backup_path):
                shutil.copy(manifest_path, backup_path)
                logging.info(f"Backed up the file to: {backup_path}")
            else:
                logging.info(f"Backup file already exists: {backup_path}")

            tree.write(manifest_path, encoding="utf-8", xml_declaration=True)
            logging.info(f"Saved the modified file to: {manifest_path}")
    
        return activities,package
    except Exception as e:
        logging.info(f"Error parsing manifest: {e}")

def set_extractNativeLibs(manifest_path):
    try:
        ET.register_namespace("android", "http://schemas.android.com/apk/res/android")
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        namespace = "{http://schemas.android.com/apk/res/android}"
        attribute_name = f"{namespace}extractNativeLibs"
        modified = False
        for elem in root.iter("application"):
            if attribute_name in elem.attrib:
                current_value = elem.attrib[attribute_name]
                if current_value == "false":
                    elem.attrib[attribute_name] = "true"
                    logging.info(f"Changed android:extractNativeLibs from 'false' to 'true'")
                    modified = True
                elif current_value == "true":
                    logging.info("android:extractNativeLibs is already 'true'; no change is needed")
                else:
                    logging.info(f"Unexpected attribute value: {current_value}")
            else:

                elem.attrib[attribute_name] = "true"
                logging.info("android:extractNativeLibs was not found; added it and set it to 'true'")
                modified = True

        if modified:
            backup_path = manifest_path + ".bak"
            if not os.path.exists(backup_path):
                shutil.copy(manifest_path, backup_path)
                logging.info(f"Backed up the file to: {backup_path}")
            else:
                logging.info(f"Backup file already exists: {backup_path}")

            tree.write(manifest_path, encoding="utf-8", xml_declaration=True)
            logging.info(f"Saved the modified file to: {manifest_path}")
        return True if modified else False

    except Exception as e:
        logging.error(f"Error: {str(e)}")
        return False

