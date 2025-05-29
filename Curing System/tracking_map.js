/*
 * @author Omar Zitouni
 * !! For posting on GITHUB: I removed the original MapQuest-API's Key !!
 */

let socket;
let map;
let ambulanceMarkers = {};
let ambulanceRoutes = {};
let incidentMarkers = {};
let hospitalMarkers = {};
let resolvedIncidentMarkers = {};
let mainIncidentMarker;
let mainResolvedIncidentMarker;
let mainHospitalMarker;
let loggedAmbulances = new Set();
let mainAmbulanceId;
let ambulancesAtHospital = new Set();
let isInitialized = true;

// Values for testing: 2, true, true
// This is not important, just for saving route request costs while testing!
let idTesting = 3;
let idTestingOneHilfer = false;
let idTestingTwoHilfer = false;

function load_map() {
  L.mapquest.key = "xxxxxxxxxxxxxxxxxxxxx";
  map = L.mapquest.map("map", {
    center: [LATITUDE, LONGITUDE],
    layers: L.mapquest.tileLayer("map"),
    zoom: 14,
    zoomControl: false,
  });
  /* THIS GIVES NO DATA BACK FOR EUROPE COUNTRIES
  map.addLayer(L.mapquest.trafficLayer());
  map.addLayer(L.mapquest.incidentsLayer());
  map.addLayer(L.mapquest.marketsLayer());
  */
  mainIncidentMarker = L.marker([LATITUDE, LONGITUDE], {
    icon: L.mapquest.icons.marker({
      primaryColor: "#db1d1d",
      secondaryColor: "#000000",
      symbol: "U",
    }),
    draggable: false,
  }).addTo(map);
  mainHospitalMarker = L.marker([H_LATITUDE, H_LONGITUDE], {
    icon: L.mapquest.icons.marker({
      primaryColor: "#1d1ddb",
      secondaryColor: "#1d1ddb",
      symbol: "H",
    }),
    draggable: false,
  }).addTo(map);
  map.addControl(L.mapquest.navigationControl());
  map.addControl(L.mapquest.satelliteControl({ position: "topleft" }));
  if (isInitialized) {
    initializeSocket();
  }
}

/**
 * Converts seconds to HH:MM:SS format.
 */
function formatTime(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  return `${String(hours).padStart(2, "0")}:${String(minutes).padStart(
    2,
    "0"
  )}:${String(secs).padStart(2, "0")}`;
}

/*
 * This function calculates the distance between two points on the Earth's surface
 * using the Haversine formula. The formula is commonly used in geography and geodesy.
 * Reference: https://en.wikipedia.org/wiki/Haversine_formula
 * Generated with the assistance of ChatGPT by OpenAI.
 */
function getDistanceFromLatLonInMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000; // Radius of the Earth in meters
  const dLat = (lat2 - lat1) * (Math.PI / 180);
  const dLon = (lon2 - lon1) * (Math.PI / 180);
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * (Math.PI / 180)) *
      Math.cos(lat2 * (Math.PI / 180)) *
      Math.sin(dLon / 2) *
      Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
}

function findNearestPointIndex(
  ambulanceId,
  currentLat,
  currentLng,
  routeCoordinates
) {
  let nearestIndex = 0;
  let minDistance = Infinity;
  for (let i = 0; i < routeCoordinates.length; i++) {
    let [routeLat, routeLng] = routeCoordinates[i];
    let distance = getDistanceFromLatLonInMeters(
      currentLat,
      currentLng,
      routeLat,
      routeLng
    );
    if (distance < minDistance) {
      minDistance = distance;
      nearestIndex = i;
    }
  }
  const rerouteThreshold = 50; // MODIFICATION
  if (minDistance > rerouteThreshold) {
    console.log(
      `Deviation detected for Ambulance ${ambulanceId}: ${minDistance} meters from route. Triggering reroute...`
    );
    return -1;
  }
  /* 
  if (minDistance > 150) {
    console.log(
      `Start of deviation detected for Ambulance ${ambulanceId}: ${minDistance} meters from route. !!DONT UPDATE ROUTE!!`
    );
    return -2;
  }
  */
  return nearestIndex;
}

