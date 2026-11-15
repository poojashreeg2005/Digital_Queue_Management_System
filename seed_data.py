
from flask import Flask

from config import Config
from models import db, Department, Service, Counter


app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)


def seed_database():

    department_data = [
        {
            "name": "Student Administration",
            "building": "Main Administrative Block",
            "floor": "Ground Floor",
            "room": "Room 101",
            "directions": "Enter the main block and turn left near the reception.",
            "contact_person": "Student Services Desk",
            "contact_phone": "0800000001",
            "contact_email": "studentservices@example.com",
            "daily_limit": 60
        },
        {
            "name": "Technical Support",
            "building": "Technology Block",
            "floor": "First Floor",
            "room": "Room 204",
            "directions": "Use the main staircase and turn right on the first floor.",
            "contact_person": "IT Support Desk",
            "contact_phone": "0800000002",
            "contact_email": "itsupport@example.com",
            "daily_limit": 30
        },
        {
            "name": "Library Services",
            "building": "Central Library",
            "floor": "Ground Floor",
            "room": "Counter L1",
            "directions": "Enter through the library entrance and proceed to the service counter.",
            "contact_person": "Library Help Desk",
            "contact_phone": "0800000003",
            "contact_email": "library@example.com",
            "daily_limit": 80
        }
    ]

    service_data = {
        "Student Administration": [
            {
                "name": "Bonafide Certificate Request",
                "description": "Request and track your bonafide certificate.",
                "estimated_minutes": 15,
                "fee": 0
            },
            {
                "name": "Student ID Card Assistance",
                "description": "Get assistance with new or replacement student ID cards.",
                "estimated_minutes": 20,
                "fee": 50
            },
            {
                "name": "Fee Payment Assistance",
                "description": "Get help with tuition fee and payment-related queries.",
                "estimated_minutes": 15,
                "fee": 0
            }
        ],

        "Technical Support": [
            {
                "name": "Wi-Fi and Network Support",
                "description": "Report and resolve campus network connectivity issues.",
                "estimated_minutes": 20,
                "fee": 0
            },
            {
                "name": "Computer and Lab Assistance",
                "description": "Get help with computer systems and laboratory equipment.",
                "estimated_minutes": 30,
                "fee": 0
            }
        ],

        "Library Services": [
            {
                "name": "Book Issue and Return",
                "description": "Get assistance with issuing and returning library books.",
                "estimated_minutes": 10,
                "fee": 0
            },
            {
                "name": "Library Account Assistance",
                "description": "Resolve library account and membership issues.",
                "estimated_minutes": 15,
                "fee": 0
            }
        ]
    }

    new_departments = 0
    new_services = 0
    new_counters = 0

    for department_info in department_data:

        department = Department.query.filter_by(
            name=department_info["name"]
        ).first()

        if department is None:
            department = Department(**department_info)
            db.session.add(department)
            db.session.flush()
            new_departments += 1

        # Create a sample counter for each department.
        counter = Counter.query.filter_by(
            department_id=department.id,
            name="Main Service Counter"
        ).first()

        if counter is None:
            counter = Counter(
                department_id=department.id,
                name="Main Service Counter",
                building=department.building,
                floor=department.floor,
                room=department.room,
                directions=department.directions,
                active=True
            )

            db.session.add(counter)
            new_counters += 1

        # Add the services belonging to this department.
        for service_info in service_data[department.name]:

            existing_service = Service.query.filter_by(
                department_id=department.id,
                name=service_info["name"]
            ).first()

            if existing_service is None:

                service = Service(
                    department_id=department.id,
                    name=service_info["name"],
                    description=service_info["description"],
                    estimated_minutes=service_info["estimated_minutes"],
                    fee=service_info["fee"],
                    active=True
                )

                db.session.add(service)
                new_services += 1

    db.session.commit()

    print("\n========== QUEUEFLOW SEED RESULTS ==========")
    print("New departments:", new_departments)
    print("New services:", new_services)
    print("New counters:", new_counters)

    print("\nDepartments in database:")

    for department in Department.query.order_by(Department.id).all():
        print("-", department.name)

    print("\nServices in database:")

    for service in Service.query.order_by(Service.id).all():
        print("-", service.name)

    print("\nSample data setup completed successfully!")


if __name__ == "__main__":

    with app.app_context():

        try:
            seed_database()

        except Exception as error:
            db.session.rollback()
            print("Error while adding sample data:")
            print(error)
            raise
