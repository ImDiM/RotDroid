text_prompt = r"""You are a Mobile App User. You need to type appropriate text in the text box marked with a red rectangle, not the same as the prompt text in the red rectangle.
Please answer the content of the text in a single line.
"""

DEFECT_PROMPT = '''\
You are an expert GUI defect detector.
You are provided with a pair of screenshots corresponding to the states before and after an APP rotation, with their order unspecified. One is in portrait mode and the other in landscape mode. One of the images may contain a defect.
Your task is to determine whether a defect exists in either image. If a defect is detected, identify: which image contains the defect (portrait or landscape), the type of defect, and the location of the defect.
Write the result in a json block, for example:
```json
...
```

Your result should be a dictionary type json data, following the below format (strict json format, no comments):
    a `bug` field: boolean format, indicating whether a defect is found. If found, should be true, otherwise false. If no defect is found, filling the following fields with null.
    a `type` field: string format, the type of the defect, should be one of the following types:
      - "layout-overlap": UI components or content overlapping/masking each other
      - "layout-clip": Content or components being truncated or extending beyond visible screen boundaries
      - "layout-miss": Required UI elements not displaying/rendering correctly, resulting in incomplete layout
      - "direction-mismatch": Screen/UI elements rotate incorrectly or at inconsistent angles relative to the device's orientation changes.
      - "state-loseinput": Loss of user input data in forms/fields or navigation state
    a `image` field: a string, either "portrait" or "landscape", indicating which screenshot contains the defect.
    a `bbox_2d` field: a list of four integers [x_min, y_min, x_max, y_max], representing the bounding box of the defect area in the image.
'''

class_2_prompt = '''\
You are an expert GUI defect detector.
You are provided with a pair of screenshots showing the same screen before and after an APP rotation, with their order unspecified. One is in portrait mode and the other in landscape mode. One of the images may contain a defect, or both may be correct.
Your task is to determine whether any GUI defect is present in either image. If there is a defect in either screenshot, set `bug` to true; otherwise, set it to false.
Write the result in a strict JSON block as follows:
```json
{
  "bug": true
}
```'''

class_multi_prompt = '''\
You are an expert GUI defect detector.
You are provided with a pair of screenshots corresponding to the states before and after an APP rotation, with their order unspecified. One is in portrait mode and the other in landscape mode. One of the images contains a defect.
Your task is to identify: which image contains the defect (portrait or landscape), the type of defect, and the location of the defect.
Write the result in a json block, for example:
```json
{
  "type": "layout-overlap",
  "image": "portrait",
  "bbox_2d": [100, 200, 400, 500]
}
```

Your result should be a dictionary type json data, following the below format (strict json format, no comments):
    a `type` field: string format, the type of the defect, should be one of the following types: 
      - "layout-overlap": UI components or content overlapping/masking each other
      - "layout-clip": Content or components being truncated or extending beyond visible screen boundaries
      - "layout-miss": Required UI elements not displaying/rendering correctly, resulting in incomplete layout
      - "direction-mismatch": Screen/UI elements rotate incorrectly or at inconsistent angles relative to the device's orientation changes
      - "state-loseinput": Loss of user input data in forms/fields or navigation state
    a `image` field: a string, either "portrait" or "landscape", indicating which screenshot contains the defect
    a `bbox_2d` field: a list of four integers [x_min, y_min, x_max, y_max], representing the bounding box of the defect area in the image
'''
