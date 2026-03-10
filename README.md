
# **Dynamic Blocklist Manager**

*A lightweight, auditable, multi‑list IP blocklist service for Fortigate and other firewalls*

***

## **✨ Overview**

Modern firewalls such as **Fortigate** support *External Dynamic Lists (EDL)* to centralize blocklists and reduce configuration complexity.  
In theory, EDLs should eliminate the need to constantly edit firewall rules and objects manually.

In practice, most organizations still struggle with:

*   Blocklists hidden inside firewall configuration
*   Growing, duplicated, or inconsistent IP objects
*   No audit trail explaining *who* added an IP and *why*
*   No way to cleanly expire old blocks
*   Sysadmins bypassing the EDL because updating it is too painful
*   Lack of separation between “firewall management” and “threat/risk decisions”

This project solves that problem.

***

## **🎯 What This Tool Solves**

### **1. Easy manipulation of firewall blocklists**

Instead of modifying firewall configuration directly, administrators can:

*   Add IP addresses
*   Remove IP addresses
*   Bulk add multiple IPs
*   Assign reasons
*   Set expiration periods (1d, 1w, 1m, …)

All from a simple, intuitive, browser‑based interface.

### **2. No bloat inside the firewall**

The firewall configuration stays clean:

*   No giant address groups
*   No ever‑growing list of inconsistent object names
*   No need to reload firewall config or create new objects
*   The Fortigate merely fetches a text list served by this application

The firewall becomes a *consumer* of blocklists, not the database for them.

### **3. Multiple independent blocklists**

The application supports **multiple lists**, allowing clear separation of use cases:

*   Outbound blocklist
*   Inbound blocklist
*   Temporary quarantine list
*   Partner‑specific “deny” lists
*   SOC‑driven IP bans

Each list is exposed via:

    /api/list?id=<list_name>

### **4. Full audit trail**

Every action is logged:

*   Add
*   Remove
*   Automatic expiration

With metadata:

*   IP
*   Actor (via OIDC identity)
*   Reason
*   Expiration timestamp
*   List name
*   Timestamp

Audit logs are:

*   Stored in PostgreSQL (append‑only)
*   Forwarded to syslog so SIEMs can ingest them automatically
*   Viewable (but not exportable) in the UI

### **5. Automatic expiration**

Entries expire automatically the moment the firewall requests the list.

This removes stale blocks, avoids “blocklist creep”, and improves clarity.

### **6. Minimal operational footprint**

The entire system runs inside **three lightweight containers**:

1.  The Python-based application
2.  The HTTPS reverse proxy
3.  PostgreSQL database

And upgrades are as simple as:

    docker compose down
    docker compose pull -a
    docker compose up -d

### **7. Seamless security & authentication**

The application uses **OIDC SSO** (Azure AD, Okta, Keycloak…) for administrators:

*   Zero-friction login
*   Group-based authorization
*   No passwords managed in the app

The only Basic Auth credential required is for Fortigate EDL access.

***

## **📌 Business Value**

### **Reduce firewall complexity**

A cluttered firewall configuration is a risk:

*   Harder to audit
*   Harder to maintain
*   Higher chance of configuration drift
*   More difficult change control

This application externalizes and simplifies blocklist management.

### **Improve traceability & accountability**

Firewall objects do not provide visibility on *why* changes were made.  
This platform records:

*   Who added an IP
*   When
*   For what reason
*   For how long

This drastically improves:

*   Incident response
*   Forensics
*   Change review
*   SOC/firewall team communication

### **Enable secure delegation**

Network teams no longer need to edit firewall configuration themselves.  
Security analysts, SOC operators, or incident responders can:

*   Enforce blocks
*   Lift blocks
*   Call urgent containment actions

…without touching the firewall.

### **Support multiple firewalls / vendors**

Although initially designed for Fortigate EDLs, this service is generic:

*   Any firewall supporting HTTP-based external feeds can consume the lists
*   Same for WAFs, reverse proxies, NDR tools, etc.

### **Avoid vendor lock-in**

The output format is intentionally simple:

    <one IP per line>

It works anywhere.

***

## **📚 Summary**

This tool exists to make security teams faster and firewall teams happier.

It provides:

*   Simple UI for IP blocklist management
*   Clear audit trail
*   Automatic expiration
*   Externalized list generation
*   Minimal operational overhead
*   Clean firewall configuration
*   Seamless SSO authentication

It is a **practical**, **lightweight**, and **auditable** solution to a very common problem:  
**“How do we manage dynamic blocklists without making a mess?”**

