__author__ = "Omar Zitouni"
# OZ: !! For posting on Github, i deleted the real MapQuest-API's Key!!

import flask
from flask import Response
from flask import request
import csv
import time
import logging
import time
import os
import isan_def
import requests
import urllib
import json
import random
from flask import jsonify
import threading
from connectDB import myDB

logging.basicConfig(level=logging.INFO)

current_location = {}
thread = None
stop_signal = None
random_coordinates_set = [
    [52.27551818675605, 10.530476485345455],
    [52.27026619568706, 10.538544569678649],
    [52.264417704970974, 10.527858302291447],
    [52.26436683764947, 10.517841593602515],
    [52.26653280409229, 10.518985965515483],
]


def get_location_as_map_request(location: str) -> str:
    splitted = location.split("^")
    cleaned_up = list(filter(lambda split: split != "", splitted))
    if len(cleaned_up) > 2:
        map_request = f"{cleaned_up[1]},{cleaned_up[2]},{cleaned_up[3]}{cleaned_up[4]}"
    else:
        latitude = location[1:9]
        longitude = location[10:18]
        map_request = urllib.parse.quote_plus(f"{latitude}, {longitude}")
    return map_request


def get_random_coordinates_within_rectangle(min_lat, max_lat, min_lng, max_lng):
    lat = random.uniform(min_lat, max_lat)
    lng = random.uniform(min_lng, max_lng)
    return [lat, lng]


ACTIVE_IDS_FILE = "/app/static/active_ids.json"


def load_active_ids():
    try:
        with open(ACTIVE_IDS_FILE, "r") as f:
            return set(json.load(f))
    except (FileNotFoundError, json.JSONDecodeError):
        with open(ACTIVE_IDS_FILE, "w") as f:
            json.dump([], f)
        return set()


def save_active_ids(active_ids):
    with open(ACTIVE_IDS_FILE, "w") as f:
        json.dump(list(active_ids), f)


ISAN_INSTANCE_FILE = "/app/static/isan_id_pairs.json"


