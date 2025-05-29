# ----------------------------------
# ----------------------------------
# OZ: TRACKING (PRACTICAL/SIMULATION)
# ----------------------------------
# ----------------------------------


# OZ: POST endpoint that handle getting the main ambulance ID from the RSM  and forwards it to the corresponding CS's.
def forward_main_ambulance_id():
    try:
        data = request.get_json()
        if not data:
            logging.error("No data provided in the request.")
            return {
                "status": "error",
                "message": "No data provided in the request."
            }, 400           
        rsm_res = req.post(
            "http://rsm:5003/get_main_ambulance_id",
            json={"isan": data["isan"]}
        )           
        if rsm_res.status_code == 204 or rsm_res.status_code == 200:
            rsm_data = rsm_res.json()
            ambulance_id = rsm_data.get("ambulance_id") 
            if ambulance_id:
                cs_res = req.post(
                    f'http://{data["REQ_SYS"]}:5557/main_ambulance_id',
                    json={"ambulance_id": ambulance_id},
                )
                if cs_res.status_code == 204 or cs_res.status_code == 200:
                    return {
                        "status": "success",
                        "message": f"Succeed to forward data to CS"
                    }, 200  
                else:
                    logging.error(f"Failed to forward data to CS. Status Code: {cs_res.status_code}, Response: {cs_res.text}")
                    return {
                        "status": "error",
                        "message": f"Failed to forward data to CS: {cs_res.text}"
                    }, 400              
            else:
                logging.error("Ambulance ID not found in RSM response.")
                return {
                    "status": "error",
                    "message": "Ambulance ID not found in RSM response."
                }, 404
        else:
            logging.error(f"Failed to get ambulance ID from RSM. Status Code: {rsm_res.status_code}, Response: {rsm_res.text}")
            return {
                "status": "error",
                "message": f"Failed to get ambulance ID from RSM: {rsm_res.text}"
            }, 400
    except Exception as e:
        logging.error(f"An error occurred during the forwarding process: {str(e)}")
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }, 500


# OZ: POST endpoint that handle getting the ambulances coordinates and forwards them to the corresponding CS's.
def forward_ambulances_coordinates():
    global ACTIVE_CS_IPS, STOP_SCHEDULER, PRACTICAL_OCCUPIED_RS_IPS, PRACTICAL_RS_AT_HOSPITAL_IPS #, SIMULATION_OCCUPIED_RS_IDS, SIMULATION_RS_AT_HOSPITAL_IDS
    try:
        data = request.get_json()
        if not data or "REQ_SYS" not in data:
            logging.error("No data provided in the request or REQ_SYS missing.")
            return {
                "status": "error",
                "message": "No data provided in the request or REQ_SYS missing."
            }, 400
        req_sys_ip = data["REQ_SYS"]
        ACTIVE_CS_IPS.add(req_sys_ip)
        if len(ACTIVE_CS_IPS) == 1:
            PRACTICAL_OCCUPIED_RS_IPS.clear()
            PRACTICAL_RS_AT_HOSPITAL_IPS.clear()
            STOP_SCHEDULER.clear()
            thread_one = threading.Thread(target=periodic_request_occupied_ambulances_ids_or_ips, daemon=True)
            thread_one.start()
            time.sleep(1)
            if TRACKING_SIMULATION == 1:
                thread_two = threading.Thread(target=simulation_request_occupied_ambulances_coordinates, daemon=True)
                thread_two.start()
            elif TRACKING_SIMULATION == 0:
                thread_two = threading.Thread(target=practical_request_occupied_ambulances_coordinates, daemon=True)
                thread_two.start()                
        return {
            "status": "success",
            "message": "Coordinates requesting terminated!"
        }, 200
    except Exception as e:
        logging.error(f"An error occurred during the forwarding process: {str(e)}")
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }, 500


