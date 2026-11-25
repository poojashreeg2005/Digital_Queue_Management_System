/**
 * Visitor campus map demo.
 * The marker positions and indoor layouts come only from campus_demo_data.js.
 */
document.addEventListener("DOMContentLoaded", function () {
    const demoCampus = window.QUEUEFLOW_DEMO_CAMPUS;
    const mapElement = document.getElementById("campus-map");
    const mapError = document.getElementById("campus-map-error");
    const directoryResults = document.getElementById("campus-directory-results");
    const searchInput = document.getElementById("campus-search");
    const directoryCount = document.getElementById("directory-count");
    const buildingInfo = document.getElementById("building-info");

    const createElement = function (tagName, className, text) {
        const element = document.createElement(tagName);
        if (className) element.className = className;
        if (text !== undefined) element.textContent = text;
        return element;
    };

    const showMapError = function (message) {
        if (mapError) {
            mapError.textContent = message;
            mapError.hidden = false;
        }
    };

    const categoryLabels = {
        entrance: "Entrance",
        administration: "Administration",
        department: "Department",
        facility: "Facility",
        service: "Student services",
        reception: "Visitor services",
        parking: "Parking",
        academic: "Academic building"
    };

    const markerClasses = {
        entrance: "entrance",
        administration: "building",
        department: "department",
        facility: "facility",
        service: "service",
        reception: "service",
        parking: "parking",
        academic: "building"
    };

    const markerColors = {
        entrance: "#17865b",
        administration: "#263c78",
        department: "#3268b2",
        facility: "#7254ca",
        service: "#087f8c",
        reception: "#087f8c",
        parking: "#bd7022",
        academic: "#263c78"
    };

    const locations = demoCampus && Array.isArray(demoCampus.locations)
        ? demoCampus.locations
        : [];
    const markers = {};
    let map = null;
    let selectedDirectoryId = null;

    const showBuildingInfo = function (location) {
        if (!buildingInfo) return;

        buildingInfo.textContent = "";
        buildingInfo.appendChild(createElement("h2", "", "Building information"));
        buildingInfo.appendChild(createElement(
            "span",
            `campus-category campus-category--${markerClasses[location.category] || "building"}`,
            categoryLabels[location.category] || "Campus location"
        ));
        buildingInfo.appendChild(createElement("h3", "building-info-name", location.name));
        buildingInfo.appendChild(createElement("p", "building-info-description", location.description));
        buildingInfo.appendChild(createElement(
            "p",
            "demo-data-note",
            "Illustrative demo location — not an actual building position."
        ));
    };

    const focusLocation = function (location) {
        selectedDirectoryId = location.id;
        showBuildingInfo(location);

        if (map && markers[location.id]) {
            map.flyTo(markers[location.id].getLatLng(), 18, { duration: 0.6 });
            markers[location.id].openPopup();
        } else if (!map && mapElement) {
            showMapError("The map is unavailable, but the selected location information is shown here.");
        }

        renderDirectory(searchInput ? searchInput.value : "");
    };

    const renderDirectory = function (query) {
        if (!directoryResults) return;
        directoryResults.textContent = "";

        const normalizedQuery = (query || "").trim().toLowerCase();
        const filteredLocations = locations.filter(function (location) {
            const searchableText = [
                location.name,
                location.description,
                categoryLabels[location.category]
            ].join(" ").toLowerCase();
            return searchableText.includes(normalizedQuery);
        });

        if (directoryCount) {
            directoryCount.textContent = `${filteredLocations.length} ${filteredLocations.length === 1 ? "place" : "places"}`;
        }

        if (!filteredLocations.length) {
            directoryResults.appendChild(createElement(
                "li",
                "directory-empty",
                "No demo locations match your search."
            ));
            return;
        }

        filteredLocations.forEach(function (location) {
            const item = createElement("li", "directory-item");
            item.setAttribute("role", "listitem");

            const button = createElement("button", "directory-result");
            button.type = "button";
            button.dataset.locationId = location.id;
            button.setAttribute("aria-pressed", String(selectedDirectoryId === location.id));
            if (selectedDirectoryId === location.id) {
                button.classList.add("is-selected");
            }

            const symbol = createElement(
                "span",
                `legend-marker ${markerClasses[location.category] || "building"}`,
                location.symbol
            );
            symbol.setAttribute("aria-hidden", "true");

            const text = createElement("span", "directory-result-text");
            text.appendChild(createElement("strong", "", location.name));
            text.appendChild(createElement(
                "small",
                "",
                categoryLabels[location.category] || "Campus location"
            ));

            button.appendChild(symbol);
            button.appendChild(text);
            button.appendChild(createElement("span", "directory-result-arrow", "›"));
            button.addEventListener("click", function () {
                focusLocation(location);
            });

            item.appendChild(button);
            directoryResults.appendChild(item);
        });
    };

    if (searchInput) {
        searchInput.addEventListener("input", function () {
            renderDirectory(this.value);
        });
    }

    renderDirectory("");

    const indoorBuildings = demoCampus && Array.isArray(demoCampus.indoorBuildings)
        ? demoCampus.indoorBuildings
        : [];
    const buildingSelect = document.getElementById("indoor-building-select");
    const floorSelect = document.getElementById("indoor-floor-select");
    const planLabel = document.getElementById("indoor-plan-label");
    const floorPlanElement = document.getElementById("indoor-floor-plan");
    const roomInfo = document.getElementById("room-info");

    const updateRoomInfo = function (room, building, floor) {
        if (!roomInfo) return;

        roomInfo.textContent = "";
        roomInfo.appendChild(createElement("span", "campus-category", "Illustrative room details"));
        roomInfo.appendChild(createElement("h3", "", room.name));
        roomInfo.appendChild(createElement("p", "", room.description));

        const directions = createElement("p", "room-directions");
        directions.appendChild(createElement("strong", "", "Illustrative directions: "));
        directions.appendChild(document.createTextNode(room.directions));
        roomInfo.appendChild(directions);
        roomInfo.appendChild(createElement(
            "small",
            "demo-data-note",
            `${building.name} · ${floor.name} · Static text only; no live indoor route is calculated.`
        ));
    };

    const updateDemoUrl = function (building, floor) {
        if (!window.history || !window.history.replaceState) return;

        const url = new URL(window.location.href);
        url.searchParams.set("demo_building", building.id);
        url.searchParams.set("demo_floor", floor.id);
        url.searchParams.delete("floor_plan_id");
        window.history.replaceState(null, "", url);
    };

    const renderFloor = function (building, floor) {
        if (!floorPlanElement) return;

        floorPlanElement.textContent = "";
        floorPlanElement.setAttribute(
            "aria-label",
            `Demonstration floor plan: ${building.name}, ${floor.name}`
        );
        if (planLabel) {
            planLabel.textContent = `DEMO LAYOUT · ${building.name} · ${floor.name}`;
        }

        const diagram = createElement("div", "floorplan-diagram");
        diagram.appendChild(createElement("div", "floorplan-entrance-label", "Illustrative main entrance"));

        const addRoomRow = function (rowName, rooms, offset) {
            const row = createElement("div", `floorplan-room-row floorplan-room-row--${rowName}`);
            rooms.forEach(function (room, index) {
                const button = createElement("button", "floorplan-room-marker");
                button.type = "button";
                button.setAttribute("aria-label", `${room.name}. View room description and illustrative directions.`);

                const markerNumber = createElement("span", "floorplan-room-number", String(offset + index + 1));
                markerNumber.setAttribute("aria-hidden", "true");
                button.appendChild(markerNumber);
                button.appendChild(createElement("span", "floorplan-room-name", room.name));
                button.addEventListener("click", function () {
                    updateRoomInfo(room, building, floor);
                });
                row.appendChild(button);
            });
            diagram.appendChild(row);
        };

        const northRooms = floor.rooms.filter(function (room) {
            return room.row === "north";
        });
        const southRooms = floor.rooms.filter(function (room) {
            return room.row !== "north";
        });

        addRoomRow("north", northRooms, 0);
        diagram.appendChild(createElement("div", "floorplan-corridor", "Main corridor · illustrative"));
        addRoomRow("south", southRooms, northRooms.length);
        floorPlanElement.appendChild(diagram);
        updateDemoUrl(building, floor);
    };

    const populateSelect = function (select, items, selectedId) {
        select.textContent = "";
        items.forEach(function (item) {
            const option = createElement("option", "", item.name);
            option.value = item.id;
            option.selected = item.id === selectedId;
            select.appendChild(option);
        });
    };

    const selectBuilding = function (buildingId, requestedFloorId) {
        const building = indoorBuildings.find(function (item) {
            return item.id === buildingId;
        });
        if (!building || !building.floors.length) return;

        const selectedFloor = building.floors.find(function (floor) {
            return floor.id === requestedFloorId;
        }) || building.floors[0];

        populateSelect(floorSelect, building.floors, selectedFloor.id);
        floorSelect.disabled = false;
        renderFloor(building, selectedFloor);
    };

    if (buildingSelect && floorSelect && indoorBuildings.length) {
        const query = new URLSearchParams(window.location.search);
        const requestedBuildingId = query.get("demo_building");
        const initialBuilding = indoorBuildings.find(function (building) {
            return building.id === requestedBuildingId;
        }) || indoorBuildings[0];

        populateSelect(buildingSelect, indoorBuildings, initialBuilding.id);
        buildingSelect.disabled = false;
        selectBuilding(initialBuilding.id, query.get("demo_floor"));

        buildingSelect.addEventListener("change", function () {
            selectBuilding(this.value, null);
        });
        floorSelect.addEventListener("change", function () {
            const building = indoorBuildings.find((item) => item.id === buildingSelect.value);
            const floor = building && building.floors.find((item) => item.id === this.value);
            if (building && floor) renderFloor(building, floor);
        });
    } else if (floorPlanElement) {
        floorPlanElement.textContent = "Indoor demonstration plans are unavailable.";
    }

    if (!demoCampus || !locations.length) {
        showMapError("Demonstration map data could not be loaded. Indoor and outdoor map data are unavailable.");
        return;
    }

    if (!mapElement) return;

    if (mapElement.dataset.mapInitialized === "true") return;
    if (typeof L === "undefined") {
        showMapError("The outdoor map library could not be loaded. Directory and indoor demonstrations remain available.");
        return;
    }

    mapElement.dataset.mapInitialized = "true";

    try {
        const center = {
            lat: Number(mapElement.dataset.defaultLat),
            lng: Number(mapElement.dataset.defaultLng)
        };
        const initialZoom = Number(mapElement.dataset.defaultZoom) || 16;
        map = L.map(mapElement, { zoomControl: true }).setView([center.lat, center.lng], initialZoom);

        const tileLayer = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        });
        tileLayer.on("tileerror", function () {
            showMapError("Map tiles could not be loaded. Check your connection; directory and indoor demonstrations remain available.");
        });
        tileLayer.addTo(map);

        const metersPerLongitudeDegree = 111320 * Math.cos(center.lat * Math.PI / 180);
        const markerPositions = [];

        const locationForMap = function (location) {
            return {
                lat: center.lat + location.north / 111320,
                lng: center.lng + location.east / metersPerLongitudeDegree
            };
        };

        locations.forEach(function (location) {
            const position = locationForMap(location);
            const markerClass = markerClasses[location.category] || "building";
            const markerNode = createElement(
                "span",
                `campus-map-marker campus-map-marker--${markerClass}`
            );
            markerNode.setAttribute("aria-hidden", "true");
            markerNode.appendChild(createElement("span", "campus-map-marker-symbol", location.symbol));

            const icon = L.divIcon({
                className: "campus-map-marker-wrap",
                html: markerNode,
                iconSize: [38, 38],
                iconAnchor: [19, 19],
                popupAnchor: [0, -18]
            });
            const marker = L.marker([position.lat, position.lng], {
                icon: icon,
                title: location.name,
                alt: location.name,
                keyboard: true
            }).addTo(map);
            const popup = createElement("div", "map-popup");
            popup.appendChild(createElement("h3", "", location.name));
            popup.appendChild(createElement(
                "span",
                `campus-category campus-category--${markerClass}`,
                categoryLabels[location.category] || "Campus location"
            ));
            popup.appendChild(createElement("p", "", location.description));
            popup.appendChild(createElement(
                "small",
                "demo-data-note",
                "Illustrative marker — not an actual building location."
            ));

            const directionsLink = createElement("a", "map-directions-link", "Open demo point in Google Maps ↗");
            const directionsUrl = new URL("https://www.google.com/maps/dir/");
            directionsUrl.searchParams.set("api", "1");
            directionsUrl.searchParams.set("destination", `${position.lat},${position.lng}`);
            directionsLink.href = directionsUrl.toString();
            directionsLink.target = "_blank";
            directionsLink.rel = "noopener noreferrer";
            popup.appendChild(directionsLink);

            marker.bindPopup(popup);
            marker.on("click", function () {
                selectedDirectoryId = location.id;
                showBuildingInfo(location);
                renderDirectory(searchInput ? searchInput.value : "");
            });

            markers[location.id] = marker;
            markerPositions.push([position.lat, position.lng]);
        });

        const fullCampusButton = document.getElementById("show-full-campus");
        if (fullCampusButton) {
            fullCampusButton.addEventListener("click", function () {
                if (!markerPositions.length) {
                    map.setView([center.lat, center.lng], initialZoom);
                    return;
                }
                map.fitBounds(L.latLngBounds(markerPositions), {
                    padding: [30, 30],
                    maxZoom: 16
                });
            });
        }
    } catch (error) {
        console.error("Campus demo map initialization failed:", error);
        showMapError("The outdoor map could not be initialized. Directory and indoor demonstrations remain available.");
    }
});
