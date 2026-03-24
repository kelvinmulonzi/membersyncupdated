# MemberSync API Documentation

## Base URL
```
http://localhost:5000/api/v1
```

## Authentication
- Most endpoints are public (member self-service)
- No authentication required for member APIs
- Uses membership_id for identification

---

## 🏢 Organizations

### GET /api/v1/organizations
**Purpose**: Get list of available organizations for registration

**Response:**
```json
{
  "success": true,
  "organizations": [
    {
      "id": 1,
      "name": "string",
      "industry": "string",
      "location": "string",
      "status": "active"
    }
  ]
}
```

**Status Codes:**
- `200` - Success
- `500` - Server error

---

### POST /api/v1/register
**Purpose**: Member self-registration with organization selection

**Request Body:**
```json
{
  "name": "string" (required),
  "email": "string" (required),
  "phone": "string" (required), 
  "password": "string" (required),
  "birthdate": "string" (optional, format: YYYY-MM-DD),
  "gender": "string" (optional, values: "Male", "Female", "Other"),
  "organization_id": "number" (required),
  "membership_type": "string" (optional, default: "Standard")
}
```

**Response:**
```json
{
  "success": true,
  "message": "Registration successful",
  "member": {
    "membership_id": "string",
    "name": "string",
    "email": "string", 
    "organization_id": "number"
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "You are already registered with this organization"
}
```

**Status Codes:**
- `200` - Success
- `400` - Bad Request (missing data or invalid organization)
- `409` - Email/phone already exists in same organization

---

## 🔐 Authentication Endpoints

### POST /api/v1/login
**Purpose**: Member login using membership ID only

**Request Body:**
```json
{
  "membership_id": "string" (required)
}
```

**Response:**
```json
{
  "success": true,
  "member": {
    "membership_id": "string",
    "name": "string", 
    "email": "string",
    "phone": "string",
    "organization_id": "number",
    "photo_url": "string|null"
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Invalid membership ID"
}
```

**Status Codes:**
- `200` - Success
- `400` - Bad Request (missing data)
- `401` - Invalid membership ID
- `403` - Account not active

---

### POST /api/v1/register
**Purpose**: Member self-registration

**Request Body:**
```json
{
  "name": "string" (required),
  "email": "string" (required),
  "phone": "string" (required), 
  "password": "string" (required),
  "organization_id": "number" (optional, default: 1),
  "membership_type": "string" (optional, default: "Standard")
}
```

**Response:**
```json
{
  "success": true,
  "message": "Registration successful",
  "member": {
    "membership_id": "string",
    "name": "string",
    "email": "string", 
    "organization_id": "number"
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Email or phone already registered"
}
```

**Status Codes:**
- `200` - Success
- `400` - Bad Request (missing data)
- `409` - Email/phone already exists

---

### POST /api/v1/set-password
**Purpose**: Set password for existing members

**Request Body:**
```json
{
  "membership_id": "string" (required),
  "password": "string" (required)
}
```

**Response:**
```json
{
  "success": true,
  "message": "Password set successfully"
}
```

---

## 👤 Member Profile Endpoints

### GET /api/v1/members/{membership_id}/profile
**Purpose**: Get member profile information

**Path Parameters:**
- `membership_id` (string): Member's unique ID

**Response:**
```json
{
  "success": true,
  "data": {
    "membership_id": "string",
    "name": "string",
    "email": "string",
    "phone": "string",
    "type": "string",
    "expiration": "string|null",
    "status": "string",
    "organization": "string",
    "photo_url": "string|null",
    "birthdate": "string|null",
    "gender": "string|null"
  }
}
```

**Status Codes:**
- `200` - Success
- `404` - Member not found

---

### PUT /api/v1/members/{membership_id}/profile
**Purpose**: Update member profile data

**Path Parameters:**
- `membership_id` (string): Member's unique ID

**Request Body:**
```json
{
  "name": "string" (optional),
  "email": "string" (optional),
  "phone": "string" (optional)
}
```

**Response:**
```json
{
  "success": true,
  "message": "Profile updated successfully",
  "updated_fields": ["name", "email"]
}
```

**Status Codes:**
- `200` - Success
- `400` - No valid fields to update
- `404` - Member not found
- `409` - Email/phone already exists

---

## 💳 Prepaid Balance Endpoints

