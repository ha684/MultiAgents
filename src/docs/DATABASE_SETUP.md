# Database Setup Guide

This guide explains how to set up the database for production use of the Travel Agent application.

## Overview

The application has been upgraded from in-memory storage to a production-ready database backend using SQLAlchemy ORM. This provides:

- **Persistent storage** - Data survives application restarts
- **Scalability** - Can handle multiple concurrent users
- **Data integrity** - ACID compliance and foreign key constraints
- **Query performance** - Optimized indexes for common queries

## Supported Databases

The application supports:
- PostgreSQL (recommended for production)
- MySQL/MariaDB
- SQLite (for development/testing)

## Database Schema

The database includes the following tables:

### Core Tables
- `conversations` - Stores conversation metadata
- `messages` - Stores all messages with JSONB for flexible content
- `tasks` - Stores task information and status
- `events` - Audit log of all events
- `agents` - Registered agent information

### Supporting Tables
- `task_mappings` - Maps messages to tasks
- `pending_messages` - Tracks messages being processed
- `artifact_chunks` - Stores large artifact data in chunks
- `next_id_mappings` - Maintains message ID chains

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Environment Variables

Create a `.env` file with:

```bash
# PostgreSQL example
DATABASE_URL=postgresql://username:password@localhost:5432/travel_agent_db

# MySQL example
# DATABASE_URL=mysql+pymysql://username:password@localhost:3306/travel_agent_db

# Other required variables
GOOGLE_API_KEY=your_api_key_here
```

### 3. Create Database

#### PostgreSQL:
```bash
createdb travel_agent_db
```

#### MySQL:
```sql
CREATE DATABASE travel_agent_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. Initialize Database Schema

#### Option A: Using SQL Script (Recommended for first setup)
```bash
# PostgreSQL
psql -U username -d travel_agent_db -f docker/init.sql

# MySQL (requires modifications to init.sql for MySQL syntax)
mysql -u username -p travel_agent_db < docker/init.sql
```

#### Option B: Using SQLAlchemy (Auto-creates tables)
The application will automatically create tables on first run if they don't exist.

#### Option C: Using Alembic Migrations (For updates)
```bash
# Initialize Alembic (first time only)
alembic init alembic

# Create initial migration
alembic revision --autogenerate -m "Initial migration"

# Apply migrations
alembic upgrade head
```

### 5. Verify Database Connection

Run the application and check logs:
```bash
python main.py
```

You should see:
```
INFO: DatabaseService initialized
INFO: DatabaseSessionService initialized
```

## Performance Optimization

### Indexes
The schema includes indexes for:
- User conversations lookup
- Message ordering within conversations
- Task status queries
- Event timeline queries

### Connection Pooling
The application uses SQLAlchemy's connection pooling:
- Pool size: 20 connections
- Max overflow: 40 connections
- Pool recycle: 3600 seconds

### Caching
Consider adding Redis for:
- Frequently accessed conversations
- Agent metadata
- Pending message status

## Monitoring and Maintenance

### Regular Tasks
1. **Backup database** - Set up automated backups
2. **Monitor performance** - Check slow query logs
3. **Archive old data** - Move old conversations to archive tables
4. **Update statistics** - Run `ANALYZE` (PostgreSQL) or `OPTIMIZE TABLE` (MySQL)

### Health Checks
Monitor:
- Database connection pool usage
- Query response times
- Table sizes and growth rates
- Index usage statistics

## Troubleshooting

### Common Issues

1. **Connection refused**
   - Check DATABASE_URL format
   - Verify database server is running
   - Check firewall/network settings

2. **Permission denied**
   - Grant necessary permissions to database user
   - PostgreSQL: `GRANT ALL PRIVILEGES ON DATABASE travel_agent_db TO username;`
   - MySQL: `GRANT ALL PRIVILEGES ON travel_agent_db.* TO 'username'@'localhost';`

3. **JSONB not supported**
   - PostgreSQL: Use version 9.4+
   - MySQL: Use version 5.7+ or switch JSONB columns to JSON

4. **Migration conflicts**
   - Check current schema with `alembic current`
   - Resolve conflicts with `alembic downgrade` and `alembic upgrade`

## Production Checklist

- [ ] Set strong database passwords
- [ ] Enable SSL/TLS for database connections
- [ ] Configure automated backups
- [ ] Set up monitoring and alerting
- [ ] Test failover procedures
- [ ] Document recovery procedures
- [ ] Configure log rotation
- [ ] Set appropriate resource limits

## Migration from In-Memory

If migrating from the previous in-memory version:

1. Export existing data (if needed)
2. Stop the application
3. Configure database connection
4. Run database initialization
5. Import existing data (if applicable)
6. Start the application

The new database-backed system maintains the same API interface, so no client-side changes are required. 