# OZ: This thread will start fetching the coordinates from the RS's and sends them to the CS's who are requesting tracking-data. (Practical Case)
def practical_request_occupied_ambulances_coordinates():
    global ACTIVE_CS_IPS, STOP_SCHEDULER, PRACTICAL_OCCUPIED_RS_IPS, PRACTICAL_RS_AT_HOSPITAL_IPS 
    try:
        while ACTIVE_CS_IPS:
            local_active_ambulances_ips = PRACTICAL_OCCUPIED_RS_IPS - PRACTICAL_RS_AT_HOSPITAL_IPS
            positionsSet = []
            for rs_ip in local_active_ambulances_ips:
                response = req.get(
                    f"http://{rs_ip}:5556/practical_get_current_ambulance_location"
                )
                if response.status_code == 200:
                    position = response.json().get("position")
                    if position:
                        if "isAtHospital" in position:
                            PRACTICAL_RS_AT_HOSPITAL_IPS.add(rs_ip)
                            db_cursor = connectDB.myDB.cursor()
                            delete_command = "DELETE FROM activeCom WHERE respon_adr = %s"
                            db_cursor.execute(delete_command, (rs_ip,))
                            connectDB.myDB.commit()
                            # OZ: for the practical case, send request to rsm, to re active back the occupied ambulance status.
                            rsm_res = req.post(
                                "http://rsm:5003/practical_reactive_ambulance_status",
                                json={"ambulance_ip": rs_ip},
                            )
                        positionsSet.append(position)
                else:
                    print(
                        f"Failed to fetch position for ambulance ID {rs_ip}: {response.status_code} - {response.text}"
                    )
            if positionsSet:
                local_active_cs_ips = ACTIVE_CS_IPS
                for cs_ip in local_active_cs_ips:
                    cs_res = req.post(
                        f'http://{cs_ip}:5557/ambulances_coordinates',
                        json={"positionsSet": positionsSet},
                    )
            time.sleep(0.5)   
        PRACTICAL_OCCUPIED_RS_IPS.clear()
        PRACTICAL_RS_AT_HOSPITAL_IPS.clear() 
        ACTIVE_CS_IPS.clear()
    except Exception as e:
        logging.error(f"An error occurred during the background processing: {str(e)}")


# OZ: This thread will start fetching the coordinates from the RS's and sends them to the CS's who are requesting for tracking-data. (SIMULATION Case)
def simulation_request_occupied_ambulances_coordinates():
    global ACTIVE_CS_IPS, STOP_SCHEDULER, PRACTICAL_OCCUPIED_RS_IPS, PRACTICAL_RS_AT_HOSPITAL_IPS #, SIMULATION_OCCUPIED_RS_IDS, SIMULATION_RS_AT_HOSPITAL_IDS
    try:
        for rs_ip in PRACTICAL_OCCUPIED_RS_IPS:
            if rs_ip == "172.18.0.12":
                port = 5556
            elif rs_ip == "172.18.0.13":
                port = 5558
            elif rs_ip == "172.18.0.14":
                port = 5559
            else:
                continue  # IP is not recognized
            post_start_response = req.post(f"http://{rs_ip}:{port}/simulation_start_tracking_single_ambulance")
            if post_start_response.status_code != 204:
                print(
                    f"Failed to start tracking for ambulance IP {rs_ip}: {post_start_response.status_code} - {post_start_response.text}"
                )
            else:
                print(f"Tracking started successfully for ambulance IP {rs_ip}")
        local_active_ambulances_ips = set(PRACTICAL_OCCUPIED_RS_IPS)
        time.sleep(0.1)
        while ACTIVE_CS_IPS:
            positionsSet = []
            filtered_active_ambulances_ips = (
                PRACTICAL_OCCUPIED_RS_IPS - PRACTICAL_RS_AT_HOSPITAL_IPS
            )
            if local_active_ambulances_ips != filtered_active_ambulances_ips:
                new_ambulances_ips = (
                    filtered_active_ambulances_ips - local_active_ambulances_ips
                )
                if new_ambulances_ips:
                    for ambulance_ip in new_ambulances_ips:
                        if ambulance_ip == "172.18.0.12":
                            port = 5556
                        elif ambulance_ip == "172.18.0.13":
                            port = 5558
                        elif ambulance_ip == "172.18.0.14":
                            port = 5559
                        else:
                            continue  # IP is not recognized
                        post_start_response = req.post(f"http://{ambulance_ip}:{port}/simulation_start_tracking_single_ambulance")
                        if post_start_response.status_code != 204:
                            print(
                                f"Failed to start tracking for ambulance IP {ambulance_ip}: {post_start_response.status_code} - {post_start_response.text}"
                            )
                        else:
                            print(
                                f"Tracking started successfully for ambulance IP {ambulance_ip}"
                            )
                local_active_ambulances_ips = set(filtered_active_ambulances_ips)
                time.sleep(0.1)
            for ambulance_ip in list(local_active_ambulances_ips):
                if ambulance_ip == "172.18.0.12":
                    port = 5556
                elif ambulance_ip == "172.18.0.13":
                    port = 5558
                elif ambulance_ip == "172.18.0.14":
                    port = 5559
                else:
                    continue  # IP is not recognized
                response = req.get(f"http://{ambulance_ip}:{port}/simulation_current_location_single_ambulance")
                if response.status_code == 200:
                    position = response.json().get("position")
                    if position:
                        if "isAtHospital" in position:
                            PRACTICAL_RS_AT_HOSPITAL_IPS.add(ambulance_ip)
                            #for the simulation stop the simulating thread
                            rs_res = req.post(f"http://{ambulance_ip}:{port}/simulation_stop_particular_thread")
                        positionsSet.append(position)
                else:
                    print(
                        f"Failed to fetch position for ambulance IP {ambulance_ip}: {response.status_code} - {response.text}"
                    )
            for ip in ACTIVE_CS_IPS:
                cs_res = req.post(
                    f'http://{ip}:5557/ambulances_coordinates',
                    json={"positionsSet": positionsSet},
                )
            time.sleep(0.4)   
        PRACTICAL_OCCUPIED_RS_IPS.clear()
        PRACTICAL_RS_AT_HOSPITAL_IPS.clear() 
        ACTIVE_CS_IPS.clear()
    except Exception as e:
        logging.error(f"An error occurred during the background processing: {str(e)}")
    

