# # **Blocklist Management Platform - Developer Specification**

### *Version 1.0 - Architecture, API, DB, Security, Deployment & Front-End Specification*

### *Target Stack: Python (Flask for dev, Uvicorn for prod), pure ES6 front-end, PostgreSQL, Docker*

***

# # **0. Configuration**

Configuration is managed primarily through:

*   **Environment variables** (preferred)
*   `.env` file loaded at container startup

All configuration values MUST be injectable via environment variables.  
Nothing may be hardcoded in the container image.

### **0.1 Expected Configuration Variables**

    # OIDC
    OIDC_ISSUER=
    OIDC_CLIENT_ID=
    OIDC_CLIENT_SECRET=
    OIDC_AUTH_ENDPOINT=
    OIDC_TOKEN_ENDPOINT=
    OIDC_JWKS_URI=
    OIDC_REDIRECT_URI=
    OIDC_REQUIRED_GROUP=   # Optional; if present → mandatory for access

    # Session
    SESSION_SECRET=

    # Global Basic Auth for /api/list
    LIST_BASIC_AUTH_USER=
    LIST_BASIC_AUTH_PASSWORD=

    # Database
    DB_HOST=
    DB_PORT=5432
    DB_NAME=
    DB_USER=
    DB_PASSWORD=

    # App
    APP_PORT=8080
    APP_LOG_LEVEL=INFO

    # Lists Configuration
    DEFAULT_LIST=default

***

# # **1. Authentication & SSO (OIDC)**

## **1.1 Login Flow**

The application implements **Authorization Code Flow + PKCE**, directly within Flask.  
No reverse proxy intervention is required for authentication.

Sequence:

1.  User visits `/` or any protected endpoint.
2.  If no valid session → redirect to IdP with:
    *   `prompt=none` (first attempt)
3.  If IdP returns `login_required`, retry with:
    *   standard prompt (interactive login)
4.  After authentication, the app receives an authorization code.
5.  The app exchanges it for:
    *   ID Token (mandatory)
6.  Claims are extracted and validated.
7.  User session is created (short-lived, no refresh, expires after one hour or when browser closed).

## **1.2 Authorization Rules**

*   If `OIDC_REQUIRED_GROUP` is **defined**:
    *   The user MUST have this group in their `groups` claim.
    *   If group is missing → **deny access**.
*   If no group is defined → all authenticated users are allowed.

## **1.3 User Identity Model**

*   Authoritative identity: `email` claim
*   Other used claims:
    *   `name`
    *   `groups`

## **1.4 Logout**

*   **No logout endpoint is implemented.**
*   User session expires naturally.
*   Identity Provider controls SSO session lifetime.

***

# # **2. HTTPS & Reverse Proxy**

The Flask/Uvicorn app runs **HTTP only**.

A mandatory reverse proxy (nginx/traefik/caddy) handles:

*   TLS termination
*   HSTS
*   CSP
*   Rate limiting
*   Basic security headers
*   Network ACLs (e.g., restricting `/api/list` to Fortigate IPs)

The application is **never exposed publicly**.

### **2.1 Example Reverse Proxy Responsibilities**

*   Only allow external port 443
*   Redirect HTTP → HTTPS
*   Block requests to `/api/list` except:
    *   Fortigate IP sources
    *   Requests with expected Basic Auth credentials

***

# # **3. Database / Storage Backend**

Persistence relies exclusively on **PostgreSQL**.  
App containers are stateless.

### **3.1 Expected Data Volume**

*   Active entries: max **1,000–2,000**
*   Audit log: unbounded (low volume - a few entries per week)

### **3.2 Tables**

#### **3.2.1 `blocklist_entries`**

Tracks active entries.

| Field       | Type        | Description                                           |
| ----------- | ----------- | ----------------------------------------------------- |
| id          | SERIAL PK   | Entry ID                                              |
| list\_name  | TEXT        | Name of list (`default`, `inbound`, `outbound`, etc.) |
| ip          | INET        | IP address                                            |
| reason      | TEXT        | Free text reason                                      |
| added\_by   | TEXT        | Email of the user                                     |
| added\_at   | TIMESTAMPTZ | Timestamp                                             |
| expires\_at | TIMESTAMPTZ | Expiration time                                       |

