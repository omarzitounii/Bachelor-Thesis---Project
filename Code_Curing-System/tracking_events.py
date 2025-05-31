# ---------------------------------------------------------------------
# ---------------------------------------------------------------------
# Author:    		       Omar Zitouni
# Title:   		            Map Events
# Description:  Manages all map-related events, including Socket.IO listeners and emitters.
# ---------------------------------------------------------------------
# ---------------------------------------------------------------------

# TRACKING_SIMULATION = 0
# TRACKING_SIMULATION = 1


active_connections = set()


# OZ: Handles 'main_ambulance_isan' event: sends the received ISAN to the ISAN system and retrieves the corresponding ID.
@socketio.on("main_ambulance_isan")
def handle_main_ambulance_isan(data):
    isan = data.get("isan")
    if not isan:
        print(f"ISAN not provided from frontend map")
        return
    try:
        response = requests.post(
            "http://wm:5005/main_ambulance_id_to_cs",
            json={"isan": isan},
        )
    except Exception as e:
        print(f"Error while trying to get main ambulance ID: {str(e)}")


# OZ: POST endpoint to receive the main ambulance ID and emit it via Socket.IO.
@app.route("/main_ambulance_id", methods=["POST"])
def handle_main_ambulance_id():
    try:
        data = request.get_json()
        if not data:
            return (
                jsonify(
                    {"status": "error", "message": "No data provided in the request."}
                ),
                400,
            )

        ambulance_id = data.get("ambulance_id")
        if ambulance_id:
            socketio.emit(
                "main_ambulance_id",
                {"id": ambulance_id},
                # room=request.sid,
                # broadcast=True
            )
            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "Ambulance ID processed successfully.",
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "No ambulance id provided in the request.",
                    }
                ),
                400,
            )
    except Exception as e:
        return {"error": f"An exception occurred: {str(e)}"}, 500


# OZ: Emits a request to the ISAN system to retrieve coordinates of currently occupied ambulances.
@socketio.on("start_tracking")
def handle_start_tracking(data):
    isan = data.get("isan")
    if not isan:
        print(f"ISAN not provided from frontend map")
        return
    try:
        if TRACKING_SIMULATION == 0 or TRACKING_SIMULATION == 1:
            response = requests.post(
                "http://wm:5005/ambulances_coordinates_to_cs",
                json={"isan": isan},
            )
    except Exception as e:
        print(f"Error while trying to get main ambulance ID: {str(e)}")


# OZ: POST endpoint that receives ambulance coordinates and emits them via Socket.IO.
@app.route("/ambulances_coordinates", methods=["POST"])
def handle_ambulances_coordinates():
    try:
        data = request.get_json()
        if not data:
            return (
                jsonify(
                    {"status": "error", "message": "No data provided in the request."}
                ),
                400,
            )
        positionsSet = data.get("positionsSet")
        if positionsSet:
            socketio.emit(
                "position_update",
                positionsSet,
                # room=request.sid,
                # broadcast=True
            )
            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "Ambulances Coordinates processed successfully.",
                    }
                ),
                200,
            )
        else:
            return (
                jsonify({"status": "error", "message": "No ambulances coordinates."}),
                400,
            )
    except Exception as e:
        return {"error": f"An exception occurred: {str(e)}"}, 500


@socketio.on("connect")
def handle_connect():
    global active_connections
    client_id = request.sid
    active_connections.add(client_id)
    print(f"Client connected with SID: {request.sid}")


# OZ: Notifies the ISAN system on client disconnect to stop sending tracking data.
@socketio.on("disconnect")
def handle_disconnect():
    global active_connections
    client_id = request.sid
    try:
        response = requests.post(
            "http://wm:5005/cs_tracking_exit_to_cm",
            json={"isan": isan},
        )
        active_connections.discard(client_id)
        print(f"Client {client_id} disconnected")
    except Exception as e:
        print(f"Error while handling disconnect: {e}")


