import requests

def decode_vin(vin):
    """Decode VIN using free NHTSA API"""
    url = f"https://vpic.nhtsa.dot.gov/api/vehicles/decodevin/{vin}?format=json"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        result = {}
        field_map = {
            'Make': 'make',
            'Model': 'model',
            'Model Year': 'year',
            'Trim': 'trim',
            'Body Class': 'body_class',
            'Doors': 'doors',
            'Transmission Style': 'transmission',
            'Drive Type': 'drive_type',
            'Fuel Type - Primary': 'fuel_type',
        }
        for r in data.get('Results', []):
            var = r.get('Variable', '')
            val = r.get('Value', '')
            if var in field_map and val and val != 'Not Applicable':
                result[field_map[var]] = val
        return result
    except Exception as e:
        print(f"VIN decode error: {e}")
        return {}