**Constraints:**

*   `(list_name, ip)` must be **unique**
*   Expired rows are not kept here - removed after expiry

***

#### **3.2.2 `audit_logs`**

Append-only audit trail.

| Field       | Type        | Description                                    |
| ----------- | ----------- | ---------------------------------------------- |
| id          | SERIAL PK   | Log ID                                         |
| list\_name  | TEXT        | List name                                      |
| ip          | INET        | IP                                             |
| action      | TEXT        | `add`, `remove`, `expire`                      |
| user\_email | TEXT        | Actor email (if system-driven → `"system"`)    |
| reason      | TEXT        | Reason (for add), or cause (for remove/expire) |
| expires\_at | TIMESTAMPTZ | Expiration timestamp                           |
| timestamp   | TIMESTAMPTZ | When the action happened                       |

**Rules:**

*   Rows are **never** updated or deleted.
*   Each entry is also logged via **syslog**.

***

# # **4. Back-End API Specification**

All non-Fortigate endpoints require **session cookie**.

The Fortigate-facing endpoint requires **Basic Auth**.

***

## **4.1 Blocklist API**

### **4.1.1 GET `/api/list?id=<list_name>`**

Produces raw text list for EDL.

*   **Auth:** Basic Auth
*   **Output:** Pure IP list, one per line, deduplicated
*   **Triggers expiration cleanup**

**Example Response:**

    198.51.100.3
    203.0.113.42

***

### **4.1.2 GET `/api/entries?list=<list_name>`**

Returns all active entries for the chosen list.

*   **Auth:** session cookie
*   **Output:** JSON array of entries

***

### **4.1.3 POST `/api/entries`**

Creates a new entry.

Body:

    {
      "list_name": "default",
      "ip": "203.0.113.42",
      "reason": "Manual block",
      "expires_in": "1w"   // One of: 1d, 1w, 1m, 3m, 6m, 1y
    }

*   **Auth:** session cookie
*   **Actions:**
    *   Validate IP format
    *   Validate list name
    *   Insert DB row
    *   Write audit log (DB + syslog)

***

### **4.1.4 PUT `/api/entries/<ip>`**

Modifies reason or expiration.

Body:

    {
      "list_name": "default",
      "reason": "Updated reason",
      "expires_in": "1m"
    }

*   **Auth:** session cookie
*   **Audit recorded**

***

### **4.1.5 DELETE `/api/entries/<ip>?list=<name>`**

Deletes an entry.

*   **Auth:** session cookie
*   **Audit:** action=`remove`

***

## **4.2 Audit API**

### **4.2.1 GET `/api/audit`**

Returns paginated audit rows.

### **4.2.2 GET `/api/history/<ip>`**

Shows all audit rows related to an IP.

***

# # **5. Housekeeping Logic**

Triggered automatically by any request to:

    GET /api/list?id=...

### **5.1 Steps**

1.  Query all entries where `expires_at < now()`
2.  For each:
    *   Insert audit row (`expire`)
    *   Delete active entry
    *   Log to syslog
3.  Regenerate final IP list
4.  Return output

### **5.2 Notes**

*   Housekeeping MUST be idempotent.
*   If called twice with no expired entries → no side effects.

***

# # **6. Front-End Specification (Pure ES6)**

The front-end runs **pure ES6**, no frameworks, no external CDN.

### **6.1 Structure**

    /static/
        index.html
        css/style.css
        js/main.js
        js/api.js
        js/render.js
        js/util.js

### **6.2 Dark Mode**

*   Default color scheme
*   Prefer CSS variables for easy theme adjustments

***

## **6.3 Screens / Components**

### **6.3.1 List View**

Displays all active entries.

*   Entire list rendered as `<div>` blocks (not `<table>`)
*   Sortable by:
    *   IP
    *   Reason
    *   Added by
    *   Added at
    *   Expires at
*   Manual refresh button
*   Delete button with confirmation popup

***

