# QueueFlow AI Backend API

This document describes the Flask routes currently implemented in `backend/app.py`.
It reflects the existing implementation; it does not describe planned endpoints.

## Base URL and access

When started with `python app.py` from the `backend` directory, Flask listens at:

```text
http://127.0.0.1:5000
```

The local API base URL is therefore `http://127.0.0.1:5000/api`.
The development server binds to localhost by default. A React app running on the
same computer can use this URL. A frontend on a different device cannot reach
that loopback address; the backend would need to be deliberately configured to
listen on a reachable network interface and the frontend would need to use that
host address.

Flask-CORS is configured with `CORS(app, resources={r"/api/*": {"origins": "*"}})`.
This allows browser requests from any origin to `/api/*`. It is permissive and
should be restricted to trusted frontend origins before production deployment.

**Authentication:** None of the current endpoints requires authentication.
This includes the `/api/admin/*` endpoints; their URLs do not enforce an admin
login or role check.

## Response conventions

Successful responses use:

```json
{
  "success": true,
  "data": {}
}
```

Errors use:

```json
{
  "success": false,
  "error": {
    "code": "error_code",
    "message": "Human-readable description."
  }
}
```

Unless specified otherwise, request bodies must be JSON objects and IDs are
positive integers. Timestamps are returned as ISO-formatted strings.

## Endpoints

### Health check

- **Method and URL:** `GET /api/health`
- **Purpose:** Runs a simple database query to check API/database availability.
- **Request body:** None.
- **Authentication:** Not required.
- **Success (`200`):**

  ```json
  {
    "success": true,
    "data": {
      "status": "ok",
      "database": true
    }
  }
  ```

- **Errors:** `503 database_unavailable` if the database query fails.

### List departments

- **Method and URL:** `GET /api/departments`
- **Purpose:** Lists departments ordered by name.
- **Request body:** None.
- **Authentication:** Not required.
- **Success (`200`):**

  ```json
  {
    "success": true,
    "data": [
      {
        "id": 1,
        "name": "Examination",
        "description": "Examinations, results, transcripts, and academic records.",
        "is_active": 1
      }
    ]
  }
  ```

  `data` contains the department rows returned by the database, with `id`,
  `name`, `description`, and `is_active`.

- **Errors:** `500 database_error` if departments cannot be retrieved.

### List services

- **Method and URL:** `GET /api/services`
- **Purpose:** Lists active services, optionally filtered by department.
- **Query parameter:** `department_id` (optional positive integer). Example:
  `GET /api/services?department_id=1`.
- **Request body:** None.
- **Authentication:** Not required.
- **Success (`200`):**

  ```json
  {
    "success": true,
    "data": [
      {
        "id": 1,
        "department_id": 1,
        "name": "Transcript Request",
        "description": "Request an official academic transcript.",
        "estimated_duration_minutes": 15,
        "is_active": 1
      }
    ]
  }
  ```

  The response includes active services only, ordered by department ID and
  service name. An unknown but valid department ID returns an empty list.

- **Errors:** `400 invalid_department_id` if `department_id` is not a positive
  integer; `500 database_error` if services cannot be retrieved.

### List counters

- **Method and URL:** `GET /api/counters` (also available as `GET /api/admin/counters`)
- **Purpose:** Lists active service counters, optionally filtered by department.
- **Query parameter:** `department_id` (optional positive integer). Example:
  `GET /api/counters?department_id=1`.
- **Request body:** None.
- **Authentication:** Not required.
- **Success (`200`):**

  ```json
  {
    "success": true,
    "data": [
      {
        "id": 10,
        "department_id": 1,
        "department_name": "Examination",
        "counter_name": "Counter 1 - Transcripts & Records",
        "location": "Building A, Room 101",
        "is_active": 1
      }
    ]
  }
  ```

- **Errors:** `400 invalid_department_id` if `department_id` is not a positive
  integer; `500 database_error` if counters cannot be retrieved.

