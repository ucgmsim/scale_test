import json


def load_json(filename):
    with open(filename, "r") as json_file:
        return json.load(json_file)