### **6.3.2 Add Entry Form**

Fields:

*   IP input (validation)
*   Reason (mandatory)
*   Expiration dropdown with:
    *   1 day
    *   1 week
    *   1 month
    *   3 months
    *   6 months
    *   1 year

***

### **6.3.3 Bulk Add Form**

*   Textarea with one IP per line
*   Reason dropdown
*   Expiration dropdown
*   Bulk validation
*   Sends a sequence of POST requests

***

### **6.3.4 Audit View**

*   Searchable on the client side (filtering)
*   Not exportable
*   Rendered via virtual scrolling (if dataset grows too large)

***

### **6.3.5 Error Handling**

All errors shown via a top-floating banner.

***

# # **7. Deployment Model (Docker)**

Three containers:

    services:
      app:
        image: blocklist-app:latest
        ports: [8080]
        depends_on: [db]
        environment:
          (all env variables)
        restart: unless-stopped

      proxy:
        image: nginx:stable
        volumes:
          - ./nginx.conf:/etc/nginx/nginx.conf
        ports:
          - "443:443"
        depends_on: [app]
        restart: unless-stopped

      db:
        image: postgres:16-alpine
        environment:
          POSTGRES_DB=${DB_NAME}
          POSTGRES_USER=${DB_USER}
          POSTGRES_PASSWORD=${DB_PASSWORD}
        volumes:
          - pgdata:/var/lib/postgresql/data
        restart: unless-stopped

### **7.1 Persistence**

*   DB uses Docker volume `pgdata`
*   App container is stateless

### **7.2 Upgrade Procedure**

    docker compose down
    docker compose pull -a
    docker compose up -d

***

# # **8. Access Control & Authorization**

*   Authorization via OIDC group if configured
*   Admin = full access
*   No read-only mode
*   No multi-group support
*   Deletes require confirmation
*   Unlimited number of entries per user

***

# # **9. Audit Logging**

### **9.1 Requirements**

*   Append-only DB table
*   Each audit event also logged to system syslog
*   Fields included:
    *   IP
    *   User
    *   Action
    *   Reason
    *   Expiration
    *   Timestamp
    *   List name

### **9.2 No export option in UI**

Audit log stays view-only.

***

# # **10. Expiration Handling**

### **10.1 Rules**

*   Expired entries removed from `blocklist_entries`
*   Always logged in `audit_logs`
*   Triggered on:
    *   `/api/list` calls

### **10.2 No notifications**

No email or Teams webhook.

***

# # **11. EDL Publishing**

### **11.1 Requirements**

*   Endpoint:
        GET /api/list?id=<list>
*   Returns:
    *   One IP per line
    *   No comments
    *   Deduplicated
*   Basic Auth required
*   Reverse proxy must enforce ACLs

***

# # **12. Security Requirements**

### **12.1 Application**

*   Strict input validation
*   Context-sensitive output escaping
*   CSRF protection for all write calls
*   Avoid running as root inside container
*   No extra sandboxing required for v1

### **12.2 Reverse Proxy**

*   Rate limiting
*   HSTS
*   CSP headers
*   Optional WAF (future)

***

# # **13. Operational Constraints**

*   \~10 sysadmins
*   \~1000 active entries
*   Edits \~ weekly
*   Restart-safe
*   Backup: admin may run `pg_dump` manually
*   No HA required

***

# # **14. Developer Guidelines**

### **14.1 Python**

*   Development server: Flask built-in
*   Production server: Uvicorn
*   Use async I/O for the OIDC token exchange
*   Use psycopg2 or asyncpg for DB
*   No ORM, only reviewable SQL queries - parametrized queries to avoid SQL injection
*   Use Python `logging` + syslog handler

### **14.2 Front-End**

*   ES modules
*   No bundler
*   No dependencies
*   Use `fetch()` for all requests
*   Use only locally packaged JS/CSS

***

# # **15. Minimum CI/CD**

(Not implemented but recommended)

*   Lint Python with `flake8`
*   Validate Dockerfile builds
*   Run DB migrations automatically on app startup
*   Optional pytest suite

***

# # **✔ Document Complete**
