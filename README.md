# MemberSync - Enterprise Membership Management System

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://python.org)
[![Flask](https://img.shields.io/badge/Flask-2.3+-green.svg)](https://flask.palletsprojects.com)
[![SQLite](https://img.shields.io/badge/SQLite-3+-lightblue.svg)](https://sqlite.org)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A comprehensive, multi-tenant membership management platform designed for organizations to efficiently manage members, payments, check-ins, communications, and more.

## 🚀 Features

### Core Functionality
- **Multi-Organization Management** - Support for multiple organizations with role-based access
- **Member Management** - Complete member lifecycle from registration to expiration
- **Payment Processing** - Flexible payment options including prepaid cards
- **Check-in System** - Real-time facility access tracking
- **Communication Center** - Email and SMS notifications
- **Digital Membership Cards** - QR code-based digital cards
- **Reporting & Analytics** - Comprehensive reporting dashboard

### Advanced Features
- **Prepaid Card System** - Rechargeable prepaid balances with fee management
- **Discount Management** - Flexible discount codes and promotional campaigns
- **Multi-language Support** - Internationalization ready
- **Role-based Access Control** - Granular permissions system
- **Audit Logging** - Complete transaction and activity tracking
- **Data Export** - CSV/PDF export capabilities

## 🏗️ Architecture

### Tech Stack
- **Backend**: Python 3.8+ with Flask
- **Database**: SQLite with SQLAlchemy-style queries
- **Frontend**: HTML5, Bootstrap 5, JavaScript
- **Authentication**: Session-based with role management
- **File Storage**: Local file system with organized structure
- **QR Codes**: Python QRCode library
- **SMS**: Twilio integration
- **Email**: SMTP integration

### System Requirements
- Python 3.8 or higher
- 2GB RAM minimum
- 1GB disk space
- Modern web browser

## 📦 Installation

### Prerequisites
```bash
# Ensure Python 3.8+ is installed
python --version

# Install virtual environment (recommended)
pip install virtualenv
```

### Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-org/membersync.git
   cd membersync
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   
   # Windows
   venv\Scripts\activate
   
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize the database**
   ```bash
   python app.py
   # The database will be created automatically on first run
   ```

5. **Start the application**
   ```bash
   python app.py
   ```

6. **Access the application**
   - Open your browser and navigate to `http://localhost:5000`
   - Default login credentials:
     - **Username**: `globaladmin`
     - **Password**: `ChangeMe123!`

## 🔐 User Roles & Permissions

### Global Super Admin
- Full system access across all organizations
- User and organization management
- System-wide settings and configuration
- Fee management and reporting
- Membership card downloads

### Organization Super Admin
- Complete access to assigned organization
- Member management and payments
- Check-in monitoring and reports
- Communication management
- Organization settings

### Organization Admin
- Member management within organization
- Payment processing
- Check-in operations
- Basic reporting

## 📊 Key Modules

### Member Management
- **Registration**: Complete member onboarding with photo upload
- **Profile Management**: Comprehensive member profiles with history
- **Membership Types**: Flexible membership categorization
- **Expiration Tracking**: Automated expiration monitoring
- **Photo Management**: Secure photo storage and retrieval

### Payment System
- **Multiple Payment Methods**: Cash, card, prepaid balance
- **Prepaid Cards**: Rechargeable balance system
- **Fee Management**: Configurable percentage-based fees
- **Discount Codes**: Promotional and bulk discounts
- **Payment History**: Complete transaction tracking

### Check-in System
- **Real-time Check-ins**: Instant facility access tracking
- **Service Types**: Categorized service tracking
- **Duration Monitoring**: Automatic time tracking
- **Statistics**: Comprehensive usage analytics
- **Reports**: Detailed check-in reports

### Communication Center
- **Email Notifications**: Automated email campaigns
- **SMS Integration**: Twilio-powered SMS notifications
- **Bulk Messaging**: Mass communication tools
- **Template Management**: Customizable message templates
- **Delivery Tracking**: Message delivery status

## 🛠️ Configuration

### Environment Variables
Create a `.env` file in the root directory:

```env
# Database
DATABASE_URL=sqlite:///membersync.db

# Email Configuration
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password

# SMS Configuration (Twilio)
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token
TWILIO_PHONE_NUMBER=+1234567890

# Security
SECRET_KEY=your-secret-key-here
```

### Database Configuration
The system uses SQLite by default. For production environments, consider PostgreSQL or MySQL:

```python
# For PostgreSQL
DATABASE_URL = 'postgresql://user:password@localhost/membersync'

# For MySQL
DATABASE_URL = 'mysql://user:password@localhost/membersync'
```

## 📈 Usage Examples

### Member Registration
```python
# Register a new member
POST /register
{
    "name": "John Doe",
    "email": "john@example.com",
    "phone": "+1234567890",
    "membership_type": "premium",
    "expiration_date": "2024-12-31"
}
```

### Payment Processing
```python
# Process a payment
POST /payments/MBR-0001
{
    "amount": 100.00,
    "payment_method": "prepaid",
    "notes": "Monthly membership fee"
}
```

### Check-in Processing
```python
# Check in a member
POST /checkin/process
{
    "membership_id": "MBR-0001",
    "service_type": "gym"
}
```

## 🔧 API Endpoints

### Authentication
- `POST /login` - User authentication
- `POST /logout` - User logout
- `POST /register` - User registration

### Member Management
- `GET /members` - List all members
- `POST /register` - Register new member
- `GET /member/<id>` - Get member details
- `POST /edit/<id>` - Update member
- `DELETE /delete/<id>` - Delete member

### Payments
- `GET /payments/<id>` - Get payment history
- `POST /payments/<id>` - Process payment
- `GET /prepaid_card/<id>` - Prepaid card management

### Check-ins
- `POST /checkin/process` - Process check-in
- `GET /checkin/status` - Get check-in status
- `GET /checkin/reports` - Generate reports

## 🚀 Deployment

### Production Deployment

1. **Configure Production Settings**
   ```python
   # In app.py
   app.config['DEBUG'] = False
   app.config['SECRET_KEY'] = 'your-production-secret-key'
   ```

2. **Set up Web Server**
   ```bash
   # Using Gunicorn
   pip install gunicorn
   gunicorn -w 4 -b 0.0.0.0:8000 app:app
   ```

3. **Configure Reverse Proxy (Nginx)**
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;
       
       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
       }
   }
   ```

### Docker Deployment
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 5000
CMD ["python", "app.py"]
```

## 📊 Database Schema

### Core Tables
- `organizations` - Organization management
- `users` - User accounts and roles
- `members` - Member information
- `payments` - Payment transactions
- `prepaid_balances` - Prepaid card balances
- `prepaid_transactions` - Prepaid transaction history
- `checkins` - Check-in records
- `notifications` - Communication history

## 🔒 Security Features

- **Role-based Access Control** - Granular permission system
- **Session Management** - Secure session handling
- **Input Validation** - Comprehensive data validation
- **SQL Injection Prevention** - Parameterized queries
- **File Upload Security** - Secure file handling
- **Password Hashing** - Secure password storage

## 📝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

For support and questions:
- Create an issue in the GitHub repository
- Contact the development team
- Check the documentation wiki

## 🗺️ Roadmap

### Phase 1 ✅ (Completed)
- Membership ID immutability
- Enhanced phone validation
- Card download restrictions
- Fee management system

### Phase 2 (Planned)
- Advanced reporting dashboard
- Mobile app integration
- API rate limiting
- Advanced analytics

### Phase 3 (Future)
- Multi-currency support
- Advanced workflow automation
- Third-party integrations
- Machine learning insights

## 🙏 Acknowledgments

- Flask community for the excellent framework
- Bootstrap team for the responsive UI components
- SQLite team for the reliable database engine
- All contributors and testers

---

**MemberSync** - *Streamlining membership management for modern organizations*

*Built with ❤️ for efficient membership management*