### GET /api/v1/members/{membership_id}/prepaid
**Purpose**: Get prepaid balance and recent transactions

**Path Parameters:**
- `membership_id` (string): Member's unique ID

**Response:**
```json
{
  "success": true,
  "balance": {
    "current_balance": "number",
    "total_bonus_earned": "number", 
    "total_recharged": "number",
    "total_spent": "number"
  },
  "transactions": [
    {
      "transaction_type": "string",
      "amount": "number",
      "balance_after": "number",
      "description": "string",
      "transaction_date": "string"
    }
  ]
}
```

**Status Codes:**
- `200` - Success
- `404` - Member not found

---

## 🏃 Check-in Endpoints

### GET /api/v1/members/{membership_id}/checkins
**Purpose**: Get member's check-in history

**Path Parameters:**
- `membership_id` (string): Member's unique ID

**Response:**
```json
{
  "success": true,
  "history": [
    {
      "checkin_time": "string",
      "checkout_time": "string|null",
      "service_type": "string",
      "status": "string"
    }
  ]
}
```

**Status Codes:**
- `200` - Success

---

### POST /api/v1/members/{membership_id}/checkin
**Purpose**: Member self check-in

**Path Parameters:**
- `membership_id` (string): Member's unique ID

**Request Body:**
```json
{
  "service_type": "string" (optional, default: "General"),
  "location_id": "number" (optional, default: 1)
}
```

**Response:**
```json
{
  "success": true,
  "message": "Check-in successful",
  "member_name": "string",
  "membership_type": "string",
  "checkin_time": "string",
  "service_type": "string"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Member already checked in"
}
```

**Status Codes:**
- `200` - Success
- `403` - Member account not active
- `404` - Member not found
- `409` - Already checked in

---

## 🔄 Membership Renewal

### POST /api/v1/members/{membership_id}/renew
**Purpose**: Renew membership

**Path Parameters:**
- `membership_id` (string): Member's unique ID

**Request Body:**
```json
{
  "months": "number" (optional, default: 1, min: 1, max: 12),
  "payment_method": "string" (optional, default: "prepaid"),
  "amount": "number" (optional)
}
```

**Response:**
```json
{
  "success": true,
  "message": "Membership renewed successfully",
  "member_name": "string",
  "new_expiry_date": "string",
  "renewal_months": "number",
  "amount_paid": "number",
  "payment_method": "string"
}
```

**Status Codes:**
- `200` - Success
- `400` - Invalid renewal period
- `404` - Member not found

---

## 🔔 Notification Endpoints

### GET /api/v1/members/{membership_id}/notifications
**Purpose**: Get member notifications

**Path Parameters:**
- `membership_id` (string): Member's unique ID

**Response:**
```json
{
  "success": true,
  "notifications": [
    {
      "id": "number",
      "title": "string",
      "message": "string",
      "type": "string",
      "created_at": "string",
      "read_at": "null",
      "is_read": "boolean"
    }
  ],
  "unread_count": "number"
}
```

**Status Codes:**
- `200` - Success
- `404` - Member not found

---

### POST /api/v1/members/{membership_id}/notifications/{notification_id}/read
**Purpose**: Mark notification as read

**Path Parameters:**
- `membership_id` (string): Member's unique ID
- `notification_id` (number): Notification ID

**Response:**
```json
{
  "success": true,
  "message": "Notification marked as read"
}
```

**Status Codes:**
- `200` - Success
- `500` - Server error

---

### GET /api/v1/members/{membership_id}/notifications/stream
**Purpose**: Server-Sent Events (SSE) stream for real-time notifications

**Path Parameters:**
- `membership_id` (string): Member's unique ID

**Response Format:** (Server-Sent Events)
```
data: {"id": 123, "title": "Notification", "message": "Hello", "type": "info", "created_at": "2025-03-08 20:30:00", "is_read": false}

data: {"error": "Member not found"}
```

**Event Types:**
- Regular notification data
- Error messages

**Usage:**
```javascript
const eventSource = new EventSource('/api/v1/members/MBR-000019/notifications/stream');

eventSource.onmessage = function(event) {
    const data = JSON.parse(event.data);
    if (data.error) {
        console.error(data.error);
    } else {
        // Handle new notification
        console.log('New notification:', data);
    }
};
```

