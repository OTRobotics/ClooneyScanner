from collections import OrderedDict

import cv2
import numpy as np

from scanners.base import ScannerBase


class Scanner(ScannerBase):
    DEBUG_SHOW_ALL_BOXES = False

    SHEET_WIDTH = 8.5
    SHEET_HEIGHT = 11

    def __init__(self, scan_fields, sheet_config, img_dir):
        super().__init__()
        self._scan_fields = scan_fields
        self._config = sheet_config
        self._img_dir = img_dir
        self._marker_colour = sheet_config["marker_colour"]
        self._highlight_colour = (0, 255, 0)  # RGB
        self._xy_factors = (1, 1)

    def set_config(self, config):
        self._config = config

    def set_fields(self, fields):
        self._scan_fields = fields

    def _read_box(self, src, dst, x, y, width, height, min_val=50):
        x = int(x * self._xy_factors[0])
        y = int(y * self._xy_factors[1])
        width = int(width * self._xy_factors[0])
        height = int(height * self._xy_factors[1])
        img2 = src[y:y + height, x:x + width]

        avg = img2.sum() / (3 * img2.size)

        if avg < min_val or self.DEBUG_SHOW_ALL_BOXES:
            cv2.rectangle(dst, (x, y), (x + width, y + height), (0, 255, 0), thickness=3)
        else:
            cv2.rectangle(dst, (x, y), (x + width, y + height), (200, 200, 200), thickness=3)

        return avg < min_val

    def scan_sheet(self, image):
        scan_area = self._crop_scan_area(image)
        img_height, img_width, img_channels = scan_area.shape
        self._xy_factors = (img_width / self.SHEET_WIDTH, img_height / self.SHEET_HEIGHT)
        box_size = self._config["box_size"]
        box_spacing = self._config["box_spacing"]
        y_spacing = self._config["y_spacing"]
        data = OrderedDict({})

        img2 = cv2.cvtColor(scan_area, cv2.COLOR_RGB2GRAY)
        thresh, img2 = cv2.threshold(img2, 100, 255, cv2.THRESH_BINARY)

        for field in list(self._scan_fields):
            label = field["id"]
            field_type = field["type"]
            x_pos = field["x_pos"]
            y_pos = field["y_pos"]
            if field_type == "Markers":
                pass
            elif field_type == "Digits":
                width = self._config["seven_segment_width"]
                thickness = self._config["seven_segment_thickness"]
                spacing = self._config["seven_segment_offset"]
                nums = ""
                for i in range(4):
                    parts = [
                        self._read_box(img2, scan_area, x_pos + thickness + spacing * i, y_pos, width, thickness),
                        self._read_box(img2, scan_area, x_pos + spacing * i, y_pos + thickness, thickness, width),
                        self._read_box(img2, scan_area, x_pos + spacing * i + thickness + width, y_pos + thickness, thickness,
                                       width),
                        self._read_box(img2, scan_area, x_pos + thickness + spacing * i, y_pos + width + thickness, width,
                                       thickness),
                        self._read_box(img2, scan_area, x_pos + spacing * i, y_pos + width + thickness + thickness, thickness,
                                       width),
                        self._read_box(img2, scan_area, x_pos + spacing * i + thickness + width,
                                       y_pos + width + thickness + thickness, thickness, width),
                        self._read_box(img2, scan_area, x_pos + thickness + spacing * i, y_pos + (width + thickness) * 2,
                                       width, thickness)]
                    for j in range(10):
                        if self.NUMBERS_MODEL[j] == parts:
                            nums += str(j)
                            break
                        elif self.ALT_NUMBERS_MODEL[j] == parts:
                            nums += str(j)
                            break
                    else:
                        nums += "_"
                data[label] = nums
            elif field_type == "Barcode":
                digits = len(bin(int("9" * field["options"]["digits"]))[2:])
                print(label + " digits: " + str(digits))
                x_offset = -box_size
                values = []
                for i in range(digits):
                    values.append(self._read_box(img2, scan_area, x_pos + x_offset, y_pos, box_size, box_size))
                    x_offset -= box_size + self._config['barcode_spacing']
                print(label+ " values: ")
                print(values)
                number = "".join(["1" if e else "0" for e in values][::-1])
                try:
                    data[label] = str(int(number, 2))
                except:
                    data[label] = ""

            elif field_type == "BoxNumber":
                digits = field["options"]["digits"]
                x_pos += self._config["label_offset"]
                y_pos += y_spacing * 1.5
                number = ""
                for i in range(digits):
                    values = []
                    for j in range(10):
                        box_val = self._read_box(img2, scan_area, x_pos + j * (box_size + box_spacing),
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
                x_pos += self._config["label_offset"] + note_width + self._config["marker_size"] + field['options']['offset']
                data_type = field["options"]["type"]

                values = []
                for i in range(len(options)):
                    box_val = self._read_box(img2, scan_area, x_pos + i * (box_size + box_spacing), y_pos, box_size, box_size)
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
                        value = self._read_box(img2, scan_area, x_pos + i * (box_size + box_spacing),
                                               y_pos + j * (box_size + box_spacing), box_size, box_size)
                        bool_values.append(value)
                    for k in range(len(bool_values)):
                        if bool_values[k]:
                            values.append(options[k])
                    bulk_data[header] = values
                data[label] = bulk_data
            elif field_type == "Image":
                width = field["options"]["width"]
                height = field["options"]["height"]
                x_pos += self._config["marker_size"]
                if field["options"]["prev_line"]:
                    x_pos += field["options"]["offset"] + 1
                    y_pos -= field["options"]["y_offset"] + 0.2375
                else:
                    x_pos += 1

                pt1 = (int(x_pos * self._xy_factors[0]), int(y_pos * self._xy_factors[1]))
                pt2 = (int((x_pos + width) * self._xy_factors[0]), int((y_pos + height) * self._xy_factors[1]))

                crop = scan_area[pt1[1]:pt2[1], pt1[0]:pt2[0]]

                edged = cv2.Canny(crop, 100, 200)
                edged = cv2.blur(edged, (5, 5))
                (_, contours, _) = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

                save_img = len(contours) > 4 or crop.mean() < 240
                if save_img:
                    filename = str(data["team_num"]) + "-" + str(data["encoded_match_data"]) + "_" + label + ".png"
                    cv2.imwrite(self._img_dir + filename, crop)

                if save_img or self.DEBUG_SHOW_ALL_BOXES:
                    cv2.rectangle(scan_area, pt1, pt2, self._highlight_colour, thickness=3)
                data[label] = str(save_img)

        print("Match Data Encoded (position,match) " + str(data["encoded_match_data"]))
        print("Team Number Encoded (teamNumber) " + str(data["team_number_encoded"]))
        data["match"] = int("0" + data["encoded_match_data"][0:-1])
        data["pos"] = int("0" + data["encoded_match_data"][-1])
        data.move_to_end("pos", last=False)
        data.move_to_end("match", last=False)


        data["event"] = self._config["event"]
        data["match_code"] = "2018_" + str(data["event"]) + "_" + "q" + str(data["match"])

        del data["encoded_match_data"]

        return data, scan_area

    def _crop_scan_area(self, img):
        img2 = img[:]
        img2 = self._round_colours(img2)
        img_height, img_width, img_channels = img2.shape

        hue_target = list(cv2.cvtColor(np.array([[self._marker_colour]]).astype(np.uint8), cv2.COLOR_RGB2HSV)[0, 0])
        if hue_target[0] < 10 or hue_target[0] > 170:
            img_hsv = cv2.cvtColor(img2, cv2.COLOR_RGB2HSV)  # Read BGR image as RGB to switch Blue and Red channels.
            target_colour = list(reversed(self._marker_colour))  # Reverse the marker colour to match.
        else:
            img_hsv = cv2.cvtColor(img2, cv2.COLOR_BGR2HSV)
            target_colour = self._marker_colour

        mask_range = self._get_colour_mask_range(*(target_colour + [50]))
        mask = cv2.inRange(img_hsv, *mask_range)
        res = cv2.bitwise_and(img, img, mask=mask)

        edged = cv2.Canny(res, 100, 200)
        edged = cv2.blur(edged, (5, 5))

        (_, contours, _) = cv2.findContours(edged.copy(), cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)[:4]  # grab the 4 biggest contours.
        cv2.drawContours(res, contours, -1, (0, 255, 0), 3)

        upper_left_box = []
        upper_right_box = []
        lower_left_box = []
        lower_right_box = []

        for cnt in contours:
            for e in cnt:
                for d in e:
                    if d[0] < (img_width / 2) and d[1] < (img_height / 2):
                        upper_left_box.append([d[0], d[1]])
                    if d[0] > (img_width / 2) and d[1] < (img_height / 2):
                        upper_right_box.append([img_width - d[0], d[1]])
                    if d[0] < (img_width / 2) and d[1] > (img_height / 2):
                        lower_left_box.append([d[0], img_height - d[1]])
                    if d[0] > (img_width / 2) and d[1] > (img_height / 2):
                        lower_right_box.append([d[0], d[1]])

        if not all([upper_left_box, upper_right_box, lower_left_box, lower_right_box]):
            print(Exception("Not enough corners!", upper_left_box, upper_right_box, lower_left_box, lower_right_box))
            return img

        selected_points = []
        upper_left_point = sorted(upper_left_box, key=lambda pt: sum(pt))[0]
        selected_points.append(upper_left_point)

        upper_right_point = sorted(upper_right_box, key=lambda pt: sum(pt))[0]
        upper_right_point = [img_width - upper_right_point[0], upper_right_point[1]]
        selected_points.append(upper_right_point)

        lower_left_point = sorted(lower_left_box, key=lambda pt: sum(pt))[0]
        lower_left_point = [lower_left_point[0], img_height - lower_left_point[1]]
        selected_points.append(lower_left_point)

        lower_right_point = sorted(lower_right_box, key=lambda pt: sum(pt), reverse=True)[0]
        selected_points.append(lower_right_point)

        if len(selected_points) != 4:
            print(Exception("Wrong number of corner points!", selected_points))
            return img

        new_points = ((0, 0), (img_width, 0), (0, img_height), (img_width, img_height))
        new_points = sorted(new_points, key=lambda e: sum(e))
        selected_points = sorted(selected_points, key=lambda e: sum(e))
        warp_matrix = cv2.getPerspectiveTransform(np.float32(selected_points), np.float32(new_points))
        cropped_img = cv2.warpPerspective(img[:], warp_matrix, (img_width, img_height),
                                          borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))
        return cropped_img
