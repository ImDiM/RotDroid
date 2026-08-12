import hashlib
from PIL import Image
from qwen_vl_utils import smart_resize
import uiautomator2 as u2
def parse_bounds(bounds_str):
    if not bounds_str:
        return None
    bounds = bounds_str.replace('[', '').replace(']', ',').split(',')
    return [int(x) for x in bounds if x] 

def get_size(d:u2.Device):
    width, height = d.window_size()
    return width, height

def get_smart_bbox(bounds, image_path, min_pixels=4 * 28 * 28, max_pixels=16384 * 28 * 28):
    image = Image.open(image_path)
    width, height = image.size
    input_height, input_width = smart_resize(
        height, width, min_pixels=min_pixels, max_pixels=max_pixels
    )
    if input_height == height and input_width == width:
        return bounds
    x_min, y_min, x_max, y_max = bounds
    return (
        int(x_min / width * input_width),
        int(y_min / height * input_height),
        int(x_max / width * input_width),
        int(y_max / height * input_height),
    )


def get_hashes(text: str) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()