### Student registration

- **Method and URL:** `POST /api/users`
- **Purpose:** Registers a student. The stored password is hashed by the backend.
- **Required JSON body:**

  ```json
  {
    "full_name": "Asha Student",
    "email": "asha@example.edu",
    "password": "example-password"
  }
  ```

  `full_name` must be a non-empty string of at most 120 characters. `email`
  must be a valid-looking email string of at most 254 characters. `password`
  must contain 8–128 characters.

- **Authentication:** Not required.
- **Success (`201`):**

  ```json
  {
    "success": true,
    "data": {
      "user_id": 42
    }
  }
  ```

- **Errors:** `400 invalid_json`, `400 invalid_full_name`, `400 invalid_email`,
  or `400 invalid_password`; `409 email_already_registered` for a duplicate
  email; `500 database_error` for a database failure.

### Generate a token and QR code

- **Method and URL:** `POST /api/tokens`
- **Purpose:** Creates a Waiting token for an active user and service. The token
  code is unique; queue numbers are assigned per service and date.
- **Required JSON body:**

  ```json
  {
    "user_id": 42,
    "service_id": 1
  }
  ```

- **Authentication:** Not required.
- **Success (`201`):**

  ```json
  {
    "success": true,
    "data": {
      "token_id": 101,
      "service_id": 1,
      "queue_date": "2026-11-13",
      "queue_number": 7,
      "token_code": "0123456789ABCDEF0123456789ABCDEF",
      "status": "Waiting",
      "created_at": "2026-11-13T10:00:00",
      "qr_code_base64": "<Base64-encoded PNG image>",
      "qr_code_mime_type": "image/png"
    }
  }
  ```

  The QR image encodes a JSON object containing the token code, not database
  credentials or student details.

- **Errors:** `400 invalid_json`, `400 invalid_user_id`, or
  `400 invalid_service_id`; `404 user_not_found` or `404 service_not_found`
  when the specified active record is not found; `500 database_error` or
  `500 token_generation_error` if token creation fails.

### Student: track a token

- **Method and URL:** `GET /api/tokens/<token_reference>`
- **Purpose:** Retrieves token status and queue estimate by token ID or token
  code. A numeric path segment is treated as an ID; a 32-character
  hexadecimal segment is treated as a token code.
- **Request body:** None.
- **Authentication:** Not required.
- **Examples:** `GET /api/tokens/101` or
  `GET /api/tokens/0123456789ABCDEF0123456789ABCDEF`.
- **Success (`200`):**

  ```json
  {
    "success": true,
    "data": {
      "token_id": 101,
      "token_number": 7,
      "token_code": "0123456789ABCDEF0123456789ABCDEF",
      "service_id": 1,
      "service_name": "Transcript Request",
      "department_id": 1,
      "department_name": "Examination",
      "queue_date": "2026-11-13",
      "created_at": "2026-11-13T10:00:00",
      "status": "Waiting",
      "queue_position": 3,
      "people_ahead": 2,
      "estimated_wait_minutes": 30,
      "estimate_basis": "configured_service_duration",
      "counter_id": null,
      "counter_name": null,
      "counter_location": null,
      "qr_code_base64": "<Base64-encoded PNG image>",
      "qr_code_mime_type": "image/png"
    }
  }
  ```

  Active queue statuses are Waiting, Called, and Serving. Queue position counts
  earlier active tokens in the same service and queue date. Completed, Skipped,
  and Cancelled tokens have `queue_position: null`, zero `people_ahead`, and
  zero estimated wait.

  When a token has been called or served, `counter_id`, `counter_name`, and
  `counter_location` reflect the serving counter. The QR code image is
  retrievable at any time.

  The wait is calculated as `people_ahead × service duration in minutes`.
  When at least three positive-duration service-history samples exist, the
  rounded average is used. Otherwise, the service's configured estimated
  duration is used (or a 10-minute fallback if unavailable). The response's
  `estimate_basis` is `service_history_average`,
  `configured_service_duration`, `fallback`, or `not_queued`. This is a
  duration-based estimate, not an AI prediction.