# OZ: Handles the 'simulation_ambulance_breakdown' event to initiate a simulated ambulance breakdown.
@socketio.on("simulation_ambulance_breakdown")
def handle_simulation_ambulance_Breakdown(data):
    global active_connections
    try:
        ambulance_id = data.get("ambulanceId")
        transported = data["transported"]
        payload = {"ambulanceId": ambulance_id, "transported": transported}
        broken_ambulance_location = data.get("brokenAmbulanceLocation")
        if broken_ambulance_location:
            payload["brokenAmbulanceLocation"] = broken_ambulance_location
        try:
            response = requests.get(
                f"http://rsm:5003/simulation_get_ambulance_ip",
                params={"ambulance_id": ambulance_id},
            )
            if response.status_code == 200:
                ambulance_ip = response.json().get("ip_address")
                print(f"Received IP for ambulance {ambulance_id}: {ambulance_ip}")
                if TRACKING_SIMULATION == 1:
                    if ambulance_ip == "172.18.0.12":
                        port = 5556
                    elif ambulance_ip == "172.18.0.13":
                        port = 5558
                    elif ambulance_ip == "172.18.0.14":
                        port = 5559
                    rs_resp = requests.post(
                        f"http://{ambulance_ip}:{port}/simulation_breakdown",
                        json=payload,
                    )
                # OZ: For practical case, this should actually start directly from the RS, not from the map like in the simulation!
                elif TRACKING_SIMULATION == 0:
                    placeholder = 0
                    # rs_resp = requests.post(
                    #    "http://172.18.0.1:5556/breakdown",
                    #    json=payload,
                    # )
            else:
                print(
                    f"Failed to retrieve IP for ambulance {ambulance_id}, status: {response.status_code}"
                )
        except requests.exceptions.RequestException as e:
            print(f"Error making request to practical_get_ambulance_ip: {e}")
    except Exception as e:
        logging.error(f"Error while handling simulation ambulance breakdown: {str(e)}")


# OZ: POST endpoint to receive a broken ambulance ID and emit an event to remove it from the map.
@app.route("/broken_ambulance_id", methods=["POST"])
def handle_broken_ambulance_id():
    try:
        data = request.get_json()
        if not data:
            return (
                jsonify(
                    {"status": "error", "message": "No data provided in the request."}
                ),
                400,
            )
        ambulance_id = data.get("ambulance_id")
        if ambulance_id:
            socketio.emit(
                "ambulance_breakdown_delete_on_map",
                {"ambulanceId": ambulance_id},
                # room=request.sid,
                # broadcast=True
            )
            return (
                jsonify(
                    {
                        "status": "success",
                        "message": "Ambulance ID processed successfully.",
                    }
                ),
                200,
            )
        else:
            return (
                jsonify(
                    {
                        "status": "error",
                        "message": "No ambulance id provided in the request.",
                    }
                ),
                400,
            )
    except Exception as e:
        return {"error": f"An exception occurred: {str(e)}"}, 500


# OZ: Deletes simulation data to avoid manual cleanup and prepares the system for a new, clean simulation scenario.
@socketio.on("delete_simulation_data")
def handle_delete_simulation_data():
    print(f"Event delete_simulation_data received from client: {request.sid}")
    try:
        mycursor = connectDB.myDB.cursor()
        mycursor.execute("DELETE FROM place_holder")
        connectDB.myDB.commit()
        post_req = requests.post("http://cm:5004/simulation_delete_activeCom")
        if post_req.status_code != 204:
            print(f"Failed to clear simulation data")
        post_one = requests.post("http://rsm:5003/simulation_update_ambulances_status")
        if post_one.status_code != 204:
            print(f"Failed to re-active ambulances status in RSM: {post_one.text}")
        ambulance_ips = {"172.18.0.12", "172.18.0.13", "172.18.0.14"}
        for rs_ip in ambulance_ips:
            if rs_ip == "172.18.0.12":
                port = 5556
            elif rs_ip == "172.18.0.13":
                port = 5558
            elif rs_ip == "172.18.0.14":
                port = 5559
            else:
                continue  # IP is not recognized
            post_two = requests.post(
                f"http://{rs_ip}:{port}/simulation_delete_alarm_list"
            )
            if post_two.status_code != 204:
                print(f"Failed to delete alarm list in RS: {post_two.text}")
    except Exception as e:
        print(f"Error clearing place_holder table: {e}")
    time.sleep(1)
    emit("redirect", room=request.sid)