// show/hide ambulances data function
let showState = true;
function toggleOtherAmbulances() {
  let show = (showState = !showState);
  let toggleButton = document.getElementById("toggleAmbulancesButton");
  if (!show) {
    toggleButton.textContent = "Show Other Ambulances Map Data";
  } else {
    toggleButton.textContent = "Hide Other Ambulances Map Data";
  }
  Object.keys(ambulanceMarkers).forEach((ambulanceId) => {
    if (ambulanceId != mainAmbulanceId) {
      if (show) {
        if (ambulanceMarkers[ambulanceId]) {
          ambulanceMarkers[ambulanceId].addTo(map);
        }
        if (ambulanceRoutes[ambulanceId]?.polyline) {
          ambulanceRoutes[ambulanceId].polyline.addTo(map);
        }
        if (incidentMarkers[ambulanceId]) {
          incidentMarkers[ambulanceId].addTo(map);
        }
        if (hospitalMarkers[ambulanceId]) {
          hospitalMarkers[ambulanceId].addTo(map);
        }
        if (resolvedIncidentMarkers[ambulanceId]) {
          resolvedIncidentMarkers[ambulanceId].addTo(map);
        }
      } else {
        if (ambulanceMarkers[ambulanceId]) {
          map.removeLayer(ambulanceMarkers[ambulanceId]);
        }
        if (ambulanceRoutes[ambulanceId]?.polyline) {
          map.removeLayer(ambulanceRoutes[ambulanceId].polyline);
        }
        if (incidentMarkers[ambulanceId]) {
          map.removeLayer(incidentMarkers[ambulanceId]);
        }
        if (hospitalMarkers[ambulanceId]) {
          map.removeLayer(hospitalMarkers[ambulanceId]);
        }
        if (resolvedIncidentMarkers[ambulanceId]) {
          map.removeLayer(resolvedIncidentMarkers[ambulanceId]);
        }
      }
    }
  });
}

