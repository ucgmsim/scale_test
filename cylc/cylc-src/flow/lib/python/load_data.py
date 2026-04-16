import csv


def load_data(filepath):
    with open(filepath, 'r') as f:
        dict_reader = csv.DictReader(f)
        result = []
        for row in dict_reader:
            result.append({k: int(v) for k, v in row.items()})
    return result