def load_isan_id_pairs():
    try:
        with open(ISAN_INSTANCE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        with open(ISAN_INSTANCE_FILE, "w") as f:
            json.dump({}, f)
        return {}


def save_isan_id_pair(isan_id_pair):
    with open(ISAN_INSTANCE_FILE, "w") as f:
        json.dump(isan_id_pair, f, indent=4)


# OZ: This thread will write the route coordinates from random or predefined start coordinate to the in ISAN incident location.
def simulation_write_route_to_incident(id, isan_instance, isan, brokenAmbulanceLocation):
    global random_coordinates_set
    logging.info("--> RES_ID: %s", id)
    """
    # to randomize the start of  vehicle in the simulation OR chooose randomly from predefined coordinates.
    min_lat, max_lat = 52.254755942517235, 52.280841177092626
    min_lng, max_lng = 10.497785388389847, 10.548202571507677 
    startingCoordinates = get_random_coordinates_within_rectangle(min_lat, max_lat, min_lng, max_lng)  
    """
    #startingCoordinates = [52.27483,10.5053] #id1
    #startingCoordinates = [52.26863, 10.526249]  # id2
    id_int = int(id)
    if id_int == 1:  
        startingCoordinates = [52.27483, 10.5053] #[52.27483, 10.5053] 
    elif id_int == 2: 
        startingCoordinates = [52.26863, 10.526249] #[52.26863, 10.526249]
    elif id_int == 3:
        startingCoordinates = [52.27553851157736, 10.535364013343754] #[52.27553851157736, 10.535364013343754]
    else:
        startingCoordinates = random.choice(random_coordinates_set)  
    # (Commented this to save route costs)
    if brokenAmbulanceLocation is None:
        address = get_location_as_map_request(isan_instance.get_location_data())
        try:
            map_quest_api_res = requests.get(
                f"http://www.mapquestapi.com/geocoding/v1/address?key=xxxxxxxxxxxxxxxxxxxxx&location={address}",
                allow_redirects=True,
            )
            response_json = map_quest_api_res.content.decode("utf-8")
            if map_quest_api_res.status_code == 200:
                location = json.loads(response_json)["results"][0]["locations"][0]["displayLatLng"]
                lat = location["lat"]
                lng = location["lng"]
                incidentCoordinates = [lat, lng]
            else:
                print(
                    f"Could not retrieve lat and lng from `mapquestapi`: [{map_quest_api_res.status_code}] {response_json}"
                )
        except requests.exceptions.ConnectionError as ceex:
            print(f"Could not query map api: {ceex}")
    else:
        lat = brokenAmbulanceLocation["lat"]
        lng = brokenAmbulanceLocation["lng"]  
        incidentCoordinates = [lat, lng]
    # Fetch route coordinates
    url = f"https://www.mapquestapi.com/directions/v2/route?key=xxxxxxxxxxxxxxxxxxxxx&from={startingCoordinates[0]},{startingCoordinates[1]}&to={incidentCoordinates[0]},{incidentCoordinates[1]}&unit=k&fullShape=true&shapeFormat=raw"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        shapePoints = data["route"]["shape"]["shapePoints"]
        routeCoordinates = [[shapePoints[i], shapePoints[i + 1]] for i in range(0, len(shapePoints), 2)]
        logging.info(f"Route coordinates fetched successfully for RES_ID: {id}")
    except Exception as e:
        logging.error(f"Error occurred while fetching route: {str(e)}")
        return
    # Writing the coordinates for the simulation
    file_name = f"/app/static/simulation_coordinates.csv"
    try:
        with open(file_name, mode="w", newline="") as file:
            csv_writer = csv.writer(file)
            if routeCoordinates:
                first_coord = routeCoordinates[0]
                csv_writer.writerow(
                    [
                        id,
                        first_coord[0],
                        first_coord[1],
                        incidentCoordinates[0],
                        incidentCoordinates[1],
                        "incident_location",
                    ]
                )
            for coord in routeCoordinates[1:-1]:
                csv_writer.writerow(
                    [id, coord[0], coord[1], incidentCoordinates[0], incidentCoordinates[1], "incident_location"]
                )
            if routeCoordinates[-1]:
                last_coord = routeCoordinates[-1]
                for i in range(4):
                    csv_writer.writerow(
                        [
                            id,
                            last_coord[0],
                            last_coord[1],
                            incidentCoordinates[0],
                            incidentCoordinates[1],
                            "incident_location",
                        ]
                    )
        logging.info(f"Route coordinates written to {file_name}")
    except Exception as e:
        logging.error("Error occurred while writing CSV file: %s", str(e))
    # end COMMENT
    '''
    id = int(id)
    isan_id_pairs = load_isan_id_pairs()
    for existing_isan, existing_id in list(isan_id_pairs.items()):
        if existing_id == id:
            del isan_id_pairs[existing_isan]
    # Saving isan <-> id, so that can we can distinguish the main ambulance on the simulation.
    isan_id_pairs[isan] = id
    save_isan_id_pair(isan_id_pairs)
    '''


# OZ: This thread will write the route coordinates from in ISAN incident location to the hospital location.
def simulation_write_route_to_hospital(isan, lat, lng):
    savingRouteCosts = 0
    # (Commented this to save route costs)
    try:
        '''
        isan_id_pairs = load_isan_id_pairs()
        if isan not in isan_id_pairs:
            logging.error(f"ISAN {isan} not found in ISAN-ID pairs.")
            return
        ambulance_id = isan_id_pairs[isan]
        logging.info(f"Ambulance ID for ISAN {isan}: {ambulance_id}")
        '''
        file_name = f"/app/static/simulation_coordinates.csv"
        try:
            with open(file_name, mode="r") as file:
                csv_reader = csv.reader(file)
                rows = list(csv_reader)
                second_last_row = rows[-2]
                ambulance_id = second_last_row[0]
                start_lat, start_lng = map(float, second_last_row[1:3])
        except FileNotFoundError:
            logging.error(f"CSV file not found for ambulance.")
        except Exception as e:
            logging.error(f"Error processing CSV file for ambulance: {str(e)}")
        hospital_coordinates = [lat, lng]
        url = f"https://www.mapquestapi.com/directions/v2/route?key=xxxxxxxxxxxxxxxxxxxxx&from={start_lat},{start_lng}&to={hospital_coordinates[0]},{hospital_coordinates[1]}&unit=k&fullShape=true&shapeFormat=raw"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            shapePoints = data["route"]["shape"]["shapePoints"]
            routeCoordinates = [[shapePoints[i], shapePoints[i + 1]] for i in range(0, len(shapePoints), 2)]
            logging.info(f"Route coordinates fetched successfully for ambulance ID to hospital.")
        except Exception as e:
            logging.error(f"Error occurred while fetching route to hospital: {str(e)}")
            return
        # Writing the coordinates for the simulation
        try:
            with open(file_name, mode="a", newline="") as file:
                csv_writer = csv.writer(file)
                if routeCoordinates:
                    first_coord = routeCoordinates[0]
                    csv_writer.writerow(
                        [
                            ambulance_id,
                            first_coord[0],
                            first_coord[1],
                            hospital_coordinates[0],
                            hospital_coordinates[1],
                            "hospital_location",
                        ]
                    )
                for coord in routeCoordinates[1:-1]:
                    csv_writer.writerow(
                        [
                            ambulance_id,
                            coord[0],
                            coord[1],
                            hospital_coordinates[0],
                            hospital_coordinates[1],
                            "hospital_location",
                        ]
                    )
                if routeCoordinates[-1]:
                    last_coord = routeCoordinates[-1]
                    for i in range(5):
                        if i < 4:
                            csv_writer.writerow(
                                [
                                    ambulance_id,
                                    last_coord[0],
                                    last_coord[1],
                                    hospital_coordinates[0],
                                    hospital_coordinates[1],
                                    "hospital_location",
                                ]
                            )
                        else:
                            csv_writer.writerow([ambulance_id, last_coord[0], last_coord[1], "isAtHospital"])
        except Exception as e:
            logging.error("Error occurred while writing CSV file: %s", str(e))
    except Exception as e:
        logging.error(f"Error in simulation_write_route_to_hospital: {str(e)}")
        return
    
    #end comment


# OZ: This thread will simulate getting data from the Rescuetrack API.
def simulation_track_single_vehicle():
    global current_location, stop_signal
    logging.info(f"Thread started for vehicle: (Thread Name: {threading.current_thread().name})")
    # Simulate tracking from the written file
    file_name = f"/app/static/simulation_coordinates.csv"
    try:
        time.sleep(2)
        with open(file_name, mode="r") as file:
            csv_reader = csv.reader(file)
            tracking_data = [row for row in csv_reader]
        last_read_idx = 0
        while True:
            if stop_signal.is_set():
                logging.info(f"Thread for vehicle stopping.")
                break
            if last_read_idx < len(tracking_data):
                for idx in range(last_read_idx, len(tracking_data)):
                    if stop_signal.is_set():
                        logging.info(f"Thread for vehicle ID stopping.")
                        return
                    row = tracking_data[idx]
                    id = int(row[0])
                    lat, lng = map(float, row[1:3])
                    if len(row) > 5 and row[5] == "incident_location":
                        incident_lat, incident_lng = map(float, row[3:5])
                        current_location = {
                            "id": id,
                            "lat": lat,
                            "lng": lng,
                            "incident_location": {"lat": incident_lat, "lng": incident_lng},
                        }
                    elif len(row) > 5 and row[5] == "hospital_location":
                        hospital_lat, hospital_lng = map(float, row[3:5])
                        current_location = {
                            "id": id,
                            "lat": lat,
                            "lng": lng,
                            "hospital_location": {"lat": hospital_lat, "lng": hospital_lng},
                        }
                    elif len(row) > 3 and row[3] == "isAtHospital":
                        current_location = {"id": id, "lat": lat, "lng": lng, "isAtHospital": {}}
                    elif len(row) == 3:
                        current_location = {"id": id, "lat": lat, "lng": lng}
                    logging.info(
                        f"Updated coordinates for vehicle: (Thread Name: {threading.current_thread().name})"
                    )
                    last_read_idx = idx + 1
                    time.sleep(1)
            else:
                with open(file_name, mode="r") as file:
                    csv_reader = csv.reader(file)
                    new_tracking_data = [row for row in csv_reader]
                if len(new_tracking_data) > len(tracking_data):
                    tracking_data = new_tracking_data
                else:
                    if last_read_idx > 0:
                        row = tracking_data[last_read_idx - 1]
                        id = int(row[0])
                        lat, lng = map(float, row[1:3])
                        if len(row) > 5 and row[5] == "incident_location":
                            incident_lat, incident_lng = map(float, row[3:5])
                            current_location = {
                                "id": id,
                                "lat": lat,
                                "lng": lng,
                                "incident_location": {"lat": incident_lat, "lng": incident_lng},
                            }
                        elif len(row) > 5 and row[5] == "hospital_location":
                            hospital_lat, hospital_lng = map(float, row[3:5])
                            current_location = {
                                "id": id,
                                "lat": lat,
                                "lng": lng,
                                "hospital_location": {"lat": hospital_lat, "lng": hospital_lng},
                            }
                        elif len(row) > 3 and row[3] == "isAtHospital":
                            current_location = {"id": id, "lat": lat, "lng": lng, "isAtHospital": {}}
                        elif len(row) == 3:
                            current_location = {"id": id, "lat": lat, "lng": lng}
                        logging.info(
                            f"Repeating last coordinates for vehicle ID: (Thread Name: {threading.current_thread().name})"
                        )
                        time.sleep(5)

    except Exception as e:
        logging.error("Error occurred while reading CSV file: %s", str(e))
    finally:
        current_location = {}
        logging.info(f"Thread finished for vehicle ID: (Thread Name: {threading.current_thread().name})")


# OZ: POST endpoint to stop all active threads, when the user by the Curing System quits the tracking page.
def simulation_stop_particular_thread():
    global thread, stop_signal
    if stop_signal:
        stop_signal.set() 
        time.sleep(2)
    if thread and thread.is_alive():
        thread.join() 
    thread = None 
    stop_signal = None  
    logging.info("+++++Thread stopped+++++")


# OZ: POST endpoint, to start the simulation-tracking thread for a specific ambulance (by it's ID).
def simulation_start_tracking_single_ambulance():
    global thread, stop_signal
    try:
        logging.info("Starting simulation tracking for ambulance")
        if stop_signal is None:
            stop_signal = threading.Event()
        stop_signal.clear()
        if thread is None or not thread.is_alive():
            thread = threading.Thread(target=simulation_track_single_vehicle)
            thread.start()
            logging.info("Thread started successfully for ambulance")
        else:
            logging.info("Simulation is already running, not starting a new thread.")
    except Exception as e:
        logging.info("Error starting tracking for ambulance ID: %s", str(e))


# OZ: GET endpoint, to get the current position of the ambulance.
def simulation_current_location_single_ambulance():
    global current_location
    try:
        if current_location:
            position = current_location
            return jsonify({"status": "success", "position": position}), 200
        else:
            return {"status": "error", "message": f"No location found for ambulance."}, 404
    except Exception as e:
        logging.error(f"Error getting current location for ambulance ID: {str(e)}")
        return {"status": "error", "message": f"An error occurred: {str(e)}"}, 500


# OZ: POST endpoint, to clear the simulation data when required.
def simulation_delete_alarm_list():
    try:
        mycursor = myDB.cursor()
        delete_command = "DELETE FROM alarm_list"
        mycursor.execute(delete_command)
        myDB.commit()
        print("All records in the alarm_list table have been deleted.")
    except Exception as e:
        logging.error("Failed to delete records from alarm_list: %s", str(e))


# OZ: POST endpoint, that will start the simulation of an ambulance breakdown.
def simulation_breakdown():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400
        ambulance_id = data.get("ambulanceId")
        transported = data.get("transported")
        broken_ambulance_location = data.get("brokenAmbulanceLocation")
        payload = {
            "ambulanceId": ambulance_id,
            "transported": transported
        }
        mycursor = myDB.cursor()
        select_command = "SELECT isan FROM alarm_list ORDER BY currenttime DESC LIMIT 1"  # Get the most recent ISAN
        mycursor.execute(select_command)
        result = mycursor.fetchone()
        if result:
            isan = result[0]
            payload["isan"] = isan  # Add ISAN to the payload
        else:
            print(f'THE ISAN IS NOT FOUND IN THE ALARM LIST TABLE')
            return jsonify({"error": f"ISAN not found"}), 404
        '''
        isan_id_pairs = load_isan_id_pairs()
        for isan, id in isan_id_pairs.items():
            if id == ambulance_id:
                payload["isan"] = isan
                break
        '''
        if broken_ambulance_location:
            payload["brokenAmbulanceLocation"] = broken_ambulance_location
        wm_resp = requests.post(
            "http://wm:5005/handle_breakdown",
            json=payload
        )
        return jsonify({"status": "success", "message": "Breakdown successfully sent"}), 200
    except Exception as e:
        logging.error(f"Error while processing simulation breakdown: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500