function updateAmbulanceInfo(ambulanceId, remainingTime, destination) {
  const infoDiv = document.getElementById("ambulanceInfo");
  if (!document.getElementById("ambulanceInfoTable")) {
    infoDiv.innerHTML = `
            <table id="ambulanceInfoTable" class="ambulance-table">
                <thead>
                    <tr>
                        <th>Ambulance ID</th>
                        <th>Remaining Time</th>
                        <th>To</th>
                        <th class="empty-header"></th> 
                    </tr>
                </thead>
                <tbody id="ambulanceInfoTableBody"></tbody>
            </table>
        `;
    // Add event listening to the button defined in the html.
    let toggleButton = document.getElementById("toggleAmbulancesButton");
    if (toggleButton) {
      toggleButton.addEventListener("click", toggleOtherAmbulances);
    }
    let deleteButton = document.getElementById("deleteSimulationDataButton");
    if (deleteButton) {
      deleteButton.addEventListener("click", () => {
        socket.emit("delete_simulation_data");
      });
    }
  }
  const tableBody = document.getElementById("ambulanceInfoTableBody");
  let row = document.getElementById("ambulanceRow_" + ambulanceId);
  function isTimeLessThanThreeMinutes(time) {
    const [hours, minutes, seconds] = time.split(":").map(Number);
    const totalMinutes = hours * 60 + minutes + seconds / 60;
    return totalMinutes < 3;
  }
  let destinationText = "undefined";
  if (ambulanceId === mainAmbulanceId) {
    if (mainIncidentMarker !== null) {
      destinationText = "Incident";
    } else {
      destinationText = "Hospital";
    }
  } else {
    if (incidentMarkers[ambulanceId]) {
      destinationText = "Incident";
    } else if (hospitalMarkers[ambulanceId]) {
      destinationText = "Hospital";
    }
  }
  if (!row) {
    row = document.createElement("tr");
    row.id = "ambulanceRow_" + ambulanceId;
    if (ambulanceId === mainAmbulanceId) {
      row.classList.add("bold-row");
    }
    row.innerHTML = `
            <td>${ambulanceId}</td>
            <td id="remainingTime_${ambulanceId}">${remainingTime}</td>
            <td id="destination_${ambulanceId}">${destinationText}</td>
            <td class="sim-delete-button"><button id="delete_${ambulanceId}" class="sim-delete-button">Breakdown!</button>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;</td> 
        `;
    tableBody.appendChild(row);
    let simDeleteButton = document.getElementById(`delete_${ambulanceId}`);
    simDeleteButton.addEventListener("click", function () {
      if (ambulanceId === mainAmbulanceId) {
        if (mainIncidentMarker) {
          socket.emit("simulation_ambulance_breakdown", {
            ambulanceId: ambulanceId,
            transported: false,
          });
        } else {
          const brokenAmbulanceLocation =
            ambulanceMarkers[ambulanceId]?.getLatLng();
          if (brokenAmbulanceLocation) {
            console.log(
              "brokenAmbulanceLocation exists:",
              brokenAmbulanceLocation
            );
            console.log(
              "Type of brokenAmbulanceLocation:",
              typeof brokenAmbulanceLocation
            );
            socket.emit("simulation_ambulance_breakdown", {
              ambulanceId: ambulanceId,
              transported: true,
              brokenAmbulanceLocation: brokenAmbulanceLocation,
            });
          } else {
            console.error(
              `Could not retrieve location for broken main ambulance ID: ${ambulanceId}`
            );
          }
        }
      } else {
        if (incidentMarkers[ambulanceId]) {
          socket.emit("simulation_ambulance_breakdown", {
            ambulanceId: ambulanceId,
            transported: false,
          });
        } else {
          const brokenAmbulanceLocation =
            ambulanceMarkers[ambulanceId]?.getLatLng();
          if (brokenAmbulanceLocation) {
            console.log(
              "brokenAmbulanceLocation exists:",
              brokenAmbulanceLocation
            );
            console.log(
              "Type of brokenAmbulanceLocation:",
              typeof brokenAmbulanceLocation
            );
            socket.emit("simulation_ambulance_breakdown", {
              ambulanceId: ambulanceId,
              transported: true,
              brokenAmbulanceLocation: brokenAmbulanceLocation,
            });
          } else {
            console.error(
              `Could not retrieve location for broken ambulance ID: ${ambulanceId}`
            );
          }
        }
      }
    });
  } else {
    document.getElementById("remainingTime_" + ambulanceId).textContent =
      remainingTime;
    document.getElementById("destination_" + ambulanceId).textContent =
      destinationText;
  }
  let remainingTimeElement = document.getElementById(
    "remainingTime_" + ambulanceId
  );
  if (
    isTimeLessThanThreeMinutes(remainingTime) &&
    destinationText === "Hospital"
  ) {
    remainingTimeElement.classList.add("red-text");
  } else {
    remainingTimeElement.classList.remove("red-text");
  }
  if (remainingTime === "00:00:00" && destinationText === "Hospital") {
    if (row) {
      setTimeout(() => {
        row.remove();
      }, 3000); //3000ms
    }
    return;
  }
}