---

## 📊 Data Types Reference

### Common Data Types

**string**: Text values
- `membership_id`: Format "MBR-XXXXXX" (e.g., "MBR-000019")
- `email`: Valid email format
- `phone`: Phone number string
- `date/time`: ISO format "YYYY-MM-DD HH:MM:SS"

**number**: Numeric values
- `organization_id`: Integer
- `amount`: Decimal (float)
- `notification_id`: Integer

**boolean**: true/false

### Notification Types
- `info` - General information
- `warning` - Warning messages  
- `success` - Success messages
- `emergency` - Emergency alerts
- `bulk_email` - Bulk email notifications
- `bulk_sms` - Bulk SMS notifications
- `prepaid_recharge` - Prepaid recharge alerts
- `prepaid_usage` - Prepaid usage alerts

### Member Statuses
- `active` - Active member
- `inactive` - Inactive member
- `expired` - Expired membership

### Check-in Statuses
- `checked_in` - Currently checked in
- `checked_out` - Checked out

---

## 🚫 Error Responses

All endpoints return consistent error format:

```json
{
  "success": false,
  "error": "Error message description"
}
```

**Common HTTP Status Codes:**
- `200` - Success
- `400` - Bad Request (invalid data)
- `401` - Unauthorized
- `403` - Forbidden
- `404` - Not Found
- `409` - Conflict (duplicate data)
- `500` - Internal Server Error

---

## 🔧 CORS Configuration

The API supports CORS for the following origins:
- `http://localhost:3000`
- `http://127.0.0.1:3000`
- `http://192.168.0.103:3000`
- `http://localhost:5000`
- `http://127.0.0.1:5000`
- `http://192.168.0.103:5000`

**Allowed Methods:** GET, POST, PUT, DELETE, OPTIONS
**Allowed Headers:** Content-Type, Authorization
**Credentials:** Supported

---

## �️ Environment Variables

Create a `.env` file in your project root with the following variables:

```bash
# Application Base URL (IMPORTANT for password reset links)
APP_BASE_URL=http://localhost:5000  # Development
# APP_BASE_URL=https://membersync.com  # Production

# Database
DATABASE=database.db

# Flask
SECRET_KEY=your_secret_key_here

# Email
EMAIL_ADDRESS=your_email@gmail.com
EMAIL_PASSWORD=your_app_password
```

**Note**: Copy `.env.example` to `.env` and update values for your environment.

---

## �📱 Usage Examples

### Registration Flow
```javascript
// 1. Get available organizations
const orgsResponse = await fetch('/api/v1/organizations');
const { success, organizations } = await orgsResponse.json();

if (success) {
  // Display organizations to user for selection
  console.log('Available organizations:', organizations);
}

// 2. Register with selected organization
const registerResponse = await fetch('/api/v1/register', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ 
    name: 'John Doe',
    email: 'john@example.com',
    phone: '+1234567890',
    password: 'securepassword123',
    birthdate: '1990-05-15',
    gender: 'Male',
    organization_id: 1,  // Selected organization ID
    membership_type: 'Premium'
  })
});

const { success, member } = await registerResponse.json();
```

### Login Flow
```javascript
// Login
const loginResponse = await fetch('/api/v1/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ membership_id: 'MBR-000019' })
});

const { success, member } = await loginResponse.json();
```

### Get Profile
```javascript
// Get member profile
const profileResponse = await fetch('/api/v1/members/MBR-000019/profile');
const { success, data } = await profileResponse.json();
```

### Real-time Notifications
```javascript
// Setup notification stream
const eventSource = new EventSource('/api/v1/members/MBR-000019/notifications/stream');

eventSource.onmessage = function(event) {
  const notification = JSON.parse(event.data);
  if (!notification.error) {
    // Display notification to user
    showNotification(notification);
  }
};
```

---

## 📝 Notes

1. **No Authentication**: Member APIs don't require authentication tokens
2. **Membership ID**: Used as primary identifier for all member operations
3. **Real-time**: Use SSE endpoint for live notifications
4. **Error Handling**: Always check `success` field in responses
5. **Data Validation**: Server validates all input data
6. **Rate Limiting**: Not implemented (add if needed for production)

---

**Last Updated:** March 8, 2026
**API Version:** v1
**Base URL:** http://localhost:5000/api/v1
