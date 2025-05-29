__author__ = "Omar Zitouni"
# !! For posting on Github, i deleted the real username & password from the soap envelop !!

import flask
from flask import Response
from flask import request
import csv
import logging
import time
from datetime import datetime
import isan_def
import requests
import json
import urllib
from flask import jsonify
from math import sin, cos, sqrt, atan2, pi 
from connectDB import myDB
import xml.etree.ElementTree as ET
import threading

logging.basicConfig(level=logging.INFO)

STOP_TRACKING = False
current_location = {}
patientLoadedIntoAmbulance = False
patientLoadedIntoHospital = False
hospitalCoordinates = []
ID_INT = 0
ISAN = ""
EMERGENCY = False
# OZ: False, when we are testing the flow using csv files and not for real life use case (another global variable is in ComM.py)
REAL_TRACKING = True


# !!!TO BE DELETED IN THE USE OF BUTTONS!!!
finalDestinationToIncidentCoordinate = []
finalDestinationToHospitalCoordinate = []


# OZ: This function calculates the distance between two points on the Earth's surface
# using the Haversine formula. The formula is commonly used in geography and geodesy.
# Reference: https://en.wikipedia.org/wiki/Haversine_formula
# Generated with the assistance of ChatGPT by OpenAI.
def get_distance_from_lat_lon_in_meters(lat1, lon1, lat2, lon2): 
    R = 6371000
    d_lat = (lat2 - lat1) * (pi / 180)
    d_lon = (lon2 - lon1) * (pi / 180)   
    a = (sin(d_lat / 2) * sin(d_lat / 2) + 
         cos(lat1 * (pi / 180)) * 
         cos(lat2 * (pi / 180)) * 
         sin(d_lon / 2) * 
         sin(d_lon / 2))   
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


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


# OZ: This should be used for practical case to retrieve coordiantes of the ambulance.
# If evrything works correctly, the lat and lng are returned
# If not, 2x None are returned
positionID = 0
def send_soap_request_soap11():
    global positionID
    url = "https://api.rescuetrack.de/ws/v4/rescuetrack.asmx"
    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": "http://www.rescuetrack.de/GetPositions"
    }
    data = f"""<?xml version="1.0" encoding="utf-8"?>
    <soap:Envelope
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xmlns:xsd="http://www.w3.org/2001/XMLSchema"
      xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
      <soap:Body>
        <GetPositions xmlns="http://www.rescuetrack.de/">
          <username>xxxxxx</username>
          <password>xxxxxx</password>
          <lastPositionId>  </lastPositionId>
          <options>NoOptions</options>
        </GetPositions>
      </soap:Body>
    </soap:Envelope>"""
    try:
        response = requests.post(url, headers=headers, data=data) #MODIFICATION N2 FOR POLLING: timeout=60 and LongPolling option
        if response.status_code == 204:
            print("No content in the response (204).")
            return None, None
        response.raise_for_status() 
        root = ET.fromstring(response.content)
        namespaces = {
            'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
            'ns': 'http://www.rescuetrack.de/'
        }
        positions = root.findall(".//ns:ObjectPosition", namespaces=namespaces)
        if not positions:
            print(f"No Positon are found in the response Object Positions")
            print(f"Response Text:")
            print(response.text)
            return None, None, None
        latest_position = positions[-1]
        latitude = latest_position.attrib.get("Latitude")
        longitude = latest_position.attrib.get("Longitude")
        positionTimestamp = latest_position.attrib.get("Timestamp") # ONE
        #IMPORTANT MODIFICATION N1:
        position_id = latest_position.attrib.get("Id")
        if latitude is not None and longitude is not None and positionTimestamp is not None: # THREE
            print(f"Current position: Latitude={latitude}, Longitude={longitude}, Timestamp of the position={positionTimestamp}")
            print(f"Response Text:")
            print(response.text)
            if position_id is not None:
                positionID = position_id
            return float(latitude), float(longitude), positionTimestamp # TWO
        else:
            return None, None, None
    except requests.RequestException as req_err:
        print(f"HTTP error occurred: {req_err}")
        print(f"Response Text:")
        print(response.text)
        time.sleep(5)
        return None, None, None
    except ET.ParseError as parse_err:
        print(f"XML parsing error occurred: {parse_err}")
        print(f"Response Text:")
        print(response.text)
        return None, None, None
    except Exception as general_err:
        print(f"An unexpected error occurred: {general_err}")
        print(f"Response Text:")
        print(response.text)
        time.sleep(5)
        return None, None, None