function updateMap(ambulances) {
  ambulances.forEach((ambulance) => {
    let { id: ambulanceId, lat: ambulanceLat, lng: ambulanceLng } = ambulance;
    if (
      !ambulanceMarkers[ambulanceId] &&
      !ambulancesAtHospital.has(ambulanceId)
    ) {
      if (ambulanceId == mainAmbulanceId) {
        ambulanceMarkers[ambulanceId] = L.marker([ambulanceLat, ambulanceLng], {
          icon: L.mapquest.icons.marker({
            primaryColor: "#00FF00",
            secondaryColor: "#FFFFFF",
            symbol: "A",
          }),
          draggable: false,
        })
          .addTo(map)
          .bindPopup(
            `<span class="custom-popup">ID: ${mainAmbulanceId}</span>`,
            {
              className: "custom-popup-class",
              closeButton: false,
            }
          );
        start = [ambulanceLat, ambulanceLng];
        //JUST TESTING DRIVER NOT FOLLOWING THE ROUTE
        //let MY_LATITUDE = 52.26659949529258;
        //let MY_LONGITUDE = 10.517289477451177;
        end = [LATITUDE, LONGITUDE];
        fetchRoute(ambulanceId, start, end);
      } else {
        ambulanceMarkers[ambulanceId] = L.marker([ambulanceLat, ambulanceLng], {
          icon: L.mapquest.icons.marker({
            primaryColor: "#808080",
            secondaryColor: "#4D4D4D",
            symbol: "A",
          }),
          draggable: false,
        })
          .addTo(map)
          .bindPopup(`<span class="custom-popup">ID: ${ambulanceId}</span>`, {
            className: "custom-popup-class",
            closeButton: false,
          });
        if (ambulance["incident_location"]) {
          incidentMarkers[ambulanceId] = L.marker(
            [ambulance.incident_location.lat, ambulance.incident_location.lng],
            {
              icon: L.mapquest.icons.marker({
                primaryColor: "#808080",
                secondaryColor: "#4D4D4D",
                symbol: "U",
              }),
              draggable: false,
            }
          ).addTo(map);
          start = [ambulanceLat, ambulanceLng];
          end = [
            ambulance.incident_location.lat,
            ambulance.incident_location.lng,
          ];
          fetchRoute(ambulanceId, start, end);
        }
      }
    } else if (!ambulancesAtHospital.has(ambulanceId)) {
      /* OZ: FIRST UPDATE - to check later if this the correct position or should be just before SECOND UPDATE (after creating the route to the hospital)
      if (ambulanceRoutes[ambulanceId] && !loggedAmbulances.has(ambulanceId)) {
        loggedAmbulances.add(ambulanceId);
        let remainingTimeToDestination = formatTime(
          ambulanceRoutes[ambulanceId].totalTimeToDestination
        );
        updateAmbulanceInfo(ambulanceId, remainingTimeToDestination);
        console.log(
          `!FIRST! Ambulance ${ambulanceId}: ${remainingTimeToDestination}`
        );
      }
      */

      // OZ: Maybe this if should be deleted - to check later
      if (!incidentMarkers[ambulanceId] && ambulanceId != mainAmbulanceId) {
        if (ambulance["incident_location"]) {
          incidentMarkers[ambulanceId] = L.marker(
            [ambulance.incident_location.lat, ambulance.incident_location.lng],
            {
              icon: L.mapquest.icons.marker({
                primaryColor: "#808080",
                secondaryColor: "#4D4D4D",
                symbol: "U",
              }),
              draggable: false,
            }
          ).addTo(map);
          start = [ambulanceLat, ambulanceLng];
          end = [
            ambulance.incident_location.lat,
            ambulance.incident_location.lng,
          ];
          fetchRoute(ambulanceId, start, end);
        }
      }

      ambulanceMarkers[ambulanceId].setLatLng([ambulanceLat, ambulanceLng]);
      /*
       * This alternative is intended for real-world applications, but it’s possible that findNearestPointIndex could be further optimized.
       */
      if (ambulanceRoutes[ambulanceId]) {
        let nearestPointIndex = findNearestPointIndex(
          ambulanceId,
          ambulanceLat,
          ambulanceLng,
          ambulanceRoutes[ambulanceId].routeCoordinates
        );
        // rerouting if index -1
        if (nearestPointIndex === -1) {
          map.removeLayer(ambulanceRoutes[ambulanceId].polyline);
          delete ambulanceRoutes[ambulanceId];
          loggedAmbulances.delete(ambulanceId);
          start = [ambulanceLat, ambulanceLng];
          if (ambulanceId === mainAmbulanceId) {
            // may should stay null
            if (mainIncidentMarker === null) {
              end = [H_LATITUDE, H_LONGITUDE];
            } else {
              end = [LATITUDE, LONGITUDE];
            }
          } else {
            if (incidentMarkers[ambulanceId]) {
              let oldIncidentMarkerPosition =
                incidentMarkers[ambulanceId].getLatLng();
              let incidentLat = oldIncidentMarkerPosition.lat;
              let incidentLng = oldIncidentMarkerPosition.lng;
              end = [incidentLat, incidentLng];
            } else {
              let oldHospitalMarkerPosition =
                hospitalMarkers[ambulanceId].getLatLng();
              let hospitalLat = oldHospitalMarkerPosition.lat;
              let hospitalLng = oldHospitalMarkerPosition.lng;
              end = [hospitalLat, hospitalLng];
            }
          }
          fetchRoute(ambulanceId, start, end);
        } else if (nearestPointIndex === -2) {
          // THE ROUTE WILL NOT BE SLICED (UPDATED). CONTINUE UNTIL DRIVER IS BACK ON ROUTE OR GIVEN NEW ROUTE.
        } else {
          ambulanceRoutes[ambulanceId].routeCoordinates =
            ambulanceRoutes[ambulanceId].routeCoordinates.slice(
              nearestPointIndex
            );
          ambulanceRoutes[ambulanceId].polyline.setLatLngs(
            ambulanceRoutes[ambulanceId].routeCoordinates
          );
        }
      }

      /*
        * This will work perfect for the simulation, but not for real world application
        *
        if (ambulanceRoutes[ambulanceId]) {
          ambulanceRoutes[ambulanceId].routeCoordinates =
            ambulanceRoutes[ambulanceId].routeCoordinates.slice(1);
          ambulanceRoutes[ambulanceId].polyline.setLatLngs(
            ambulanceRoutes[ambulanceId].routeCoordinates
          );
        }
        */

      if (
        mainIncidentMarker != null &&
        ambulance["hospital_location"] &&
        ambulanceId == mainAmbulanceId
      ) {
        let oldMainIncidentMarkerPosition = mainIncidentMarker.getLatLng();
        let incidentLat = oldMainIncidentMarkerPosition.lat;
        let incidentLng = oldMainIncidentMarkerPosition.lng;
        map.removeLayer(mainIncidentMarker);
        mainIncidentMarker = null;
        mainResolvedIncidentMarker = L.marker([incidentLat, incidentLng], {
          icon: L.divIcon({
            className: "",
            html: '<div style="color: red; font-weight: bold; font-size: 24px; line-height: 1; background: none; border: none; padding: 0; margin: 0;">X</div>',
          }),
          draggable: false,
        }).addTo(map);
        if (ambulanceRoutes[ambulanceId]) {
          map.removeLayer(ambulanceRoutes[ambulanceId].polyline);
          delete ambulanceRoutes[ambulanceId];
          loggedAmbulances.delete(ambulanceId);
        }
        start = [ambulanceLat, ambulanceLng];
        end = [H_LATITUDE, H_LONGITUDE];
        fetchRoute(ambulanceId, start, end);
      } else if (
        !hospitalMarkers[ambulanceId] &&
        ambulance["hospital_location"] &&
        ambulanceId != mainAmbulanceId
      ) {
        if (incidentMarkers[ambulanceId]) {
          let oldIncidentMarkerPosition =
            incidentMarkers[ambulanceId].getLatLng();
          let incidentLat = oldIncidentMarkerPosition.lat;
          let incidentLng = oldIncidentMarkerPosition.lng;
          map.removeLayer(incidentMarkers[ambulanceId]);
          delete incidentMarkers[ambulanceId];
          resolvedIncidentMarkers[ambulanceId] = L.marker(
            [incidentLat, incidentLng],
            {
              icon: L.divIcon({
                className: "",
                html: '<div style="color: grey; font-weight: bold; font-size: 24px; line-height: 1; background: none; border: none; padding: 0; margin: 0;">X</div>',
              }),
              draggable: false,
            }
          ).addTo(map);
        }
        hospitalMarkers[ambulanceId] = L.marker(
          [ambulance.hospital_location.lat, ambulance.hospital_location.lng],
          {
            icon: L.mapquest.icons.marker({
              primaryColor: "#808080",
              secondaryColor: "#4D4D4D",
              symbol: "H",
            }),
            draggable: false,
          }
        ).addTo(map);
        if (ambulanceRoutes[ambulanceId]) {
          map.removeLayer(ambulanceRoutes[ambulanceId].polyline);
          delete ambulanceRoutes[ambulanceId];
          loggedAmbulances.delete(ambulanceId);
        }
        start = [ambulanceLat, ambulanceLng];
        end = [
          ambulance.hospital_location.lat,
          ambulance.hospital_location.lng,
        ];
        fetchRoute(ambulanceId, start, end);
      }
      // OZ: FIRST UPDATE
      if (ambulanceRoutes[ambulanceId] && !loggedAmbulances.has(ambulanceId)) {
        loggedAmbulances.add(ambulanceId);
        let remainingTimeToDestination = formatTime(
          ambulanceRoutes[ambulanceId].totalTimeToDestination
        );
        updateAmbulanceInfo(ambulanceId, remainingTimeToDestination);
        console.log(
          `!FIRST! Ambulance ${ambulanceId}: ${remainingTimeToDestination}`
        );
      }
      //SECOND UPDATE
      if (ambulanceRoutes[ambulanceId]) {
        if (
          ambulanceRoutes[ambulanceId].passedTimeArray &&
          ambulanceRoutes[ambulanceId].passedTimeArray.length > 0
        ) {
          let targetLat =
            ambulanceRoutes[ambulanceId].passedTimeArray[0].startPoint.lat;
          let targetLng =
            ambulanceRoutes[ambulanceId].passedTimeArray[0].startPoint.lng;
          let distance = getDistanceFromLatLonInMeters(
            ambulanceRoutes[ambulanceId].routeCoordinates[0][0],
            ambulanceRoutes[ambulanceId].routeCoordinates[0][1],
            targetLat,
            targetLng
          );
          /**
           * ambulanceRoutes[ambulanceId].routeCoordinates[5] //compare the current coordinate of the car (which is routeCoordinate[0] (ambulanceLat,ambulanceLng) with routeCoordinate[2])
           * if distance.[0] < distance.[2] -> the ambulance passed the time point => UPDATE remainingTimeToDestination
           * We do this, because , if we can send data each 5s. With enough speed, the ambulance can already pass this point-time with more than 5meteres or any defined distance.
           * Before was only if distance <= 5.
           **/
          let distanceToNextPoint = 20; //was 5 & routeCoordinates[2]
          if (ambulanceRoutes[ambulanceId].routeCoordinates[5]) {
            distanceToNextPoint = getDistanceFromLatLonInMeters(
              ambulanceRoutes[ambulanceId].routeCoordinates[5][0],
              ambulanceRoutes[ambulanceId].routeCoordinates[5][1],
              targetLat,
              targetLng
            );
          }
          if (distance <= distanceToNextPoint) {
            let remainingTimeToDestination =
              ambulanceRoutes[ambulanceId].totalTimeToDestination -
              ambulanceRoutes[ambulanceId].passedTimeArray[0].time;
            ambulanceRoutes[ambulanceId].totalTimeToDestination =
              remainingTimeToDestination;
            let remainingTimeToDestinationFormated = formatTime(
              remainingTimeToDestination
            );
            updateAmbulanceInfo(
              ambulanceId,
              remainingTimeToDestinationFormated
            );
            console.log(
              `Ambulance ${ambulanceId}: ${remainingTimeToDestinationFormated}`
            );
            ambulanceRoutes[ambulanceId].passedTimeArray.shift();
          }
        }
      }
      if ("isAtHospital" in ambulance) {
        ambulancesAtHospital.add(ambulance.id);
        console.log("isAtHospital DETECTED!");
        if (ambulanceId === mainAmbulanceId) {
          if (ambulanceRoutes[ambulanceId]) {
            map.removeLayer(ambulanceRoutes[ambulanceId].polyline);
            delete ambulanceRoutes[ambulanceId];
          }
          map.removeLayer(mainResolvedIncidentMarker);
          delete mainResolvedIncidentMarker;
          map.removeLayer(ambulanceMarkers[ambulanceId]);
          delete ambulanceMarkers[ambulanceId];
          map.removeLayer(mainHospitalMarker);
          mainHospitalMarker = null;
        } else {
          if (ambulanceRoutes[ambulanceId]) {
            map.removeLayer(ambulanceRoutes[ambulanceId].polyline);
            delete ambulanceRoutes[ambulanceId];
          }
          if (resolvedIncidentMarkers[ambulanceId]) {
            map.removeLayer(resolvedIncidentMarkers[ambulanceId]);
            delete resolvedIncidentMarkers[ambulanceId];
          }
          map.removeLayer(ambulanceMarkers[ambulanceId]);
          delete ambulanceMarkers[ambulanceId];
          if (hospitalMarkers[ambulanceId]) {
            map.removeLayer(hospitalMarkers[ambulanceId]);
            delete hospitalMarkers[ambulanceId];
          }
        }
        setTimeout(() => {
          let row = document.getElementById("ambulanceRow_" + ambulanceId);
          if (row) {
            row.remove();
          }
        }, 5000);
      }
    }
  });
}

