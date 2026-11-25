/* Fictional QueueFlow demonstration data; offsets are illustrative, not surveyed locations. */
window.QUEUEFLOW_DEMO_CAMPUS = {
    locations: [
        {
            id: "main-entrance",
            name: "Main Entrance and Security Gate",
            category: "entrance",
            symbol: "↗",
            east: 0,
            north: -340,
            description: "Illustrative campus entrance and visitor security checkpoint."
        },
        {
            id: "administrative-block",
            name: "Administrative Block",
            category: "administration",
            symbol: "A",
            east: -70,
            north: -150,
            description: "Demonstration location for campus administration and office services."
        },
        {
            id: "computer-science",
            name: "Computer Science Department",
            category: "department",
            symbol: "CS",
            east: 145,
            north: 110,
            description: "Illustrative department location for the campus map demo."
        },
        {
            id: "electronics-communication",
            name: "Electronics and Communication Department",
            category: "department",
            symbol: "EC",
            east: 255,
            north: 70,
            description: "Illustrative department location for the campus map demo."
        },
        {
            id: "library",
            name: "Library",
            category: "facility",
            symbol: "L",
            east: -250,
            north: 5,
            description: "Fictional library marker; its position is not an actual building location."
        },
        {
            id: "computer-laboratories",
            name: "Computer Laboratories",
            category: "facility",
            symbol: "⌘",
            east: 95,
            north: 220,
            description: "Illustrative computer laboratory location."
        },
        {
            id: "canteen",
            name: "Canteen",
            category: "facility",
            symbol: "C",
            east: 260,
            north: -175,
            description: "Fictional campus facility marker for demonstration."
        },
        {
            id: "auditorium",
            name: "Auditorium",
            category: "facility",
            symbol: "H",
            east: -220,
            north: 205,
            description: "Fictional campus facility marker for demonstration."
        },
        {
            id: "student-services",
            name: "Student Services",
            category: "service",
            symbol: "S",
            east: -170,
            north: -95,
            description: "Illustrative student support and services location."
        },
        {
            id: "visitor-reception",
            name: "Visitor Reception",
            category: "reception",
            symbol: "R",
            east: 45,
            north: -105,
            description: "Illustrative visitor information and reception point."
        },
        {
            id: "parking-area",
            name: "Parking Area",
            category: "parking",
            symbol: "P",
            east: -155,
            north: -365,
            description: "Fictional visitor parking marker for the map demo."
        },
        {
            id: "main-academic-block",
            name: "Main Academic Block",
            category: "academic",
            symbol: "M",
            east: 5,
            north: 45,
            description: "Illustrative academic block containing demo classrooms and laboratories."
        }
    ],
    indoorBuildings: [
        {
            id: "administrative-block",
            name: "Administrative Block",
            floors: [
                {
                    id: "ground-floor",
                    name: "Ground Floor",
                    rooms: [
                        {
                            name: "Reception",
                            description: "Illustrative visitor welcome and information desk.",
                            directions: "Enter through the main entrance, walk straight along the corridor; reception is on your left.",
                            row: "north"
                        },
                        {
                            name: "Accounts Office",
                            description: "Demonstration office for fee and account enquiries.",
                            directions: "Enter through the main entrance and continue straight; the Accounts Office is beside reception.",
                            row: "north"
                        },
                        {
                            name: "Admission Office",
                            description: "Demonstration office for admission enquiries.",
                            directions: "Enter through the main entrance, walk straight, then turn right at the corridor.",
                            row: "north"
                        },
                        {
                            name: "Waiting Area",
                            description: "Illustrative visitor seating area.",
                            directions: "Enter through the main entrance; the waiting area is opposite reception.",
                            row: "south"
                        },
                        {
                            name: "Stairs",
                            description: "Illustrative stair access to the first floor.",
                            directions: "Follow the corridor to the end of the hall; the stairs are on your right.",
                            row: "south"
                        }
                    ]
                },
                {
                    id: "first-floor",
                    name: "First Floor",
                    rooms: [
                        {
                            name: "Principal Office",
                            description: "Illustrative office location on the first floor.",
                            directions: "Take the stairs from the ground floor and turn left at the landing.",
                            row: "north"
                        },
                        {
                            name: "Administration Office",
                            description: "Demonstration administrative office.",
                            directions: "Take the stairs to the first floor and walk straight along the corridor.",
                            row: "north"
                        },
                        {
                            name: "Meeting Room",
                            description: "Illustrative meeting space.",
                            directions: "Take the stairs to the first floor; the meeting room is at the end of the left corridor.",
                            row: "south"
                        },
                        {
                            name: "Staff Room",
                            description: "Illustrative staff space.",
                            directions: "Take the stairs to the first floor and turn right at the landing.",
                            row: "south"
                        },
                        {
                            name: "Stairs",
                            description: "Illustrative stair access between floors.",
                            directions: "Follow the corridor to the central landing for the stairs.",
                            row: "south"
                        }
                    ]
                }
            ]
        },
        {
            id: "main-academic-block",
            name: "Main Academic Block",
            floors: [
                {
                    id: "ground-floor",
                    name: "Ground Floor",
                    rooms: [
                        {
                            name: "Computer Lab 1",
                            description: "Illustrative computer laboratory.",
                            directions: "Enter the academic block and follow the main corridor; Computer Lab 1 is on your left.",
                            row: "north"
                        },
                        {
                            name: "Computer Lab 2",
                            description: "Illustrative computer laboratory.",
                            directions: "Enter the academic block and continue straight to the second laboratory entrance.",
                            row: "north"
                        },
                        {
                            name: "Classroom 1",
                            description: "Illustrative ground-floor classroom.",
                            directions: "Enter the academic block and turn right along the main corridor.",
                            row: "north"
                        },
                        {
                            name: "Classroom 2",
                            description: "Illustrative ground-floor classroom.",
                            directions: "Follow the ground-floor corridor past Computer Lab 2.",
                            row: "south"
                        },
                        {
                            name: "Department Office",
                            description: "Illustrative academic department office.",
                            directions: "Enter the block, walk straight, then turn left at the corridor junction.",
                            row: "south"
                        },
                        {
                            name: "Stairs",
                            description: "Illustrative stair access to the first floor.",
                            directions: "Follow the corridor to the central stairwell.",
                            row: "south"
                        }
                    ]
                },
                {
                    id: "first-floor",
                    name: "First Floor",
                    rooms: [
                        {
                            name: "Classroom 3",
                            description: "Illustrative first-floor classroom.",
                            directions: "Take the stairs to the first floor and turn left along the corridor.",
                            row: "north"
                        },
                        {
                            name: "Classroom 4",
                            description: "Illustrative first-floor classroom.",
                            directions: "Take the stairs to the first floor and continue straight.",
                            row: "north"
                        },
                        {
                            name: "Faculty Room",
                            description: "Illustrative faculty workspace.",
                            directions: "Take the stairs to the first floor, then turn right at the landing.",
                            row: "south"
                        },
                        {
                            name: "Seminar Room",
                            description: "Illustrative seminar and presentation room.",
                            directions: "Walk along the first-floor corridor to the far end.",
                            row: "south"
                        },
                        {
                            name: "Stairs",
                            description: "Illustrative stair access between floors.",
                            directions: "Follow the corridor to the central stairwell.",
                            row: "south"
                        }
                    ]
                }
            ]
        }
    ]
};