- **Errors:** `400 invalid_token_id` for a nonpositive/oversized numeric ID;
  `400 invalid_token_reference` for an invalid path reference;
  `404 token_not_found` for a valid-shaped but unknown ID/code;
  `500 database_error` if token data cannot be retrieved.

### Admin: view active queues and status

- **Method and URL:** `GET /api/admin/queues` (also available as `GET /api/queues`)
- **Purpose:** Retrieves today's queue tokens, summary metrics, and current active counter token.
- **Query parameters:**
  - `department_id` (optional positive integer)
  - `counter_id` (optional positive integer)
- **Request body:** None.
- **Authentication:** Not required.
- **Success (`200`):**

  ```json
  {
    "success": true,
    "data": {
      "queue_date": "2026-11-13",
      "summary": {
        "waiting_count": 4,
        "called_count": 1,
        "completed_count": 12,
        "skipped_count": 1,
        "total_count": 18
      },
      "current_token": {
        "token_id": 101,
        "service_name": "Transcript Request",
        "queue_number": 7,
        "status": "Called",
        "counter_id": 10,
        "counter_name": "Counter 1 - Transcripts & Records"
      },
      "tokens": [
        {
          "token_id": 101,
          "service_id": 1,
          "service_name": "Transcript Request",
          "department_id": 1,
          "department_name": "Examination",
          "user_id": 42,
          "student_name": "Asha Student",
          "student_email": "asha@example.edu",
          "queue_date": "2026-11-13",
          "queue_number": 7,
          "token_code": "0123456789ABCDEF0123456789ABCDEF",
          "status": "Called",
          "counter_id": 10,
          "counter_name": "Counter 1 - Transcripts & Records",
          "created_at": "2026-11-13T10:00:00",
          "called_at": "2026-11-13T10:04:00",
          "completed_at": null
        }
      ]
    }
  }
  ```

- **Errors:** `400 invalid_department_id` or `400 invalid_counter_id`; `500 database_error`.

### Admin: call the next token

- **Method and URL:** `POST /api/admin/call-next`
- **Purpose:** Calls the oldest Waiting token belonging to an active service in
  the specified active counter's department. The counter assignment is recorded
  in the queue history.
- **Required JSON body:**

  ```json
  {
    "counter_id": 10
  }
  ```

- **Authentication:** Not required by the current implementation.
- **Success (`200`):**

  ```json
  {
    "success": true,
    "data": {
      "token_id": 101,
      "service_id": 1,
      "service_name": "Transcript Request",
      "queue_date": "2026-11-13",
      "queue_number": 7,
      "token_code": "0123456789ABCDEF0123456789ABCDEF",
      "status": "Called",
      "counter_id": 10,
      "created_at": "2026-11-13T10:00:00",
      "called_at": "2026-11-13T10:04:00"
    }
  }
  ```

- **Errors:** `400 invalid_json` or `400 invalid_counter_id`;
  `404 counter_not_found` if the active counter does not exist;
  `404 queue_empty` if the department has no eligible Waiting tokens;
  `409 token_unavailable` if the selected token is no longer Waiting;
  `500 database_error` on a database failure.

### Admin: complete a token

- **Method and URL:** `POST /api/admin/complete`
- **Purpose:** Completes a Called or Serving token assigned to the specified
  counter. It stores completion time, service duration, a queue event, and a
  service-history record.
- **Required JSON body:**

  ```json
  {
    "token_id": 101,
    "counter_id": 10
  }
  ```

- **Authentication:** Not required by the current implementation.
- **Success (`200`):**

  ```json
  {
    "success": true,
    "data": {
      "token_id": 101,
      "counter_id": 10,
      "status": "Completed",
      "completed_at": "2026-11-13T10:12:00",
      "duration_seconds": 480
    }
  }
  ```