async function fetchRoute(id, start, end) {
  const url = `https://www.mapquestapi.com/directions/v2/route?key=xxxxxxxxxxxxxxxxxxxxx&from=${start[0]},${start[1]}&to=${end[0]},${end[1]}&unit=k&fullShape=true&shapeFormat=raw`;
  try {
    const response = await fetch(url);
    const data = await response.json();

    //to save costs of the request, i will use for now static data
    if (id == 1 && idTestingOneHilfer) {
      idTestingOneHilfer = false;
      idTesting = 2;
    } else if (id == 2 && idTestingTwoHilfer) {
      idTestingTwoHilfer = false;
    } else if (id == 2 && idTesting == 2) {
      idTesting = 1;
    } else if (id == 1 && idTesting == 1) {
      placeholder = 0;
    }

    console.log(data);
    const shapePoints = data.route.shape.shapePoints;
    const routeCoordinates = [];
    for (let i = 0; i < shapePoints.length; i += 2) {
      routeCoordinates.push([shapePoints[i], shapePoints[i + 1]]);
    }
    let maneuvers = data.route.legs[0].maneuvers; //not sure if this 0 is always like that
    /*
     ** The returned time considers traffic, red lights, speed limits.
     ** So, i assume the times should be shorter in case of ambulances.
     ** i will assume, that ambulance is 30% faster than normal cars.
     ** ambulanceTimeFactor = 1.3
     ** One problem is, that we won't get 00:00:00 by arrival. So we wont be able to delete rows, maybe we should then check if xx:xx:xx < 00:00:10
     */
    const ambulanceTimeFactor = 1.3;
    //let totalTimeToDestination = Math.round(data.route.legs[0].time / ambulanceTimeFactor);
    let totalTimeToDestination = data.route.legs[0].time;
    let passedTimeArray = [];
    for (let i = 0; i < maneuvers.length - 1; i++) {
      //let currentTime = Math.round(maneuvers[i].time / ambulanceTimeFactor);
      let currentTime = maneuvers[i].time;
      let nextStartPoint = maneuvers[i + 1].startPoint;
      nextStartPoint = {
        lat: parseFloat(nextStartPoint.lat.toFixed(5)),
        lng: parseFloat(nextStartPoint.lng.toFixed(5)),
      };
      passedTimeArray.push({
        time: currentTime,
        startPoint: nextStartPoint,
      });
    }
    if (id === mainAmbulanceId) {
      ambulanceRoutes[id] = {
        polyline: L.polyline(routeCoordinates, {
          color: "#4285F4",
          weight: 5,
          opacity: 0.7,
          //dashArray: '4, 8',
        }).addTo(map),
        routeCoordinates: routeCoordinates,
        totalTimeToDestination: totalTimeToDestination,
        passedTimeArray: passedTimeArray,
      };
    } else {
      ambulanceRoutes[id] = {
        polyline: L.polyline(routeCoordinates, {
          color: "#808080",
          weight: 5,
          opacity: 0.7,
          //dashArray: '4, 8',
        }).addTo(map),
        routeCoordinates: routeCoordinates,
        totalTimeToDestination: totalTimeToDestination,
        passedTimeArray: passedTimeArray,
      };
    }
  } catch (error) {
    console.error("Error fetching route:", error);
  }
}

