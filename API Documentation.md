# API Documentation

This document describes the available REST API endpoints for **Chat** and **Nodes**. More will be added later.

---

## **Chat API**

### **`GET /api/chat`**
Fetches chat messages, with support for both initial loading and incremental updates.

#### **Query Parameters**
| Name     | Type   | Required | Description |
|----------|--------|----------|-------------|
| `limit`  | int    | No       | Number of messages to return (default: 100, max: 200). |
| `since`  | string | No       | Return only messages with `import_time > since` (ISO 8601 format, e.g., `2025-07-21T12:00:00`). |

#### **Response (200 OK)**
```json
{
  "packets": [
    {
      "id": 123,
      "import_time": "2025-07-22T14:12:00.123456",
      "channel": "LongFast",
      "from_node_id": 456789,
      "long_name": "Node A",
      "payload": "Hello world!"
    }
  ],
  "latest_import_time": "2025-07-22T14:12:00.123456"
}
```

**Fields:**
- `id`: Unique packet ID.
- `import_time`: ISO 8601 timestamp of when the message was imported.
- `channel`: Channel name.
- `from_node_id`: Numeric ID of the node that sent the message.
- `long_name`: Human-readable name of the node (if available).
- `payload`: Actual message text.

#### **Examples**
- **Get last 50 messages:**
  ```
  GET /api/chat?limit=50
  ```
- **Get messages after a certain timestamp:**
  ```
  GET /api/chat?since=2025-07-22T12:00:00
  ```

---

## **Nodes API**

### **`GET /api/nodes`**
Returns a list of all nodes, with optional filters based on "last seen" time.

#### **Query Parameters**
| Name              | Type   | Required | Description |
|-------------------|--------|----------|-------------|
| `hours`           | int    | No       | Only return nodes seen within the last `N` hours. |
| `days`            | int    | No       | Only return nodes seen within the last `N` days. |
| `last_seen_after` | string | No       | Custom ISO 8601 timestamp for filtering (`2025-07-21T10:00:00`). |

**Note:** `hours` and `days` take precedence over `last_seen_after`.

#### **Response (200 OK)**
```json
{
  "nodes": [
    {
      "node_id": 123456,
      "long_name": "BaseStation",
      "short_name": "BS",
      "channel": "LongFast",
      "last_seen": "2025-07-22T14:10:00.000000",
      "hardware": "Heltec V3",
      "firmware": "1.3.2",
      "role": "CLIENT"
    }
  ]
}
```

**Fields:**
- `node_id`: Unique ID of the node.
- `long_name`: Full descriptive name of the node.
- `short_name`: Short name or alias.
- `channel`: Channel the node is configured on.
- `last_seen`: ISO 8601 timestamp of the last time the node was seen.
- `hardware`: Hardware model (e.g., Heltec V3).
- `firmware`: Firmware version of the node.
- `role`: Node role (e.g., `CLIENT`, `ROUTER`, etc.).

#### **Examples**
- **All nodes:**
  ```
  GET /api/nodes
  ```
- **Nodes seen in the last 1 hour:**
  ```
  GET /api/nodes?hours=1
  ```
- **Nodes seen in the last 7 days:**
  ```
  GET /api/nodes?days=7
  ```
- **Custom timestamp:**
  ```
  GET /api/nodes?last_seen_after=2025-07-21T12:00:00
  ```

---

## **General Notes**
- All timestamps are returned in **localtime** (ISO 8601 format).
- Both endpoints return JSON responses with `application/json` content type.
- Error responses return `{"error": "message"}` with an appropriate HTTP status code (e.g., `500`).

---