justTestingWithOutRoutes = False #TESTING: TO BE DELETE
# OZ: When an emergency is assigned, this function should start the process of taking the coordinates from the rescuetrack.
def startGettingCoordinatesFromRescuetrack(id, isan_instance, isan, brokenAmbulanceLocation):
    global current_location, hospitalCoordinates, STOP_TRACKING, ID_INT, ISAN, patientLoadedIntoAmbulance, patientLoadedIntoHospital, finalDestinationToIncidentCoordinate, finalDestinationToHospitalCoordinate, positionID, justTestingWithOutRoutes
    current_location = {}
    hospitalCoordinates = []
    STOP_TRACKING = False
    patientLoadedIntoAmbulance = False
    patientLoadedIntoHospital = False
    ID_INT = int(id)
    ISAN = isan
    if brokenAmbulanceLocation is None:
        address = get_location_as_map_request(isan_instance.get_location_data())
        try:
            map_quest_api_res = requests.get(
                f"http://www.mapquestapi.com/geocoding/v1/address?key=3Q4Af0BEG1RNVbxvCXs0caWccrX075Du&location={address}",
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
            return
    else:
        lat = brokenAmbulanceLocation["lat"]
        lng = brokenAmbulanceLocation["lng"]  
        incidentCoordinates = [lat, lng]
    myCursor = myDB.cursor()
    if REAL_TRACKING:
        while not STOP_TRACKING:
            # OZ: here i should start send to Rescuetrack API request each 5 (or 1) second(s), asking it about the coordinates of the vehicle.
            vehicleCoordinates = send_soap_request_soap11()
            if vehicleCoordinates == (None, None, None):
                print(f"Failed to fetch coordinates from Rescuetrack API.")
                # TESTING INSERTING COORDINATES INTO THE DATABASE:
                sql = "INSERT INTO gps_logs (timestamp, latitude, longitude, position_timestamp) VALUES (%s, %s, %s, %s)"
                values = (datetime.now().isoformat(timespec='milliseconds'), None, None, None)  
                try:
                    myCursor.execute(sql, values)
                    myDB.commit() 
                    print(f"Saved to Coordinates to table (gps_logs)")
                except Exception as e:
                    print(f"Database insert failed: {str(e)}")  
                # TESTING INSERTING COORDINATES INTO THE DATABASE;
                time.sleep(10)  
                continue
            latitude, longitude, positionTimestamp = vehicleCoordinates
            sql = "INSERT INTO gps_logs (timestamp, latitude, longitude, position_timestamp) VALUES (%s, %s, %s, %s)"
            values = (datetime.now().isoformat(timespec='milliseconds'), latitude, longitude, positionTimestamp)
            try:
                myCursor.execute(sql, values)
                myDB.commit() 
                print(f"Saved to Coordinates to table (gps_logs)")
            except Exception as e:
                print(f"Database insert failed: {str(e)}")
            # Another Modification:
            #latitude = round(latitude, 5)  
            #longitude = round(longitude, 5)
            if not patientLoadedIntoAmbulance: #and justTestingWithOutRoutes: #TESTING: TO BE  DELETE
                current_location = {
                    "id": ID_INT,
                    "lat": latitude,
                    "lng": longitude,
                    "incident_location": {
                        "lat": incidentCoordinates[0],
                        "lng": incidentCoordinates[1],
                    }
                }
            elif hospitalCoordinates and patientLoadedIntoAmbulance and not patientLoadedIntoHospital: #and justTestingWithOutRoutes: #TESTING: TO BE DELETE
                current_location = {
                    "id": ID_INT,
                    "lat": latitude,
                    "lng": longitude,
                    "hospital_location": {
                        "lat": hospitalCoordinates[0],
                        "lng": hospitalCoordinates[1],
                    }
                }
            elif patientLoadedIntoHospital:
                current_location = {
                    "id": ID_INT,
                    "lat": latitude,
                    "lng": longitude,
                    "isAtHospital": {}
                }
                STOP_TRACKING = True
                positionID = 0
                break
            else:
                current_location = {
                    "id": ID_INT,  
                    "lat": latitude,
                    "lng": longitude,
                }      
            print(f"Current Location: {current_location}")
            #time.sleep(10)  # Time between SOAP requests
    myCursor.close()
    # !!!                                      !!!
    # !!!                                      !!!
    # !!! TO BE DELETED, JUST USED FOR TESTING !!!
    # !!!                                      !!!
    # !!!                                      !!!
    if not REAL_TRACKING:
        finalDestinationToIncidentCoordinate = []
        finalDestinationToHospitalCoordinate = []
        startingCoordinates = [52.27483, 10.5053]  
        url = f"https://www.mapquestapi.com/directions/v2/route?key=3Q4Af0BEG1RNVbxvCXs0caWccrX075Du&from={startingCoordinates[0]},{startingCoordinates[1]}&to={incidentCoordinates[0]},{incidentCoordinates[1]}&unit=k&fullShape=true&shapeFormat=raw"
        try:
            response = requests.get(url)
            response.raise_for_status()
            data = response.json()
            shapePoints = data["route"]["shape"]["shapePoints"]
            routeCoordinates = [[shapePoints[i], shapePoints[i + 1]] for i in range(0, len(shapePoints), 2)]
            finalDestinationToIncidentCoordinate = routeCoordinates[-1]
            logging.info(f"Route coordinates fetched successfully for RES_ID: {id}")
        except Exception as e:
            logging.error(f"Error occurred while fetching route: {str(e)}")
            return
        file_name = f"/app/static/practical_coordinates.csv"
        try:
            with open(file_name, mode="w", newline="") as file:
                csv_writer = csv.writer(file)
                for coord in routeCoordinates:
                    csv_writer.writerow([coord[0], coord[1]])
                logging.info(f"Route coordinates written to {file_name}")
        except Exception as e:
            logging.error("Error occurred while writing CSV file: %s", str(e))
        time.sleep(60)
        with open(file_name, mode="r") as csv_file:
            csv_reader = csv.reader(csv_file)
            rows = list(csv_reader)  
            row_index = 0  
        while not STOP_TRACKING:
            if row_index < len(rows):
                vehicleCoordinates = [float(rows[row_index][0]), float(rows[row_index][1])]
                row_index += 1  
            if get_distance_from_lat_lon_in_meters(vehicleCoordinates[0], vehicleCoordinates[1], finalDestinationToIncidentCoordinate[0], finalDestinationToIncidentCoordinate[1]) < 5:
                patientLoadedIntoAmbulance = True   
            if finalDestinationToHospitalCoordinate:
                if get_distance_from_lat_lon_in_meters(vehicleCoordinates[0], vehicleCoordinates[1], finalDestinationToHospitalCoordinate[0], finalDestinationToHospitalCoordinate[1]) < 5:
                    patientLoadedIntoHospital = True     
            if not patientLoadedIntoAmbulance:
                current_location = {
                    "id": ID_INT,  
                    "lat": vehicleCoordinates[0],
                    "lng": vehicleCoordinates[1],
                    "incident_location": {
                        "lat": incidentCoordinates[0],  
                        "lng": incidentCoordinates[1],  
                    }
                }
            elif hospitalCoordinates and patientLoadedIntoAmbulance and not patientLoadedIntoHospital: 
                current_location = {
                    "id": ID_INT,  
                    "lat": vehicleCoordinates[0],
                    "lng": vehicleCoordinates[1],
                    "hospital_location": {
                        "lat": hospitalCoordinates[0],  
                        "lng": hospitalCoordinates[1],  
                    }
                }
            elif patientLoadedIntoHospital: # OZ: This should be a button preferably (patientLoadedIntoHospital)
                current_location = {
                    "id": ID_INT,  
                    "lat": vehicleCoordinates[0],
                    "lng": vehicleCoordinates[1],
                    "isAtHospital": {}
                }
                STOP_TRACKING = True
                break
            # can be deleted
            else:
                current_location = {
                    "id": ID_INT,  
                    "lat": vehicleCoordinates[0],
                    "lng": vehicleCoordinates[1],
                }
            print(f"RS Thread of Current location: {current_location}")
            time.sleep(1)    


def set_patient_loaded_into_ambulance():
    global patientLoadedIntoAmbulance
    patientLoadedIntoAmbulance = True
    return jsonify({"message": "Patient successfully loaded into ambulance."}), 200


def set_patient_loaded_into_hospital():
    global patientLoadedIntoHospital
    patientLoadedIntoHospital = True
    return jsonify({"message": "Patient successfully loaded into hospital."}), 200

def check_tracking_status():
    return jsonify({"STOP_TRACKING": STOP_TRACKING})

def test():
    while True:
        print(f"I'm the separate thread!")
        time.sleep(5)  # Sleep to prevent excessive logging

# OZ: Get the hospital location to transport the patient to.
def setHospitalLocation(lat, lng):
    global hospitalCoordinates, finalDestinationToIncidentCoordinate, finalDestinationToHospitalCoordinate
    try:
        hospitalCoordinates = [lat, lng]

        # !!!                                      !!!
        # !!!                                      !!!
        # !!! TO BE DELETED, JUST USED FOR TESTING !!!
        # !!!                                      !!!
        # !!!                                      !!!
        if not REAL_TRACKING:
            file_name = f"/app/static/practical_coordinates.csv"
            start_lat = finalDestinationToIncidentCoordinate[0]
            start_lng = finalDestinationToIncidentCoordinate[1]
            url = f"https://www.mapquestapi.com/directions/v2/route?key=3Q4Af0BEG1RNVbxvCXs0caWccrX075Du&from={start_lat},{start_lng}&to={hospitalCoordinates[0]},{hospitalCoordinates[1]}&unit=k&fullShape=true&shapeFormat=raw"
            try:
                response = requests.get(url)
                response.raise_for_status()
                data = response.json()
                shapePoints = data["route"]["shape"]["shapePoints"]
                routeCoordinates = [[shapePoints[i], shapePoints[i + 1]] for i in range(0, len(shapePoints), 2)]
                finalDestinationToHospitalCoordinate = routeCoordinates[-1]
            except Exception as e:
                logging.error(f"Error occurred while fetching route to hospital: {str(e)}")
                return
            try:
                with open(file_name, mode="a", newline="") as file:
                    csv_writer = csv.writer(file)
                    for coord in routeCoordinates:
                        csv_writer.writerow([coord[0], coord[1]]) 
                logging.info(f"Route coordinates written successfully to {file_name}")
            except Exception as e:
                logging.error(f"Error occurred while writing CSV file: {str(e)}")
    except Exception as e:
        logging.error(f"Error in Setting Hospital Location: {str(e)}")
        return


# OZ: GET endpoint to retrieve the current location of the tracked ambulance.
def practical_get_current_ambulance_location():
    global current_location
    try:
        if not current_location:  
            return jsonify({"status": "success", "position": None}), 200
        return jsonify({"status": "success", "position": current_location}), 200
    except Exception as e:
        logging.error(f"Error getting current location for ambulance ID: {str(e)}")
        return {"status": "error", "message": f"An error occurred: {str(e)}"}, 500



# !!! TO BE DELETED, JUST USED FOR TESTING !!!
def csvStopTracking():
  global STOP_TRACKING
  STOP_TRACKING = True


# OZ: GET endpoint to verify if the provided ISAN exists in the ambulance records.
def practical_get_main_ambulance_id():
    try:
        data = flask.request.json
        if not data or "isan" not in data:
            return jsonify({"error": "ISAN is required"}), 400
        isan = data["isan"]
        mycursor = myDB.cursor()
        select_command = "SELECT COUNT(*) FROM alarm_list WHERE isan = %s"
        mycursor.execute(select_command, (isan,))
        result = mycursor.fetchone()
        if result[0] > 0:
            return jsonify({"status": "success", "message": "ISAN found"}), 200
        else:
            return jsonify({"error": "ISAN not found"}), 404 
    except Exception as e:
        logging.error(f"Error retrieving main ambulance ID: {str(e)}")
        return jsonify({"error": "Failed to retrieve main ambulance ID"}), 500
    

# OZ: Should be activated when the ambulance breakdown
def breakdown():
    global ID_INT, ISAN, current_location
    try:
        ambulance_id = ID_INT  # OR each ambulance should know its own ID by default
        transported = False
        broken_ambulance_location = None
        if patientLoadedIntoAmbulance:
            transported = True
            broken_ambulance_location = {
                "lat": current_location["lat"],
                "lng": current_location["lng"],
            }
        payload = {
            "ambulanceId": ambulance_id,
            "transported": transported,
            "isan": ISAN
        }
        if transported:
            payload["brokenAmbulanceLocation"] = broken_ambulance_location
        wm_resp = requests.post(
            "http://wm:5005/handle_breakdown",
            json=payload
        )
        return jsonify({"status": "success", "message": "Breakdown successfully sent"}), 200
    except Exception as e:
        logging.error(f"Error while processing simulation breakdown: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500




# ---------------------------------------------------------------------------------------#
# OZ: i  may  split  the  startGettingRescuetrack  function  in  two  seperate  functions#
#     which allows us to track ambulance, also in no emergency case, which  may be useful#
#     for example, to fetch the nearest RS to accident                                   #
# ---------------------------------------------------------------------------------------#

# NOTE: I HAD PROBLEMS TO MAKE  THE THREAD WORK CORRECTLY
# WHEN AUTORELOAD WORKS, I GET TWO THREADS WORKING FOR PERIODIC REQUEST COORDINATES FROM RESCUETRACK. BUT ONLY ONE THREAD WILL BE SHOWN
# WHEN AUTORELOAD IS OFF, THE THREAD WILL BUGS WHEN ANW REQUEST IS SENT TO THE RS


def setIsanRelatedData(id, isan_instance, isan, brokenAmbulanceLocation):
    global current_location, hospitalCoordinates, STOP_TRACKING, ID_INT, ISAN, patientLoadedIntoAmbulance, patientLoadedIntoHospital, finalDestinationToIncidentCoordinate, finalDestinationToHospitalCoordinate, incidentCoordinates, EMERGENCY, justTestingWithOutRoutes
    hospitalCoordinates = []
    incidentCoordinates = []
    patientLoadedIntoAmbulance = False
    patientLoadedIntoHospital = False
    ID_INT = int(id)
    ISAN = isan
    if brokenAmbulanceLocation is None:
        address = get_location_as_map_request(isan_instance.get_location_data())
        try:
            map_quest_api_res = requests.get(
                f"http://www.mapquestapi.com/geocoding/v1/address?key=3Q4Af0BEG1RNVbxvCXs0caWccrX075Du&location={address}",
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
            return
    else:
        lat = brokenAmbulanceLocation["lat"]
        lng = brokenAmbulanceLocation["lng"]  
        incidentCoordinates = [lat, lng]
    EMERGENCY = True


def periodic_request_coordinates_from_rescuetrack():
    global current_location, incidentCoordinates, hospitalCoordinates, ID_INT, patientLoadedIntoAmbulance, patientLoadedIntoHospital, ISAN, EMERGENCY, justTestingWithOutRoutes
    if REAL_TRACKING:
        myCursor = myDB.cursor()
        while True:
            print(f"Active Threads: {[thread.name for thread in threading.enumerate()]}")
            # OZ: here i should start send to Rescuetrack API request each 5 (or 1) second(s), asking it about the coordinates of the vehicle.
            vehicleCoordinates = send_soap_request_soap11()
            if vehicleCoordinates == (None, None):
                #print(f"Failed to fetch coordinates from Rescuetrack API.")
                # TESTING INSERTING COORDINATES INTO THE DATABASE:
                sql = "INSERT INTO gps_logs (timestamp, latitude, longitude) VALUES (%s, %s, %s)"
                if not EMERGENCY:
                    values = (datetime.now().isoformat(timespec='milliseconds'), 0, 0)  
                if EMERGENCY and not patientLoadedIntoAmbulance:
                    values = (datetime.now().isoformat(timespec='milliseconds'), 1, 0)
                if patientLoadedIntoAmbulance and not patientLoadedIntoHospital:
                    values = (datetime.now().isoformat(timespec='milliseconds'), 0, 1) 
                if patientLoadedIntoHospital:
                    values = (datetime.now().isoformat(timespec='milliseconds'), 1, 1) 
                try:
                    myCursor.execute(sql, values)
                    myDB.commit() 
                    myCursor.close()
                except Exception as e:
                    print(f"Database insert failed: {str(e)}")  
                # TESTING INSERTING COORDINATES INTO THE DATABASE;
                time.sleep(10)  
                continue
            else:
                latitude, longitude = vehicleCoordinates
                sql = "INSERT INTO gps_logs (timestamp, latitude, longitude) VALUES (%s, %s, %s)"
                values = (datetime.now().isoformat(timespec='milliseconds'), latitude, longitude)
                try:
                    myCursor.execute(sql, values)
                    myDB.commit() 
                    print(f"Saved to Coordinates to table (gps_logs)")
                except Exception as e:
                    print(f"Database insert failed: {str(e)}")
                if not EMERGENCY:
                        current_location = { 
                            "lat": latitude,
                            "lng": longitude,
                        }  
                        print(f"Current Location: {current_location}")
                        time.sleep(5)
                elif EMERGENCY:
                    if not patientLoadedIntoAmbulance and incidentCoordinates: #and justTestingWithOutRoutes: #TESTING: TO BE  DELETE
                        current_location = {
                            "id": ID_INT,
                            "lat": latitude,
                            "lng": longitude,
                            "incident_location": {
                                "lat": incidentCoordinates[0],
                                "lng": incidentCoordinates[1],
                            }
                        }
                    elif hospitalCoordinates and patientLoadedIntoAmbulance and not patientLoadedIntoHospital: #and justTestingWithOutRoutes: #TESTING: TO BE DELETE
                        current_location = {
                            "id": ID_INT,
                            "lat": latitude,
                            "lng": longitude,
                            "hospital_location": {
                                "lat": hospitalCoordinates[0],
                                "lng": hospitalCoordinates[1],
                            }
                        }
                    elif patientLoadedIntoHospital:
                        current_location = {
                            "id": ID_INT,
                            "lat": latitude,
                            "lng": longitude,
                            "isAtHospital": {}
                        }
                        patientLoadedIntoAmbulance = False
                        patientLoadedIntoHospital = False
                        incidentCoordinates = []
                        hospitalCoordinates = []
                        ISAN = ""
                        ID_INT = 0
                        EMERGENCY = False
                        time.sleep(10) # to ensure, all CS gets the confirmation data (isAtHospital)
                    else:
                        current_location = {
                            "id": ID_INT,  
                            "lat": latitude,
                            "lng": longitude,
                        }      
                    print(f"Current Location: {current_location}")
                    #time.sleep(1)  # Time between SOAP requests
        myCursor.close()