function deleteAmbulanceMapData(ambulanceId) {
  if (ambulanceId === mainAmbulanceId) {
    if (ambulanceRoutes[ambulanceId]) {
      map.removeLayer(ambulanceRoutes[ambulanceId].polyline);
      delete ambulanceRoutes[ambulanceId];
    }
    if (mainResolvedIncidentMarker) {
      map.removeLayer(mainResolvedIncidentMarker);
      delete mainResolvedIncidentMarker;
    }
    if (ambulanceMarkers[ambulanceId]) {
      map.removeLayer(ambulanceMarkers[ambulanceId]);
      delete ambulanceMarkers[ambulanceId];
    }
    if (mainHospitalMarker) {
      map.removeLayer(mainHospitalMarker);
      mainHospitalMarker = null;
    }
    if (mainIncidentMarker) {
      map.removeLayer(mainIncidentMarker);
      mainIncidentMarker = null;
    }
  } else {
    if (ambulanceRoutes[ambulanceId]) {
      map.removeLayer(ambulanceRoutes[ambulanceId].polyline);
      delete ambulanceRoutes[ambulanceId];
    }
    if (resolvedIncidentMarkers[ambulanceId]) {
      map.removeLayer(resolvedIncidentMarkers[ambulanceId]);
      delete resolvedIncidentMarkers[ambulanceId];
    }
    if (ambulanceMarkers[ambulanceId]) {
      map.removeLayer(ambulanceMarkers[ambulanceId]);
      delete ambulanceMarkers[ambulanceId];
    }
    if (hospitalMarkers[ambulanceId]) {
      map.removeLayer(hospitalMarkers[ambulanceId]);
      delete hospitalMarkers[ambulanceId];
    }
    if (incidentMarkers[ambulanceId]) {
      map.removeLayer(incidentMarkers[ambulanceId]);
      delete incidentMarkers[ambulanceId];
    }
  }
}