# OZ: This thread will send each period (interval = 2s) request to RSM asking it about the id's or ip's of the occupied ambulances.
def periodic_request_occupied_ambulances_ids_or_ips(interval=2):
    global STOP_SCHEDULER
    if TRACKING_SIMULATION == 1:
        while not STOP_SCHEDULER.is_set():
            practical_handle_occupied_ambulances_ips()
            time.sleep(interval)
    elif TRACKING_SIMULATION == 0:
        while not STOP_SCHEDULER.is_set():
            practical_handle_occupied_ambulances_ips()
            time.sleep(interval)

'''
def simulation_handle_occupied_ambulances_ids():
    global SIMULATION_OCCUPIED_RS_IDS
    url = "http://rsm:5003/simulation_get_occupied_ambulances_ids"
    rsm_res = req.get(url, headers={"Content-type": "application/json"})
    if rsm_res.status_code == 200:
        ambulances_ids = rsm_res.json().get("ambulances_ids", [])
        SIMULATION_OCCUPIED_RS_IDS = set(map(int, ambulances_ids))
'''

# OZ: For the practical case, we can directly just get the ip's from the active communication table.
def practical_handle_occupied_ambulances_ips():
    global PRACTICAL_OCCUPIED_RS_IPS
    url = "http://rsm:5003/practical_get_occupied_ambulances_ips"
    rsm_res = req.get(url, headers={"Content-type": "application/json"})
    if rsm_res.status_code == 200:
        ambulances_ips = rsm_res.json().get("ambulances_ips", [])
        PRACTICAL_OCCUPIED_RS_IPS = set(map(str, ambulances_ips))
        print(f"Retrieved IPs: {ambulances_ips}")
        print(f"PRACTICAL_ACTIVE_RS_IPS: {PRACTICAL_OCCUPIED_RS_IPS}")
    '''
    try:
        db_cursor = connectDB.myDB.cursor()
        select_command = "SELECT DISTINCT respon_adr FROM activeCom WHERE respon_adr IS NOT NULL"
        db_cursor.execute(select_command)
        result = db_cursor.fetchall()
        PRACTICAL_ACTIVE_RS_IPS = {row[0] for row in result}
    except Exception as e:
        logging.error(f"Failed to retrieve practical active RS IPs from database: {str(e)}")
    '''


