import os
import subprocess
import time
import logging
import shutil
import threading

class EmulatorLauncher:
    
    @staticmethod
    def _log_stream(stream, log_prefix):
        ignore_str = "Ignore IPv6 address:"
        for line in iter(stream.readline, b''):
            log_message = line.decode('utf-8', errors='ignore').strip()
            if log_message and ignore_str not in log_message:
                logging.info(f"[{log_prefix}] {log_message}")

    def __init__(self, device_name, android_port="5554", gpu_mode="auto", boot_timeout=300): 
        if "ANDROID_HOME" not in os.environ:
            raise EnvironmentError("Set ANDROID_HOME.")
        self.android_home = os.environ["ANDROID_HOME"]
        
        self.device_name = device_name.replace(' ', '_')
        self.android_port = str(android_port)
        self.initial_gpu_mode = gpu_mode
        self.boot_timeout = boot_timeout
        self.process = None
        self.start() 

    def _is_gpu_available(self):
        try:
            if os.name == 'nt':
                logging.info("Windows，default to try host GPU mode。")
                return True
            if shutil.which("glxinfo") and "OpenGL renderer" in subprocess.check_output(["glxinfo"]).decode():
                logging.info("Detected Linux/OpenGL GPU support。")
                return True
        except Exception as e:
            logging.warning(f"Error occurred while checking GPU availability: {e}")
        logging.warning("No explicit GPU hardware acceleration support detected.")
        return False

    def start(self):
        if self.process and self.process.poll() is None:
            logging.info("Emulator is already running.")
            return

        if self.initial_gpu_mode == "auto":
            gpu_option = "host" if self._is_gpu_available() else "swiftshader_indirect"
        else:
            gpu_option = self.initial_gpu_mode


        logging.info(f"Using GPU mode: {gpu_option}")

        cmd = [
            os.path.join(self.android_home, 'emulator', 'emulator'),
            '-avd', self.device_name,
            '-port', self.android_port,
            '-gpu', gpu_option,
            '-no-snapshot',
            '-no-boot-anim',
            '-wipe-data'
        ]

        logging.info(f"Starting command: {' '.join(cmd)}")
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        threading.Thread(
            target=self._log_stream, 
            args=(self.process.stdout, 'Emulator-OUT'), 
            daemon=True 
        ).start()
        threading.Thread(
            target=self._log_stream, 
            args=(self.process.stderr, 'Emulator-ERR'), 
            daemon=True
        ).start()

        serial = f'emulator-{self.android_port}'

        try:
            logging.info(f"Waiting for device {serial} to come online...")
            subprocess.run(
                ['adb', '-s', serial, 'wait-for-device'],
                check=True,
                timeout=self.boot_timeout
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            self._handle_boot_failure(f"Device {serial} failed to connect to ADB.", error=e)


        logging.info("Device is online. Waiting for system to boot...")
        start_time = time.time()
        while time.time() - start_time < self.boot_timeout:
            try:
                out = subprocess.check_output(
                    ['adb', '-s', serial, 'shell', 'getprop', 'sys.boot_completed'],
                    stderr=subprocess.DEVNULL 
                ).strip()
                if out == b'1':
                    logging.info("OK")
                    for scale in ('window_animation_scale', 'transition_animation_scale', 'animator_duration_scale'):
                        subprocess.run(['adb', '-s', serial, 'shell', 'settings', 'put', 'global', scale, '0'], check=False)
                    logging.info(f"{self.device_name} OKK!")
                    return
            except subprocess.CalledProcessError:
                time.sleep(2)

        self._handle_boot_failure(f"{self.device_name} emulator startup timed out (sys.boot_completed did not become 1).")
    
    def _handle_boot_failure(self, message, error=None):
        logging.error(message)
        if error:
            logging.error(f"Underlying error: {error}")

        logging.error("Due to startup failure, the emulator process will be terminated. Please check the [Emulator-ERR] log above for details.")
        self.stop()
        raise RuntimeError(message)

    def stop(self):
        if not self.process or self.process.poll() is not None:
            logging.info("Emulator process is not running or has already terminated.")
            subprocess.run(['adb', '-s', f'emulator-{self.android_port}', 'emu', 'kill'], check=False, capture_output=True)
            return
        
        if self.process.poll() is not None:
            logging.info("Emulator process has terminated.")
            return

        logging.info("Attempting to gracefully shut down the emulator...")
        try:
            subprocess.run(['adb', '-s', f'emulator-{self.android_port}', 'emu', 'kill'], check=False, timeout=5, capture_output=True)
            self.process.wait(timeout=10)
            logging.info("Emulator has been shut down gracefully.")
        except subprocess.TimeoutExpired:
            logging.warning("Graceful shutdown timed out, forcing process termination...")
            self.process.kill()
            self.process.wait()
            logging.info("Emulator process has been forcibly terminated.")

    def restart(self):
        logging.info("Restarting emulator...")
        self.stop()
        time.sleep(3) 
        self.start()
        logging.info("Emulator restart completed.")
