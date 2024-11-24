from flask import Flask, request, jsonify
from flask_cors import CORS
import threading
import time
import random
import requests
from pymongo import MongoClient
from bson import ObjectId
import datetime
import os

app = Flask(__name__)
CORS(app)

# MongoDB configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb+srv://hareni:root@fullstack.m6r8v.mongodb.net/Amber?retryWrites=true&w=majority&appName=fullstack')
try:
    client = MongoClient(MONGO_URI)
    db = client['Amber']
    hospitals_collection = db['Hospital']
    routes_collection = db['Route']
    print("Connected to MongoDB successfully!")
except Exception as e:
    print(f"Error connecting to MongoDB: {e}")

# ORS API Key
ORS_API_KEY = os.getenv('ORS_API_KEY', '5b3ce3597851110001cf6248e95d222c8c29470899ffd0fa1707436b')

# Predefined hospitals
hospitals_data = [
    {"name": "Manipal Hospital Sarjapur Road", "coords": (12.9199, 77.6653)},
    {"name": "AAROGYA HASTHA HOSPITALS Kasavanahalli", "coords": (12.9026, 77.67638)},
    {"name": "Care & Cure Hospital", "coords": (12.90795, 77.67553)},
    {"name": "Raksha Orthopedic And Multi Speciality Centre", "coords": (12.9052, 77.67489)},
    {"name": "HEALTH WELL HOSPITAL AND DIAGNOSTICS", "coords": (12.90476, 77.67613)},
    {"name": "BN Speciality Hospital Kasavanahalli", "coords": (12.913, 77.67665)},
    {"name": "APEKSHA HOSPITAL", "coords": (12.91457, 77.67782)},
    {"name": "Cloudnine Hospital Sarjapur", "coords": (12.916209664015579, 77.67466566763876)},
    {"name": "Motherhood Hospital, Sarjapur", "coords": (12.918012603868469, 77.67240788612644)},
    {"name": "Doctor Levine Memorial Hospital", "coords": (12.919086407450946, 77.67055813741754)},
]

# Initialize hospitals in MongoDB
def initialize_hospitals():
    hospitals_collection.delete_many({})
    for hospital in hospitals_data:
        hospital_doc = {
            'name': hospital['name'],
            'coords': {
                'latitude': hospital['coords'][0],
                'longitude': hospital['coords'][1],
            },
            'availability': random.randint(0, 30),
            'routes': []
        }
        hospitals_collection.insert_one(hospital_doc)

# Function to update hospital availability
def update_availability():
    while True:
        for hospital in hospitals_collection.find():
            availability = random.randint(0, 30)
            hospitals_collection.update_one(
                {'_id': hospital['_id']},
                {'$set': {'availability': availability}}
            )
        print("Hospital availability updated")
        time.sleep(120)  # Update every 2 minutes

# Function to get travel time
def get_travel_time(origin, destination):
    url = 'https://api.openrouteservice.org/v2/directions/driving-car'
    headers = {'Authorization': ORS_API_KEY}
    params = {
        'start': f"{origin[1]},{origin[0]}",
        'end': f"{destination[1]},{destination[0]}"
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()['features'][0]['properties']['segments'][0]['duration'] / 60  # Convert to minutes
    return float('inf')

# Function to get route geometry
def get_route_geometry(origin, destination):
    url = 'https://api.openrouteservice.org/v2/directions/driving-car'
    headers = {'Authorization': ORS_API_KEY}
    params = {
        'start': f"{origin[1]},{origin[0]}",
        'end': f"{destination[1]},{destination[0]}"
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json()['features'][0]['geometry']['coordinates']
    return []

# Function to calculate hospital score
def calculate_score(hospital, ambulance_location):
    travel_time = get_travel_time(ambulance_location, (hospital['coords']['latitude'], hospital['coords']['longitude']))
    availability = hospital['availability']
    if availability > 0:
        return availability / (travel_time + 1)
    return 0

# API to calculate the best hospital and save the route
@app.route('/run-algorithm', methods=['POST'])
def run_algorithm():
    try:
        data = request.get_json()
        if 'latitude' in data and 'longitude' in data:
            ambulance_location = (data['latitude'], data['longitude'])

            hospitals = list(hospitals_collection.find())
            for hospital in hospitals:
                hospital['score'] = calculate_score(hospital, ambulance_location)

            # Find the best hospital
            best_hospital = max(hospitals, key=lambda h: h['score'])

            # Get route geometry
            best_hospital_coords = (best_hospital['coords']['latitude'], best_hospital['coords']['longitude'])
            route_geometry = get_route_geometry(ambulance_location, best_hospital_coords)

            # Save route data to MongoDB
            route_doc = {
                'ambulanceLocation': {
                    'latitude': ambulance_location[0],
                    'longitude': ambulance_location[1]
                },
                'bestHospitalId': best_hospital['_id'],
                'bestHospital': best_hospital['_id'],
                'routeCoordinates': [
                    {'latitude': coord[1], 'longitude': coord[0]} for coord in route_geometry
                ],
                'createdAt': datetime.datetime.utcnow()
            }
            route_id = routes_collection.insert_one(route_doc).inserted_id

            # Update the best hospital's routes
            hospitals_collection.update_one(
                {'_id': best_hospital['_id']},
                {'$push': {'routes': route_id}}
            )

            # Prepare hospital availability info with IDs
            hospitals_info = [
                {"id": str(h['_id']), "name": h['name'], "availability": h['availability']} for h in hospitals
            ]

            # Prepare bestHospital info with coordinates
            best_hospital_info = {
                "id": str(best_hospital['_id']),
                "name": best_hospital['name'],
                "coords": best_hospital['coords'],
                "availability": best_hospital['availability']  # Include if needed
            }

            return jsonify({
                "message": "Algorithm run successfully",
                "bestHospital": best_hospital_info,
                "hospitals": hospitals_info
            }), 200
        else:
            return jsonify({"error": "Invalid data"}), 400
    except Exception as e:
        print(f"Error in /run-algorithm: {e}")
        return jsonify({"error": "Internal server error"}), 500

# API to get current hospital availability
@app.route('/hospital-availability', methods=['GET'])
def get_hospital_availability():
    try:
        hospitals = list(hospitals_collection.find({}, {'name': 1, 'availability': 1}))
        return jsonify(hospitals), 200
    except Exception as e:
        print(f"Error in /hospital-availability: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/test', methods=['GET'])
def test_endpoint():
    return "Test endpoint is working!", 200

if __name__ == '__main__':
    initialize_hospitals()
    # Start the hospital availability update thread
    threading.Thread(target=update_availability, daemon=True).start()
    app.run(debug=True, port=5001)