# OZ: POST endpoint: When Curing System exits the tracking page, this will stop sending the tracked coordinates to it.
def handle_exit_cs():
    global ACTIVE_CS_IPS, STOP_SCHEDULER, PRACTICAL_OCCUPIED_RS_IPS#, SIMULATION_OCCUPIED_RS_IDS, SIMULATION_RS_AT_HOSPITAL_IDS
    try:
        data = request.get_json()
        if not data or "REQ_SYS" not in data:
            logging.error("No data provided in the request or REQ_SYS missing.")
            return {
                "status": "error",
                "message": "No data provided in the request or REQ_SYS missing."
            }, 400
        req_sys_ip = data["REQ_SYS"]
        if req_sys_ip in ACTIVE_CS_IPS:
            ACTIVE_CS_IPS.remove(req_sys_ip)
        else:
            return {
                "status": "error",
                "message": "CS not in ACTIVE_CS_IPS List."
            }, 404
        if not ACTIVE_CS_IPS:
            #for the simulation , we need to stop the simulating threads!
            STOP_SCHEDULER.set()
            if TRACKING_SIMULATION == 1:
                local_active_ambulances_ips = list(PRACTICAL_OCCUPIED_RS_IPS)
                for rs_ip in local_active_ambulances_ips:
                    if rs_ip == "172.18.0.12":
                        port = 5556
                    elif rs_ip == "172.18.0.13":
                        port = 5558
                    elif rs_ip == "172.18.0.14":
                        port = 5559
                    else:
                        continue  # IP is not recognized
                    response = req.post(f"http://{rs_ip}:{port}/simulation_stop_particular_thread")
            elif TRACKING_SIMULATION == 0:
                # Just stopping the thread that i'm using for testing (this can be deleted)
                # !!! TO BE DELETED !!! JUST USED TO TEST THE FLOW !!!
                if not REAL_TRACKING:
                    rs_rep = req.post("http://172.18.0.12:5556/csvStopTracking")
        return {
            "status": "success",
            "message": "CS removed successfully."
        }, 200
    except Exception as e:
        logging.error(f"An error occurred during the CS exit handling process: {str(e)}")
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }, 500
    

# OZ: This thread will handle sending the broken ambulance ID to the cs's, so that it's data will be deleted on map.
def thread_send_broken_ambulance_id_to_cs(ip, ambulance_id):
    try:
        time.sleep(2)
        cs_res = req.post(
            f'http://{ip}:5557/broken_ambulance_id',
            json={"ambulance_id": ambulance_id},
        )
    except Exception as e:
        print(f"Failed to send request to {ip}: {str(e)}")


# OZ: POST endpoint that will handle forwarding the broken ambulance ID to all cs's that are tracking the ambulances.
def forward_broken_ambulance_id():
    global ACTIVE_CS_IPS
    try:
        data = request.get_json()
        if not data or "ambulance_id" not in data or "ambulance_ip" not in data:
            logging.error("No data provided in the request or ambulance id missing.")
            return {
                "status": "error",
                "message": "No data provided in the request or REQ_SYS missing."
            }, 400
        ambulance_id = data["ambulance_id"]
        ambulance_ip = data["ambulance_ip"]
        if TRACKING_SIMULATION == 1:
            #SIMULATION_RS_AT_HOSPITAL_IDS.add(ambulance_id) #time.sleep(2)
            if ambulance_ip == "172.18.0.12":
                port = 5556
            elif ambulance_ip == "172.18.0.13":
                port = 5558
            elif ambulance_ip == "172.18.0.14":
                port = 5559
            response = req.post(f"http://{ambulance_ip}:{port}/simulation_stop_particular_thread")
        for ip in ACTIVE_CS_IPS:
            thread = threading.Thread(target=thread_send_broken_ambulance_id_to_cs, args=(ip, ambulance_id))
            thread.start()
        return {
            "status": "success",
            "message": "Forwarded broken ambulance id to curing systems"
        }, 200
    except Exception as e:
        logging.error(f"An error occurred during forwarding broken ambulance id : {str(e)}")
        return {
            "status": "error",
            "message": f"An error occurred: {str(e)}"
        }, 500