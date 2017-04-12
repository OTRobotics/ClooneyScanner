import json

import cv2
import numpy as np

SHEET_WIDTH = 8.5
SHEET_HEIGHT = 11

DEBUG_SHOW_ALL_BOXES = False
SENSITIVITY = 50

NUMBERS_MODEL = [[True, True, True, False, True, True, True],
                 [False, False, True, False, False, True, False],
                 [True, False, True, True, True, False, True],
                 [True, False, True, True, False, True, True],
                 [False, True, True, True, False, True, False],
                 [True, True, False, True, False, True, True],
                 [True, True, False, True, True, True, True],
                 [True, False, True, False, False, True, False],
                 [True, True, True, True, True, True, True],
                 [True, True, True, True, False, True, True]]
ALT_NUMBERS_MODEL = [[False, False, False, False, False, False, False],
                     [False, True, False, False, True, False, False],
                     None,
                     None,
                     None,
                     None,
                     [False, True, False, True, True, True, True],
                     None,
                     None,
                     [True, True, True, True, False, True, False]]


class Scanner(object):
    def __init__(self, scan_fields, sheet_config, img_dir):
        self.scan_fields = scan_fields
        self.config = sheet_config
        self.img_dir = img_dir
        self.marker_colour = sheet_config["marker_colour"]
        self.outline_colour = (0, 255, 0)  # RGB
        self.xy_factor = (1, 1)

    @staticmethod
    def round_colours(img):
        img = ((img / 255.0).round() * 255)
        return img.astype(np.uint8)

    def read_box(self, src, dst, x, y, width, height):
        x = int(x * self.xy_factors[0])
        y = int(y * self.xy_factors[1])
        width = int(width * self.xy_factors[0])
        height = int(height * self.xy_factors[1])
        img2 = src[y:y + height, x:x + width]

        avg = np.sum(np.sum(np.sum(img2))) / (height * width * 3)

        if avg < SENSITIVITY or DEBUG_SHOW_ALL_BOXES:
            cv2.rectangle(dst, (x, y), (x + width, y + height), (0, 255, 0), thickness=3)
        else:
            cv2.rectangle(dst, (x, y), (x + width, y + height), (200, 200, 200), thickness=3)

        return avg < SENSITIVITY

    def scan_sheet(self, image):
        scan_area = self.crop_scan_area(image)
        img_height, img_width, img_channels = scan_area.shape
        self.xy_factors = (img_width / SHEET_WIDTH, img_height / SHEET_HEIGHT)
        box_size = self.config["box_size"]
        box_spacing = self.config["box_spacing"]
        y_spacing = self.config["y_spacing"]
        data = {}

        img2 = cv2.cvtColor(scan_area, cv2.COLOR_RGB2GRAY)
        thresh, img2 = cv2.threshold(img2, 100, 255, cv2.THRESH_BINARY)

        for field in self.scan_fields:
            label = field["id"]
            field_type = field["type"]
            x_pos = field["x_pos"]
            y_pos = field["y_pos"]
            if field_type == "Markers":
                pass
            elif field_type == "Digits":
                width = self.config["seven_segment_width"]
                thickness = self.config["seven_segment_thickness"]
                spacing = self.config["seven_segment_offset"]
                nums = ""
                for i in range(4):
                    parts = [
                        self.read_box(img2, scan_area, x_pos + thickness + spacing * i, y_pos, width, thickness),
                        self.read_box(img2, scan_area, x_pos + spacing * i, y_pos + thickness, thickness, width),
                        self.read_box(img2, scan_area, x_pos + spacing * i + thickness + width, y_pos + thickness, thickness,
                                      width),
                        self.read_box(img2, scan_area, x_pos + thickness + spacing * i, y_pos + width + thickness, width,
                                      thickness),
                        self.read_box(img2, scan_area, x_pos + spacing * i, y_pos + width + thickness + thickness, thickness,
                                      width),
                        self.read_box(img2, scan_area, x_pos + spacing * i + thickness + width,
                                      y_pos + width + thickness + thickness, thickness, width),
                        self.read_box(img2, scan_area, x_pos + thickness + spacing * i, y_pos + (width + thickness) * 2,
                                      width, thickness)]
                    for j in range(10):
                        if NUMBERS_MODEL[j] == parts:
                            nums += str(j)
                            break
                        elif ALT_NUMBERS_MODEL[j] == parts:
                            nums += str(j)
                            break
                    else:
                        nums += "_"
                data[label] = nums
            elif field_type == "Barcode":
                digits = len(bin(int("9" * field["options"]["digits"]))[2:])
                x_pos -= box_size
                number = ""
                for i in range(digits - 1):
                    box_val = self.read_box(img2, scan_area, x_pos - i * (box_size + box_spacing/4), y_pos, box_size, box_size)
                    number = ("1" if box_val else "0") + number
                try:
                    data[label] = str(int(number, 2))
                except:
                    data[label] = "____"

            elif field_type == "BoxNumber":
                digits = field["options"]["digits"]
                x_pos += self.config["label_offset"]
                y_pos += y_spacing * 2
                number = ""
                for i in range(digits):
                    values = []
                    for j in range(10):
                        box_val = self.read_box(img2, scan_area, x_pos + j * (box_size + box_spacing),
                                                y_pos + (y_spacing * 1.5 * i), box_size, box_size)
                        values.append(box_val)
                    if True in values:
                        number += str(max([a * b for a, b in zip(values, range(0, 10))]))
                    else:
                        number += "0"
                data[label] = int(number)
            elif field_type in ["HorizontalOptions", "Numbers", "Boolean"]:
                options = field["options"]["options"]
                note_width = 0 if not field["options"]["note_space"] else (1 + field["options"]["note_width"]) * (
                    box_size + box_spacing)
                x_pos += self.config["label_offset"] + note_width + self.config["marker_size"]
                data_type = field["options"]["type"]

                values = []
                for i in range(len(options)):
                    box_val = self.read_box(img2, scan_area, x_pos + i * (box_size + box_spacing), y_pos, box_size, box_size)
                    values.append(box_val)

                if data_type == "Boolean":
                    data[label] = 1 if values[0] else 0
                elif data_type == "Numbers":
                    total = 0
                    for i in range(len(values)):
                        if values[i]:
                            if "+" in options[i]:
                                total += int(options[i].strip("+"))
                            else:
                                total = int(options[i])
                    data[label] = total
                else:
                    if True in values:
                        val = list(reversed(options))[list(reversed(values)).index(True)]
                        data[label] = val[0] if type(val) == list else val
                    else:
                        data[label] = ""

            elif field_type == "BulkOptions":
                headers = field["options"]["headers"]
                options = field["options"]["options"]
                bulk_data = {}
                for i in range(len(headers)):
                    header = headers[i]
                    bool_values = []
                    values = []
                    for j in range(len(options)):
                        bool_values.append(
                                self.read_box(img2, scan_area, x_pos + i * (box_size + box_spacing),
                                              y_pos + j * (box_size + box_spacing), box_size, box_size))
                    for k in range(len(bool_values)):
                        if bool_values[k]:
                            values.append(options[k])
                    bulk_data[header] = values
                data[label] = bulk_data
            elif field_type == "Image":
                width = field["options"]["width"]
                height = field["options"]["height"]
                x_pos += 1 + self.config["marker_size"]
                if field["options"]["prev_line"]:
                    x_pos += field["options"]["offset"] + 1 + self.config["marker_size"]
                    y_pos -= field["options"]["y_offset"] - self.config["marker_size"]
                else:
                    pass
                x_coords = (int(x_pos * self.xy_factor[0]), int((x_pos + width) * self.xy_factor[0]))
                y_coords = (int(y_pos * self.xy_factor[1]), int((y_pos + height) * self.xy_factor[1]))
                crop = scan_area[y_coords[0]:y_coords[1], x_coords[0]:x_coords[1]]

                edged = cv2.Canny(crop, 100, 200)
                edged = cv2.blur(edged, (5, 5))
                (_, contours, _) = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

                num_contours = len(contours)
                if num_contours > 4:
                    filename = str(data["team_number"]) + "-" + str(data["encoded_match_data"]) + "_" + label + ".png"
                    cv2.imwrite(self.img_dir + filename, crop)

                    pt1 = (x_coords[0], y_coords[0])
                    pt2 = (x_coords[1], y_coords[1])
                    cv2.rectangle(scan_area, pt1, pt2, self.outline_colour, thickness=3)
                data[label] = num_contours > 4

        data["match"] = data["encoded_match_data"][0:-1]
        if data["match"] == "":
            data["match"] = 0
        data["pos"] = data["encoded_match_data"][-1]
        if data["pos"] == "":
            data["pos"] = 0

        del data["encoded_match_data"]

        return data, scan_area

    def crop_scan_area(self, img):
        img2 = img[:]
        img2 = self.round_colours(img2)

        hue_target = list(cv2.cvtColor(np.array([[self.marker_colour]]).astype(np.uint8), cv2.COLOR_RGB2HSV)[0, 0])
        if hue_target[0] < 10 or hue_target[0] > 170:
            img_hsv = cv2.cvtColor(img2, cv2.COLOR_RGB2HSV)  # Image is BGR, but we use RGB because red is dumb is HSV
            target_colour = list(reversed(self.marker_colour))  # Reverse the RGB to BGR
        else:
            img_hsv = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)
            target_colour = self.marker_colour

        mask_range = get_colour_mask_range(*target_colour, 50)
        mask = cv2.inRange(img_hsv, *mask_range)
        res = cv2.bitwise_and(img, img, mask=mask)

        edged = cv2.Canny(res, 100, 200)
        edged = cv2.blur(edged, (5, 5))

        (_, contours, _) = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:2]
        cv2.drawContours(res, contours, -1, (0, 255, 0), 3)

        x_coords = []
        y_coords = []

        for cnt in contours:
            for e in cnt:
                for d in e:
                    x_coords.append(d[0])
                    y_coords.append(d[1])

        upper_left_corner = (min(x_coords), min(y_coords))
        lower_right_corner = (int(max(x_coords)), max(y_coords))
        cropped_img = img[upper_left_corner[1]:lower_right_corner[1], upper_left_corner[0]:lower_right_corner[0]]
        return cropped_img


def get_colour_mask_range(*rgb, sensitivity=10):
    target_colour = np.uint8([[rgb]])
    target_hsv = cv2.cvtColor(target_colour, cv2.COLOR_RGB2HSV)[0][0]
    lower_bound = np.array([0 if target_hsv[0] < sensitivity else target_hsv[0] - sensitivity, 150, 150])
    upper_bound = np.array([255 if target_hsv[0] > 255 - sensitivity else target_hsv[0] + sensitivity, 255, 255])
    return lower_bound, upper_bound


def show_sheet(img):
    cv2.imshow("Image", cv2.resize(img, (425, 550)))
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    import glob
    scan = Scanner(json.load(open("steamworks_fields.json")), json.load(open("steamworks_config.json")), "images/")
    files = glob.glob("scans/*.jpg")
    scan.scan_sheet(cv2.imread(files[0]))