- **Errors:** `400 invalid_json`, `400 invalid_token_id`, or
  `400 invalid_counter_id`; `404 counter_not_found` or `404 token_not_found`;
  `409 counter_mismatch` if the token's department or recorded assignment does
  not match the counter; `409 invalid_token_status` unless status is Called or
  Serving; `409 service_start_missing` if no call/service start time exists;
  `409 token_already_completed` if service history already exists;
  `500 database_error` for other database failures.

### Admin: skip a token

- **Method and URL:** `POST /api/admin/skip`
- **Purpose:** Marks a Waiting or Called token Skipped and records the counter
  and status change.
- **Required JSON body:**

  ```json
  {
    "token_id": 102,
    "counter_id": 10
  }
  ```

- **Authentication:** Not required by the current implementation.
- **Success (`200`):**

  ```json
  {
    "success": true,
    "data": {
      "token_id": 102,
      "counter_id": 10,
      "status": "Skipped"
    }
  }
  ```

- **Errors:** `400 invalid_json`, `400 invalid_token_id`, or
  `400 invalid_counter_id`; `404 counter_not_found` or `404 token_not_found`;
  `409 counter_mismatch` if the token is outside the counter's department or a
  Called token is assigned to another counter; `409 invalid_token_status`
  unless status is Waiting or Called; `500 database_error` on a database
  failure.

## Student registration-to-token workflow

1. Register the student:

   ```http
   POST /api/users
   Content-Type: application/json
   ```

   ```json
   {
     "full_name": "Asha Student",
     "email": "asha@example.edu",
     "password": "example-password"
   }
   ```

   Response:

   ```json
   {
     "success": true,
     "data": {
       "user_id": 42
     }
   }
   ```

2. List departments and select a service:

   ```http
   GET /api/departments
   GET /api/services?department_id=1
   ```

3. Generate a token using the returned user ID and selected service ID:

   ```http
   POST /api/tokens
   Content-Type: application/json
   ```

   ```json
   {
     "user_id": 42,
     "service_id": 1
   }
   ```

   Save the returned `token_id` or `token_code` for tracking and display
   `qr_code_base64` as a PNG image.

4. Track the token:

   ```http
   GET /api/tokens/101
   ```

   The frontend periodically refreshes this request to display status,
   position, assigned counter, and estimated wait.

## Admin counter workflow

1. Fetch active counters:

   ```http
   GET /api/counters?department_id=1
   ```

2. Select a counter and view active queue status:

   ```http
   GET /api/admin/queues?department_id=1&counter_id=10
   ```

3. Call the next student token:

   ```http
   POST /api/admin/call-next
   Content-Type: application/json
   ```

   ```json
   {
     "counter_id": 10
   }
   ```

4. Complete the token upon finishing service:

   ```http
   POST /api/admin/complete
   Content-Type: application/json
   ```

   ```json
   {
     "token_id": 101,
     "counter_id": 10
   }
   ```

5. Or skip a token if the student is absent:

   ```http
   POST /api/admin/skip
   Content-Type: application/json
   ```

   ```json
   {
     "token_id": 101,
     "counter_id": 10
   }
   ```

## Connecting a React frontend

Set the API base URL in the React app's environment configuration:

```text
VITE_API_BASE_URL=http://127.0.0.1:5000/api
```

Example request:

```javascript
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL;

const response = await fetch(`${API_BASE_URL}/services?department_id=1`);
const result = await response.json();

if (!response.ok || !result.success) {
  throw new Error(result.error?.message ?? "Request failed");
}

console.log(result.data);
```

For JSON POST requests, set `Content-Type: application/json` and stringify the body.

To display a returned QR PNG:

```jsx
<img
  alt="Queue token QR code"
  src={`data:${token.qr_code_mime_type};base64,${token.qr_code_base64}`}
/>
```
