import csv


def load_weak_cores(filepath):
    with open(filepath, 'r') as f:
        dict_reader = csv.DictReader(filepath)
        return list(dict_reader)