function initializeSocket() {
  isInitialized = false;
  socket = io("http://localhost:5557", {
    transports: ["websocket"],
    reconnection: false,
  });

  socket.on("ambulance_breakdown_delete_on_map", (data) => {
    console.log("BROKEN AMBULANCE TO DELETE RECEIVED");
    let ambulanceId = data.ambulanceId;
    let ambulanceRow = document.getElementById(`ambulanceRow_${ambulanceId}`);
    deleteAmbulanceMapData(ambulanceId);
    if (ambulanceRow) {
      ambulanceRow.remove();
    } else {
      console.error(`Ambulance row for ID ${ambulanceId} not found.`);
    }
  });

  socket.on("redirect", function () {
    window.location.href = "http://localhost:5557";
  });

  socket.on("connect", function () {
    console.log("Connected to server (SIMULATION): ", socket.id);
    setTimeout(function () {
      socket.emit("main_ambulance_isan", { isan: ISAN });
      setTimeout(function () {
        socket.emit("start_tracking", { isan: ISAN });
      }, 1000);
    }, 1000);
  });

  socket.on("main_ambulance_id", function (data) {
    if (data && data.id) {
      mainAmbulanceId = data.id;
      console.log(`Main ambulance ID updated to: ${mainAmbulanceId}`);
    } else {
      console.log("Failed to update mainAmbulanceId. No ID received.");
    }
  });

  socket.on("position_update", function (ambulances) {
    if (ambulances.length > 0) {
      updateMap(ambulances);
    } else {
      console.log("No data in ambulances, skipping updateMap.");
    }
  });

  window.addEventListener("beforeunload", function () {
    socket.disconnect();
    console.log("Disconnected from server");
  });
}